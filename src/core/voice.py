"""
Local clap activation + lightweight speech recognition (optional).

Uses PyAudio with ≥100 ms read chunks and amplitude peaks (no ML).
If the mic or SpeechRecognition is unavailable, optional console fallback applies
only after a successful clap (or enable ENABLE_VOICE_CONSOLE_FALLBACK for typed input).
"""

from __future__ import annotations

import logging
import struct
import threading
import time

logger = logging.getLogger(__name__)


import math

try:
    import numpy as np
except ImportError:
    np = None

def get_rms(data: bytes) -> float:
    if np is not None:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        audio /= 32768.0
        if len(audio) == 0:
            return 0.0
        rms = np.sqrt(np.mean(audio**2))
        return float(rms)
    else:
        n = len(data) // 2
        if n <= 0:
            return 0.0
        fmt = f"<{n}h"
        samples = struct.unpack(fmt, data[: n * 2])
        rms = math.sqrt(sum((float(x)/32768.0)**2 for x in samples) / len(samples))
        return float(rms)


def voice_hardware_available() -> bool:
    try:
        import pyaudio  # noqa: F401

        return True
    except ImportError:
        return False


def run_voice_loop(stop_event: threading.Event) -> None:
    from .config import (
        ENABLE_VOICE_CLAP,
        ENABLE_VOICE_CONSOLE_FALLBACK,
        VOICE_CLAP_COOLDOWN_SEC,
        VOICE_CLAP_THRESHOLD,
        VOICE_DOUBLE_CLAP_MS,
        VOICE_SAMPLE_MS,
        VOICE_SPIKE_REFRACTORY_MS,
    )

    if not ENABLE_VOICE_CLAP:
        return

    try:
        import pyaudio
    except ImportError:
        logger.warning("ENABLE_VOICE_CLAP is set but PyAudio is not installed; voice disabled")
        return

    try:
        import speech_recognition as sr
    except ImportError:
        logger.warning("SpeechRecognition is not installed; voice disabled")
        return

    from .system_skills import send_notification

    rate = 16000
    chunk = 1024
    window_s = VOICE_DOUBLE_CLAP_MS / 1000.0
    cooldown_s = VOICE_CLAP_COOLDOWN_SEC
    threshold = VOICE_CLAP_THRESHOLD
    refractory_s = VOICE_SPIKE_REFRACTORY_MS / 1000.0

    pa = pyaudio.PyAudio()
    device_index = None
    for i in range(pa.get_device_count()):
        dev_info = pa.get_device_info_by_index(i)
        if dev_info.get("maxInputChannels", 0) > 0:
            device_index = i
            print(f"Using microphone: {dev_info.get('name')}")
            break

    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk,
        )
    except OSError as e:
        logger.error("Could not open microphone: %s", e)
        pa.terminate()
        return

    spike_times: list[float] = []
    last_fire = 0.0
    last_spike_at = 0.0
    recognizer = sr.Recognizer()

    last_rms = 0.0
    
    logger.info(
        "KIO voice loop started (chunk=%s, threshold=%s)",
        chunk,
        threshold,
    )

    try:
        while not stop_event.is_set():
            try:
                raw = stream.read(chunk, exception_on_overflow=False)
            except Exception:
                time.sleep(0.1)
                continue
                
            time.sleep(0.04) # 64ms read + 40ms sleep = ~104ms interval
            
            now = time.monotonic()
            if now - last_fire < cooldown_s:
                continue

            rms = get_rms(raw)
            
            if rms > threshold and last_rms <= threshold:
                if now - last_spike_at < refractory_s:
                    last_spike_at = now
                else:
                    last_spike_at = now
                    spike_times = [t for t in spike_times if now - t <= window_s]
                    spike_times.append(now)
                    
                    if len(spike_times) >= 2:
                        spike_times.clear()
                        last_fire = now

                        print("KIO activated", flush=True)
                        send_notification("KIO", "KIO listening...")

                        stream.stop_stream()
                        transcript: str | None = None
                        try:
                            with sr.Microphone(sample_rate=rate) as source:
                                recognizer.adjust_for_ambient_noise(source, duration=0.25)
                                audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)
                            transcript = recognizer.recognize_google(audio)
                        except sr.WaitTimeoutError:
                            transcript = None
                        except sr.UnknownValueError:
                            transcript = None
                        except OSError as e:
                            logger.debug("Speech capture failed: %s", e)
                            transcript = None
                        except Exception as e:
                            logger.debug("Speech recognition error: %s", e)
                            transcript = None
                        finally:
                            try:
                                stream.start_stream()
                            except Exception:
                                logger.exception("Failed to restart clap capture stream")

                        if not transcript and ENABLE_VOICE_CONSOLE_FALLBACK:
                            try:
                                transcript = input("KIO (type command): ").strip() or None
                            except EOFError:
                                transcript = None

                        if transcript:
                            from .command_router import route

                            reply = route(transcript, user_id=None)
                            out = (reply or "").strip()
                            if out:
                                print(out[:2000], flush=True)
                                send_notification("KIO", out[:200])
            last_rms = rms
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        pa.terminate()


def start_voice_daemon(stop_event: threading.Event) -> threading.Thread | None:
    """Start clap + STT loop on a daemon thread if enabled and deps exist."""
    from .config import ENABLE_VOICE_CLAP

    if not ENABLE_VOICE_CLAP:
        return None
    if not voice_hardware_available():
        logger.warning("Voice/clap enabled in config but PyAudio is missing")
        return None

    t = threading.Thread(
        target=run_voice_loop,
        args=(stop_event,),
        name="kio-voice",
        daemon=True,
    )
    t.start()
    return t

def test_clap_detection() -> None:
    print("Microphone detected")
    import pyaudio
    import time
    from .config import VOICE_CLAP_THRESHOLD, VOICE_DOUBLE_CLAP_MS
    
    pa = pyaudio.PyAudio()
    device_index = None
    for i in range(pa.get_device_count()):
        dev_info = pa.get_device_info_by_index(i)
        if dev_info.get("maxInputChannels", 0) > 0:
            device_index = i
            break
            
    if device_index is None:
        print("No microphone found.")
        return
        
    rate = 16000
    chunk = 1024
    
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=rate,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=chunk,
    )
    
    print("RMS baseline: ~0.0")
    print(f"Spike threshold: {VOICE_CLAP_THRESHOLD}")
    print("Test running for 10 seconds. Please clap!")
    
    start_time = time.monotonic()
    spike_times = []
    detected = False
    last_rms = 0.0
    
    try:
        while time.monotonic() - start_time < 10.0:
            try:
                raw = stream.read(chunk, exception_on_overflow=False)
            except Exception:
                time.sleep(0.1)
                continue
                
            time.sleep(0.04) # ~104ms
            rms = get_rms(raw)
            
            now = time.monotonic()
            if rms > VOICE_CLAP_THRESHOLD:
                print(f"RMS: {rms:.3f}  <-- clap spike")
                if last_rms <= VOICE_CLAP_THRESHOLD:
                    spike_times = [t for t in spike_times if now - t <= (VOICE_DOUBLE_CLAP_MS / 1000.0)]
                    spike_times.append(now)
                    if len(spike_times) >= 2:
                        print("Clap detection working")
                        detected = True
                        break
            else:
                print(f"RMS: {rms:.3f}")
                
            last_rms = rms
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        
    if not detected:
        print("\nSpikes not detected: suggest lowering threshold.")


__all__ = [
    "peak_int16",
    "voice_hardware_available",
    "run_voice_loop",
    "start_voice_daemon",
    "test_clap_detection",
]
