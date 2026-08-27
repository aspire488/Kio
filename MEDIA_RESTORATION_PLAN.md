# Media restoration plan — current evidence

## Process ownership repair

Evidence on 2026-08-25 showed an old KIO tree rooted at PID 18128. Its child PID 25316 owned `127.0.0.1:9877` and had eight MCP Python children. This is a live listener, not a TIME_WAIT socket. `kio_bot.py` previously had no singleton boundary, allowing every launcher to bootstrap a connector, MCP client and Telegram poller.

Cleanup attempt: `taskkill /PID 18128 /T /F` was explicitly authorized and attempted from this session. Windows returned **Access is denied** for the root, connector, and all descendants. CIM owner lookup identifies both root and connector as `LAPTOP-15TC5R0E\\joelj`; the remaining distinction is elevated/protected-process integrity. Port `9877` remains actively LISTENING under PID 25316.

`mini_kio/core/single_instance.py` now uses a Windows named mutex. `kio_bot.py` acquires it before `run_runtime()`. A second current-code startup exits before bootstrapping any KIO-owned child infrastructure. The mutex is kernel-managed, so an abnormal process exit cannot leave a stale PID lock.

## Validation sequence after legacy-tree removal

1. End the old tree through its owning/elevated session, beginning at PID 18128; do not kill its MCP children individually.
2. Start KIO once with the current launcher.
3. Confirm one Telegram long poller, one port-9877 listener and one owned MCP set.
4. Confirm extension handshake build `0.3.5`.
5. Run Telethon-as-user media acceptance tests, recording browser/player/ad snapshots per request.

Until step 4 succeeds, all playback and transport cases remain **ENVIRONMENT BLOCKED**, not PASS.
