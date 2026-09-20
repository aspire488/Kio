"""Standalone Whisper STT worker subprocess (``python -m mini_kio.voice._stt_worker``).

Why a separate process
----------------------
Measured requirement of the GLOBAL KIO RAM contract: faster-whisper /
ctranslate2 modules stay resident in a process (~90 MB) even after the
Whisper model itself is unloaded, and that residual sits on top of the
Kokoro TTS peak (~640 MB) when both share the KIO process — pushing a real
voice turn past the 700 MB hard ceiling. Running Whisper in this dedicated
worker keeps its whole footprint out of the KIO process: the STT turn peaks
near idle+worker (~290 MB process-tree), and the TTS turn runs from KIO's
clean ~56 MB base (~640 MB peak).

Protocol (JSON lines over stdio — no extra IPC dependency, works on Windows)
----------------------------------------------------------------------------
Request  ->  {"id": <int>, "pcm": "<base64 s16le 16 kHz mono>"}
             {"id": <int>, "ping": true}
Response <-  {"id": <int>, "ok": true, "text": "..."}
             {"id": <int>, "ok": false, "error": "..."}
             {"id": <int>, "ok": true, "pong": true}

The worker loads the model lazily on the first request and keeps it warm for
KIO_STT_WORKER_IDLE_UNLOAD_S (~10 s) so consecutive voice notes do not each
pay the model load. EOF on stdin (parent shutdown / parent death) triggers a
clean exit. One request is processed at a time.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time

# Eagerly import heavy libraries at module level.  On Python 3.14+ the import
# lock interacts badly with asyncio.to_thread + run_in_executor when the
# imports happen lazily inside a thread-pool callback (deadlock).
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402


def _cfg(name: str, default: str) -> str:
    return os.getenv(name, default) or default


# ---------------------------------------------------------------------------
# Model management — uses faster-whisper directly (no Pipecat wrapper)
# ---------------------------------------------------------------------------

_model: WhisperModel | None = None
_model_name: str | None = None
_model_device: str | None = None
_model_compute: str | None = None
_last_use = 0.0
_detected_device: str | None = None  # Populated once at startup.


def _detect_device() -> str:
    """Return the compute device for faster-whisper.

    Resolution order:
    1. ``KIO_STT_DEVICE`` env var if set and non-empty (explicit override).
    2. Probe CUDA via ``torch.cuda.is_available()`` — if True, use ``"cuda"``.
    3. Fall back to ``"cpu"``.

    The result is cached in ``_detected_device`` after the first call so the
    probe runs only once per worker lifetime.
    """
    global _detected_device
    if _detected_device is not None:
        return _detected_device

    env_val = os.getenv("KIO_STT_DEVICE", "").strip().lower()
    if env_val:
        _detected_device = env_val
        return _detected_device

    try:
        import torch  # noqa: F811
        if torch.cuda.is_available():
            _detected_device = "cuda"
        else:
            _detected_device = "cpu"
    except Exception:
        _detected_device = "cpu"

    return _detected_device


def _ensure_model() -> WhisperModel:
    """Lazily load the faster-whisper model (blocks ~1-2 s for base.en int8)."""
    global _model, _model_name, _model_device, _model_compute, _last_use
    name = _cfg("KIO_STT_MODEL", "base.en")
    device = _detect_device()
    compute = _cfg("KIO_STT_COMPUTE_TYPE", "int8")

    if _model is not None and (_model_name, _model_device, _model_compute) == (name, device, compute):
        _last_use = time.monotonic()
        return _model

    _model = WhisperModel(name, device=device, compute_type=compute)
    _model_name = name
    _model_device = device
    _model_compute = compute
    _last_use = time.monotonic()
    return _model


def _unload_model() -> None:
    """Release the model so the process shrinks back to near-idle."""
    global _model
    _model = None


def _maybe_idle_unload(idle_ttl: float) -> None:
    """Unload if idle longer than *idle_ttl* seconds."""
    if _model is None:
        return
    if (time.monotonic() - _last_use) < idle_ttl:
        return
    _unload_model()


def _transcribe_sync(pcm: bytes) -> str:
    """Synchronous transcription of 16 kHz mono s16le PCM via faster-whisper."""
    model = _ensure_model()

    # float32 in [-1, 1]
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    segments, _ = model.transcribe(
        audio,
        language="en",
        no_speech_threshold=0.4,
    )
    text = "".join(seg.text for seg in segments).strip()
    if not text:
        raise RuntimeError("no speech detected in audio")
    return text


# ---------------------------------------------------------------------------
# Stdio server
# ---------------------------------------------------------------------------

async def _serve(rfile, wfile) -> int:
    idle_ttl = float(_cfg("KIO_STT_WORKER_IDLE_UNLOAD_S", "10"))

    # ── Startup capability report ─────────────────────────────────────────
    _dev = _detect_device()
    _comp = _cfg("KIO_STT_COMPUTE_TYPE", "int8")
    _mdl = _cfg("KIO_STT_MODEL", "base.en")
    sys.stderr.write(f"[STT_WORKER] device={_dev} compute={_comp} model={_mdl}\n")
    sys.stderr.flush()

    loop = asyncio.get_running_loop()
    _pending: asyncio.Queue[str | None] = asyncio.Queue()
    _on_eof = asyncio.Event()

    def _read_loop():
        while True:
            line = rfile.readline()
            if not line:
                loop.call_soon_threadsafe(_pending.put_nowait, None)
                return
            loop.call_soon_threadsafe(_pending.put_nowait, line)

    reader_task = loop.run_in_executor(None, _read_loop)
    last_idle_check = time.monotonic()
    req: dict = {}
    try:
        while not _on_eof.is_set():
            try:
                item = await asyncio.wait_for(_pending.get(), timeout=0.5)
            except asyncio.TimeoutError:
                now = time.monotonic()
                if now - last_idle_check >= 2.0:
                    last_idle_check = now
                    _maybe_idle_unload(idle_ttl)
                continue

            if item is None:
                break
            item = item.strip()
            if not item:
                continue

            try:
                req = json.loads(item)
                rid = req.get("id")
                if req.get("ping"):
                    wfile.write(json.dumps({"id": rid, "ok": True, "pong": True}) + "\n")
                    wfile.flush()
                    continue

                raw = base64.b64decode(req.get("pcm") or "")
                result = await asyncio.to_thread(_transcribe_sync, raw)
                _last_use = time.monotonic()
                wfile.write(json.dumps({"id": rid, "ok": True, "text": result}) + "\n")
                wfile.flush()
            except Exception as exc:
                wfile.write(
                    json.dumps(
                        {"id": req.get("id", None), "ok": False,
                         "error": f"{type(exc).__name__}: {exc}"}
                    )
                    + "\n"
                )
                wfile.flush()
    finally:
        _unload_model()
        if reader_task is not None:
            reader_task.cancel()
    return 0


def main() -> int:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_serve(sys.stdin, sys.stdout))
    finally:
        try:
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
