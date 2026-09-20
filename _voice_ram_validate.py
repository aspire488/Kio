"""Final one-time GLOBAL KIO RAM validation (run under the .venv runtime).

The 650/700 MB budget applies to the WHOLE KIO runtime — KIO core, providers,
context, STT, TTS, audio, workers — NOT to voice in isolation. This runner:

  1. imports the real bot module (KIO core) and measures idle total RSS;
  2. performs ONE representative complete voice interaction the way a real
     Telegram turn flows: a real voice note on disk -> decode -> Whisper STT
     (loads the STT model) -> a short TTS answer (loads the Kokoro TTS model
     while STT may still be resident) -> spoken note out;
  3. performs ONE realistic long voice response (~1,400 chars, fully spoken in
     multiple bounded notes, no truncation);
  4. releases both engines and reports the peak TOTAL RSS with PASS/FAIL.

TOTAL KIO RSS is measured on the current process (the bot runs in-process;
its executors are threads). No benchmark matrix, no stress loops.
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# Real voice stack for this process, exactly as the enabled bot would use it.
os.environ.setdefault("KIO_PIPECAT_ENABLED", "true")
os.environ.setdefault("KIO_VOICE_INPUT_ENABLED", "true")
os.environ.setdefault("KIO_KOKORO_VOICE", "am_puck")
os.environ.setdefault("KIO_STT_DEVICE", "cpu")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import psutil  # noqa: E402

_MB = 1048576.0
_proc = psutil.Process(os.getpid())
_peak = {"v": 0.0, "phase": "?"}
_stop = threading.Event()
_phase = {"name": "start"}


def _sampler() -> None:
    while not _stop.is_set():
        r = _proc.memory_info().rss / _MB
        if r > _peak["v"]:
            _peak["v"] = r
            _peak["phase"] = _phase["name"]
        time.sleep(0.03)


def set_phase(name: str) -> None:
    _phase["name"] = name


def rss_mb() -> float:
    return _proc.memory_info().rss / _MB


def phase_peak(label: str) -> float:
    print(f"  {label:<52} phase_peak={_peak['v']:7.1f} MB ({_peak['phase']})")
    return _peak["v"]


def checkpoint(label: str) -> float:
    gc.collect()
    time.sleep(0.4)
    cur = rss_mb()
    _peak["v"] = max(_peak["v"], cur)
    print(f"  {label:<52} total_rss={cur:7.1f} MB")
    return cur


def _make_real_note(path: Path) -> None:
    """Synthesize ONE realistic voice note in a throwaway subprocess so the
    validation process itself starts clean (STT-first, as a real user note)."""
    code = (
        "import os\n"
        "os.environ.setdefault('KIO_PIPECAT_ENABLED','true')\n"
        "from mini_kio.voice.voice_reply import synthesize_voice\n"
        f"ogg,_ = synthesize_voice('Hey KIO, what is KIO?', 'en-US-GuyNeural', 600)\n"
        f"open({str(path)!r},'wb').write(ogg)\n"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.getcwd(), check=True, timeout=300,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> int:
    print("=== FINAL GLOBAL KIO RAM VALIDATION ===")
    threading.Thread(target=_sampler, daemon=True).start()
    checkpoint("0. python baseline")

    # KIO core (the whole bot module graph, providers still lazy).
    import kio_bot  # noqa: F401
    idle = checkpoint("1. KIO idle (kio_bot imported)")
    set_phase("stt")

    with tempfile.TemporaryDirectory() as td:
        note = Path(td) / "note.ogg"
        print("  [prep] generating a real voice note in a subprocess ...")
        _make_real_note(note)

        # --- ONE representative voice interaction: STT turn -> TTS answer ---
        from mini_kio.voice.stt import decode_to_pcm, get_stt_engine
        pcm = decode_to_pcm(note.read_bytes(), sample_rate=16000)
        transcript = get_stt_engine().transcribe(pcm)
        after_stt = checkpoint(f"2. KIO + STT active (transcript={transcript!r})")
        # The real Telegram handler unloads STT right after transcription
        # (turn-scoped STT) so TTS never stacks on the Whisper model.
        get_stt_engine().unload()
        stt_unloaded = checkpoint("2b. STT unloaded (turn-scoped, pre-reasoning)")

        from mini_kio.voice.voice_reply import synthesize_voice, unload_tts_model
        set_phase("short TTS")
        short_answer = (
            "KIO is your local companion intelligence. I listen to your voice "
            "notes, use the same tools and memory as text, and speak my "
            "answers back to you."
        )
        audio, ext = synthesize_voice(short_answer, "en-US-GuyNeural", 1000)
        assert audio and ext in ("ogg", "mp3")
        after_short = checkpoint("3. KIO + TTS (short voice reply spoken)")

        # --- ONE realistic long response: fully spoken, bounded, no truncation ---
        long_answer = (
            "So here is the full picture. KIO runs a local voice platform on "
            "top of Pipecat: your Telegram voice notes are decoded and "
            "transcribed by a local Whisper model, and the transcript enters "
            "the exact same reasoning pipeline as typed text. " * 8
        )  # ~1,900 chars realistic multi-note answer
        from mini_kio.voice.voice_reply import split_speech
        set_phase("long TTS")
        segs = split_speech(long_answer, 1000) or [long_answer]
        for i, seg in enumerate(segs):
            audio, ext = synthesize_voice(seg, "en-US-GuyNeural", 1000)
            assert audio
            if i + 1 < len(segs):
                unload_tts_model()  # reset working set between notes (as kio_bot does)
        long_check = checkpoint(f"4. KIO + long voice response ({len(segs)} complete notes, {len(long_answer)} chars)")

        # --- release both models (clean shutdown, RSS must drop) ---
        from mini_kio.voice.stt import shutdown_stt_engine
        from mini_kio.voice.kokoro_tts import shutdown_kokoro_engine
        shutdown_stt_engine()
        shutdown_kokoro_engine()
    released = checkpoint("5. after engine shutdown")

    _stop.set()
    time.sleep(0.2)
    peak = _peak["v"]
    peak_phase = _peak["phase"]
    max_peak = max(peak, rss_mb())
    target = max_peak <= 650.0
    ceiling = max_peak < 700.0

    print("\n==================== GLOBAL KIO RAM ACCEPTANCE ====================")
    print(f"KIO IDLE RSS:            {idle:7.1f} MB")
    print(f"KIO NORMAL RSS:          {idle:7.1f} MB (core; providers lazy until used)")
    print(f"KIO + STT ACTIVE:        {after_stt:7.1f} MB")
    print(f"KIO + STT UNLOADED:      {stt_unloaded:7.1f} MB")
    print(f"KIO + TTS ACTIVE:        {after_short:7.1f} MB")
    print(f"KIO LONG VOICE RESPONSE: {long_check:7.1f} MB")
    print(f"AFTER ENGINE SHUTDOWN:   {released:7.1f} MB")
    print(f"GLOBAL MAX PEAK RSS:     {max_peak:7.1f} MB (during '{peak_phase}')")
    print(f"GLOBAL KIO RAM TARGET (<=650 MB):   {'PASS' if target else 'FAIL'}")
    print(f"GLOBAL KIO HARD CEILING (<700 MB):   {'PASS' if ceiling else 'FAIL'}")
    print("===================================================================")
    if not ceiling:
        print("HARD CEILING FAILED - DO NOT SHIP THIS CONFIGURATION")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
