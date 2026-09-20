"""Media operations — real TTS via edge-tts, real transcoding via ffmpeg.

No external API credentials needed. Uses locally installed binaries.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import json
from pathlib import Path
from typing import Any


def text_to_speech(text: str, output_path: str | None = None,
                   voice: str | None = None) -> dict[str, Any]:
    """Convert text to speech using edge-tts (free Microsoft TTS).

    Returns the path to the generated audio file.
    """
    if not text:
        return {"success": False, "message": "No text provided for TTS"}

    voice = voice or os.environ.get("KIO_TTS_VOICE", "en-US-GuyNeural")
    max_chars = int(os.environ.get("KIO_TTS_MAX_CHARS", "1000"))
    if len(text) > max_chars:
        text = text[:max_chars]

    if not output_path:
        output_dir = Path.home() / "KIO" / "media" / "tts"
        output_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()[:12]
        output_path = str(output_dir / f"tts_{h}.mp3")

    try:
        import edge_tts

        async def _generate():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        asyncio.run(_generate())

        exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
        if exists:
            size = os.path.getsize(output_path)
            return {"success": True, "file_path": output_path, "size_bytes": size,
                    "voice": voice, "text_length": len(text),
                    "message": f"TTS generated: {output_path} ({size} bytes, {voice})"}
        return {"success": False, "message": "edge-tts produced empty file"}
    except ImportError:
        return {"success": False, "message": "edge-tts not installed: pip install edge-tts"}
    except Exception as e:
        return {"success": False, "message": f"TTS failed: {e}"}


def transcode_variants(input_path: str,
                       formats: list[dict[str, str]] | None = None,
                       output_dir: str | None = None) -> dict[str, Any]:
    """Transcode a media file into multiple format variants using ffmpeg.

    formats: [{"ext": "mp3", "codec": "libmp3lame", "bitrate": "128k"},
              {"ext": "wav", "codec": "pcm_s16le"}]
    Default: mp3 128k, wav pcm_s16le, ogg libvorbis.
    """
    if not input_path or not os.path.exists(input_path):
        return {"success": False, "message": f"Input file not found: {input_path}"}

    if formats is None:
        formats = [
            {"ext": "mp3", "codec": "libmp3lame", "bitrate": "128k"},
            {"ext": "wav", "codec": "pcm_s16le"},
            {"ext": "ogg", "codec": "libvorbis", "bitrate": "96k"},
        ]

    if not output_dir:
        output_dir = str(Path(input_path).parent / "variants")
    os.makedirs(output_dir, exist_ok=True)

    stem = Path(input_path).stem
    results = []

    for fmt in formats:
        ext = fmt.get("ext", "mp3")
        codec = fmt.get("codec")
        bitrate = fmt.get("bitrate")
        out_file = os.path.join(output_dir, f"{stem}.{ext}")

        cmd = ["ffmpeg", "-y", "-i", input_path]
        if codec:
            cmd.extend(["-c:a", codec])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
        cmd.append(out_file)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            ok = proc.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 0
            results.append({"ext": ext, "success": ok, "file_path": out_file,
                           "size_bytes": os.path.getsize(out_file) if ok else 0,
                           "error": proc.stderr[:200] if not ok else None})
        except FileNotFoundError:
            return {"success": False, "message": "ffmpeg not found — install ffmpeg and add to PATH",
                    "results": results}
        except subprocess.TimeoutExpired:
            results.append({"ext": ext, "success": False, "error": "ffmpeg timeout (60s)"})
        except Exception as e:
            results.append({"ext": ext, "success": False, "error": str(e)[:200]})

    success_count = sum(1 for r in results if r.get("success"))
    return {"success": success_count > 0, "variants": results,
            "success_count": success_count, "total_count": len(formats),
            "message": f"Transcoded {success_count}/{len(formats)} variants"}


def generate_image(prompt: str, output_path: str | None = None,
                   model: str | None = None) -> dict[str, Any]:
    """Generate image via AI reasoning (delegates to LLM gateway for prompt enhancement).

    For actual image generation, requires an external provider.
    Returns honest status about availability.
    """
    return {"success": False,
            "message": "Image generation requires an external provider (DALL-E, Stable Diffusion, etc.). "
                       "Set up an image generation API to enable this capability."}
