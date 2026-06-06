# Browser Connector V1 — Proof of Concept Test Plan

> **HISTORICAL NOTE** (2026-06-04): This POC test plan was created during initial
> design. It references `poc_server.py` which was never built. The connector's
> WebSocket server is implemented directly in `connector.py` and uses bootstrap
> authentication (empty token → `set_token` → reconnect), not hardcoded tokens.
> 
> This document is preserved for historical reference. For current integration
> testing, see `tests/test_connector.py` (82 tests) and
> `mini_kio/browser_connector/ARCHITECTURE_REVIEW.md`.

## Goal

Validate that a Chrome Extension can communicate with a local Python WebSocket
server bidirectionally.

## Prerequisites

- Python 3.11.9
- `websockets` 15.0.1 (installed)
- Chrome browser (any recent version)

## Step 1: Start the POC Server

Open a terminal in the project root:

```powershell
python mini_kio/browser_connector/poc_server.py --token mytoken123
```

**Expected output:**

```
HH:MM:SS [INFO] ==================================================
HH:MM:SS [INFO] KIO Browser Connector POC Server
HH:MM:SS [INFO] Bind:  127.0.0.1:9877
HH:MM:SS [INFO] Token: mytoken123
HH:MM:SS [INFO] ==================================================
HH:MM:SS [INFO] Server started. Waiting for extension connection...
```

Leave this running.

## Step 2: Configure Extension Token

Open `mini_kio/browser_connector/extension/background.js` and set:

```javascript
const AUTH_TOKEN = "mytoken123";
```

Must match the `--token` value from Step 1.

## Step 3: Load Unpacked Extension in Chrome

1. Open Chrome
2. Navigate to `chrome://extensions`
3. Enable **Developer mode** (toggle top-right)
4. Click **Load unpacked**
5. Select the folder: `mini_kio/browser_connector/extension/`
6. The extension appears: "KIO Browser Connector" version 0.1.0

## Step 4: Inspect Extension Logs

1. On `chrome://extensions`, find "KIO Browser Connector"
2. Click **service worker** link (opens DevTools for the background script)
3. Switch to the **Console** tab

## Step 5: Verify Connection

Within 5 seconds of loading the extension, the console should show:

```
[KIO Connector] INFO: Connecting to ws://127.0.0.1:9877
[KIO Connector] SUCCESS: WebSocket opened
[KIO Connector] INFO: Auth sent {type: "connect"}
```

And on the server terminal:

```
HH:MM:SS [INFO] client connected from 127.0.0.1:xxxxx
HH:MM:SS [INFO] auth SUCCESS — token accepted
```

## Step 6: Verify Ping/Pong

After auth, the extension sends an immediate ping. The server responds with pong.

**Server terminal shows:**

```
HH:MM:SS [INFO] auth SUCCESS — token accepted
HH:MM:SS [INFO] ping received
HH:MM:SS [INFO] pong sent
```

**Extension console shows:**

```
[KIO Connector] SUCCESS: Authentication successful — connection established
[KIO Connector] INFO: Ping sent
[KIO Connector] SUCCESS: Pong received — bidirectional communication verified
```

## Step 7: Verify Heartbeat

The extension sends `ping` every 15 seconds. The server responds with `pong` each time.

## Step 8: Test Auth Rejection

1. Stop the server (Ctrl+C)
2. Update `AUTH_TOKEN` in `background.js` to a wrong value
3. Restart the server with a different token
4. Wait for extension reconnect (3s)
5. Server shows:

```
HH:MM:SS [WARNING] auth FAILED — token mismatch
```

6. The WebSocket closes with code 4001
7. Extension reconnects after 3s (and fails again)

## Step 9: Test Disconnect and Reconnect

1. Stop the server (Ctrl+C)
2. Extension console shows:

```
[KIO Connector] INFO: WebSocket closed {code: 1006, reason: ""}
[KIO Connector] INFO: Scheduling reconnect in 3 seconds
```

3. Restart the server
4. Extension reconnects within 3 seconds:

```
[KIO Connector] INFO: Connecting to ws://127.0.0.1:9877
[KIO Connector] SUCCESS: WebSocket opened
[KIO Connector] INFO: Auth sent
[KIO Connector] SUCCESS: Authentication successful
```

## Success Criteria

All of the following must be verified:

- [ ] Server starts and prints bind address + token
- [ ] Extension connects to WebSocket
- [ ] Auth message sent with correct token
- [ ] Server accepts auth, responds with `{"type": "connected"}`
- [ ] Extension sends `{"type": "ping"}`
- [ ] Server receives ping, logs it
- [ ] Server sends `{"type": "pong"}`
- [ ] Extension receives pong, logs success
- [ ] Invalid token is rejected (code 4001)
- [ ] Server restart → extension auto-reconnects

## Expected Final Logs (Server)

```
HH:MM:SS [INFO] ==================================================
HH:MM:SS [INFO] KIO Browser Connector POC Server
HH:MM:SS [INFO] Bind:  127.0.0.1:9877
HH:MM:SS [INFO] Token: mytoken123
HH:MM:SS [INFO] ==================================================
HH:MM:SS [INFO] Server started. Waiting for extension connection...
HH:MM:SS [INFO] client connected from 127.0.0.1:54321
HH:MM:SS [INFO] auth SUCCESS — token accepted
HH:MM:SS [INFO] ping received
HH:MM:SS [INFO] pong sent
HH:MM:SS [INFO] ping received   (repeats every ~15s)
HH:MM:SS [INFO] pong sent
```

## Expected Final Logs (Extension Console)

```
[KIO Connector] INFO: Connecting to ws://127.0.0.1:9877
[KIO Connector] SUCCESS: WebSocket opened
[KIO Connector] INFO: Auth sent {type: "connect"}
[KIO Connector] SUCCESS: Authentication successful — connection established
[KIO Connector] INFO: Ping sent
[KIO Connector] SUCCESS: Pong received — bidirectional communication verified
[KIO Connector] INFO: Ping sent   (repeats every 15s)
[KIO Connector] SUCCESS: Pong received
```
