#!/usr/bin/env python3
"""Generate a test voice note for Test 4."""
import asyncio, edge_tts

async def main():
    text = "Hey KIO, what is two plus two?"
    out = "_voice_test4.ogg"
    comm = edge_tts.Communicate(text, voice="en-US-GuyNeural")
    await comm.save(out)
    import os
    print(f"Generated {out}: {os.path.getsize(out)} bytes")

asyncio.run(main())
