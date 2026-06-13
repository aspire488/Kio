// KIO Browser Connector V1 - Full Command Support
// WebSocket ↔ Chrome Extension bridge

const WS_URL = "ws://127.0.0.1:9877";
let AUTH_TOKEN = "";  // Set by runtime message or storage

let socket = null;
let pingInterval = null;
let reconnectTimer = null;
let tokenLoaded = false;
let pendingResolve = {};  // command_id -> { resolve, reject, timer }

function log(level, msg, data) {
  const line = `[KIO Connector] ${level}: ${msg}` + (data ? ` ${JSON.stringify(data)}` : "");
  console.log(line);
}

// ── Token Loading ───────────────────────────────────────────────────

async function loadToken() {
  if (AUTH_TOKEN) return;
  if (tokenLoaded) return;
  tokenLoaded = true;
  try {
    const result = await chrome.storage.local.get(["authToken"]);
    if (result.authToken) {
      AUTH_TOKEN = result.authToken;
      log("INFO", "Token loaded from storage");
    }
  } catch {
    log("WARN", "chrome.storage not available, using hardcoded token");
  }
}

function setToken(token) {
  AUTH_TOKEN = token;
  try {
    chrome.storage.local.set({ authToken: token });
    log("INFO", "Token saved to storage");
  } catch {
    log("WARN", "Cannot save token to storage");
  }
}

// ── Tab Command Handlers ────────────────────────────────────────────

async function handleOpenTab(msg) {
  log("INFO", "Opening tab", { url: msg.url });
  try {
    const tab = await chrome.tabs.create({ url: msg.url });
    log("FOCUS", "Window focus requested", { windowId: tab.windowId });
    await chrome.windows.update(tab.windowId, { focused: true });
    log("FOCUS", "Window focus success", { windowId: tab.windowId });
    log("SUCCESS", "Tab created", { tabId: tab.id, url: tab.pendingUrl || tab.url });
    return {
      type: "result",
      success: true,
      command_id: msg.command_id,
      tab_id: tab.id,
      url: tab.pendingUrl || tab.url,
      title: tab.title || "",
      window_id: tab.windowId,
    };
  } catch (err) {
    log("ERROR", "Failed to open tab", { error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

async function handleCloseTab(msg) {
  log("INFO", "Closing tab", { tabId: msg.tab_id });
  try {
    await chrome.tabs.remove(msg.tab_id);
    log("SUCCESS", "Tab closed", { tabId: msg.tab_id });
    return { type: "result", success: true, command_id: msg.command_id, tab_id: msg.tab_id };
  } catch (err) {
    log("ERROR", "Failed to close tab", { error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

async function handleFocusTab(msg) {
  log("INFO", "Focusing tab", { tabId: msg.tab_id });
  try {
    const tab = await chrome.tabs.get(msg.tab_id);
    log("FOCUS", "Tab focus window update", { windowId: tab.windowId });
    await chrome.windows.update(tab.windowId, { focused: true });
    await chrome.tabs.update(msg.tab_id, { active: true });
    log("FOCUS", "Tab focus success", { tabId: msg.tab_id });
    log("SUCCESS", "Tab focused", { tabId: msg.tab_id });
    return { type: "result", success: true, command_id: msg.command_id, tab_id: msg.tab_id };
  } catch (err) {
    log("ERROR", "Failed to focus tab", { error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

async function handleNavigateTab(msg) {
  log("INFO", "Navigating tab", { tabId: msg.tab_id, url: msg.url });
  try {
    const tab = await chrome.tabs.get(msg.tab_id);
    log("FOCUS", "Navigate tab window focus", { windowId: tab.windowId });
    await chrome.windows.update(tab.windowId, { focused: true });
    await chrome.tabs.update(msg.tab_id, { url: msg.url, active: true });
    log("SUCCESS", "Tab navigated", { tabId: msg.tab_id, url: msg.url });
    return {
      type: "result",
      success: true,
      command_id: msg.command_id,
      tab_id: msg.tab_id,
      url: msg.url,
      title: tab.title || "",
      window_id: tab.windowId,
    };
  } catch (err) {
    log("ERROR", "Failed to navigate tab", { error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

// ── MV3 Static Script Registry ────────────────────────────────────────
// Pre-defined functions for all supported operations.
// No eval(), no new Function() — fully MV3 CSP compliant.

const SCRIPTS = {
  play: async () => {
    // ── Initial Page Diagnostics ────────────────────────────────────
    const diag = {
      url: location.href,
      title: document.title,
      hasVideo: !!document.querySelector('video'),
      hasMoviePlayer: !!document.getElementById('movie_player'),
      hasWatchFlexy: !!document.querySelector('ytd-watch-flexy'),
      readyState: -1,
      networkState: -1,
      paused: true,
      ended: false,
      currentTime: 0,
      duration: 0,
      muted: false,
      volume: 1,
      src: '',
      player_status: 'unknown',
      waited_ms: 0,
      transitions: [],
      exceptionName: '',
      exceptionMessage: '',
      exceptionStack: '',
    };

    let v = document.querySelector('video,audio');
    if (!v) {
      diag.player_status = 'no_video';
      console.log('[PLAY_SCRIPT] no video element found');
      return JSON.stringify({ status: 'no media', ...diag });
    }

    // Capture initial diagnostic snapshot
    diag.readyState = v.readyState;
    diag.networkState = v.networkState;
    diag.paused = v.paused;
    diag.ended = v.ended;
    diag.currentTime = v.currentTime;
    diag.duration = v.duration;
    diag.muted = v.muted;
    diag.volume = v.volume;
    diag.src = v.currentSrc || '';

    // ── Player Readiness Wait (max 10s, poll 250ms) ─────────────────
    const MAX_WAIT_MS = 10000;
    const POLL_MS = 250;
    let waited = 0;
    let lastLoggedState = -1;

    while (waited < MAX_WAIT_MS) {
      v = document.querySelector('video,audio');
      if (!v) {
        diag.transitions.push(`waited=${waited}ms VIDEO_LOST`);
        diag.player_status = 'video_lost_during_wait';
        console.log('[PLAY_SCRIPT] VIDEO_LOST during readiness wait');
        return JSON.stringify({ status: 'no media', ...diag });
      }

      const rs = v.readyState;
      const dur = v.duration || 0;
      const src = v.currentSrc || '';

      if (rs !== lastLoggedState) {
        diag.transitions.push(`waited=${waited}ms readyState=${rs} duration=${dur} src=${src ? 'set' : 'empty'}`);
        lastLoggedState = rs;
        console.log(`[PLAY_SCRIPT] WAIT_PLAYER readyState=${rs} duration=${dur} src=${src ? src.substring(0,80) : '(empty)'}`);
      }

      const met = dur > 0 && rs >= 2 && src.length > 0;
      if (met) {
        diag.transitions.push(`waited=${waited}ms PLAYER_READY readyState=${rs} duration=${dur}`);
        console.log(`[PLAY_SCRIPT] PLAYER_READY readyState=${rs} duration=${dur}`);
        break;
      }

      await new Promise(r => setTimeout(r, POLL_MS));
      waited += POLL_MS;
    }

    diag.waited_ms = waited;

    // Final snapshot before play
    diag.readyState = v.readyState;
    diag.networkState = v.networkState;
    diag.paused = v.paused;
    diag.ended = v.ended;
    diag.currentTime = v.currentTime;
    diag.duration = v.duration;
    diag.muted = v.muted;
    diag.volume = v.volume;
    diag.src = v.currentSrc || '';

    if (!(v.duration > 0 && v.readyState >= 2 && v.currentSrc)) {
      diag.player_status = 'player_not_ready';
      console.log('[PLAY_SCRIPT] PLAYER_NOT_READY after wait',
        { readyState: v.readyState, duration: v.duration, src: !!v.currentSrc, waited_ms: waited });
      return JSON.stringify({ status: 'error', name: 'PlayerNotReady', ...diag });
    }

    // ── Play Attempt ────────────────────────────────────────────────
    diag.player_status = 'play_attempted';
    v.muted = true;
    console.log('[PLAY_SCRIPT] PLAY_START',
      { readyState: v.readyState, duration: v.duration, src: v.currentSrc ? 'set' : 'empty' });

    try {
      const p = v.play();

      // Log promise lifecycle
      p.then(() => {
        console.log('[PLAY_SCRIPT] PLAY_RESOLVED');
      }).catch(err => {
        console.log('[PLAY_SCRIPT] PLAY_REJECTED');
        console.log('[PLAY_SCRIPT] exception_name', err.name);
        console.log('[PLAY_SCRIPT] exception_message', err.message);
        if (err.stack) console.log('[PLAY_SCRIPT] exception_stack', err.stack.substring(0, 500));
      });

      await p;

      // Success
      console.log('[PLAY_SCRIPT] play_succeeded');
      diag.player_status = 'playing';
      return JSON.stringify({
        status: 'playing',
        currentTime: v.currentTime,
        duration: v.duration,
        volume: v.volume,
        muted: v.muted,
        ...diag,
      });

    } catch (e) {
      console.log('[PLAY_SCRIPT] exception_name', e.name);
      console.log('[PLAY_SCRIPT] exception_message', e.message);
      if (e.stack) console.log('[PLAY_SCRIPT] exception_stack', e.stack.substring(0, 500));

      diag.exceptionName = e.name;
      diag.exceptionMessage = e.message;
      diag.exceptionStack = e.stack ? e.stack.substring(0, 500) : '';

      if (e.name === 'NotAllowedError') {
        diag.player_status = 'blocked';
        return JSON.stringify({ status: 'blocked', ...diag });
      }
      if (e.name === 'AbortError') {
        diag.player_status = 'aborted';
        return JSON.stringify({ status: 'error', name: 'AbortError', ...diag });
      }
      diag.player_status = 'error';
      return JSON.stringify({ status: 'error', name: e.name, message: e.message, ...diag });
    }
  },
  pause: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.pause();
    return JSON.stringify({
      status: 'paused',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  stop: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.pause();
    v.currentTime = 0;
    return JSON.stringify({
      status: 'stopped',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  mute: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.muted = true;
    return JSON.stringify({
      status: 'muted',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  unmute: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.muted = false;
    return JSON.stringify({
      status: 'unmuted',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  volume_up: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.volume = Math.min(1, v.volume + 0.1);
    return JSON.stringify({
      status: 'volume_changed',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  volume_down: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.volume = Math.max(0, v.volume - 0.1);
    return JSON.stringify({
      status: 'volume_changed',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  seek_forward: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.currentTime = Math.min(v.duration || 0, v.currentTime + 10);
    return JSON.stringify({
      status: 'seeked',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  seek_backward: () => {
    const v = document.querySelector('video,audio');
    if (!v) return JSON.stringify({ status: 'no media' });
    v.currentTime = Math.max(0, v.currentTime - 10);
    return JSON.stringify({
      status: 'seeked',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  youtube_bootstrap: async () => {
    const _startUrl = window.location.href;
    // Try multiple selectors to find a video result link.
    // Order: most specific first, generic last.
    const s = [
      'a#video-title[href*="/watch?"]',
      'ytd-video-renderer a#video-title',
      'a#video-title',
      'a#thumbnail[href*="/watch?"]',
      'ytd-video-renderer a#thumbnail',
      'a.yt-simple-endpoint[href*="/watch?"]',
      'ytd-video-renderer a.yt-simple-endpoint',
    ];
    let link = null;
    for (const sel of s) {
      const a = document.querySelector(sel);
      if (a && a.href && a.href.includes('/watch?')) {
        link = a;
        break;
      }
    }
    if (!link) {
      console.log('[KIO_BOOTSTRAP] not found url=' + _startUrl);
      return 'not found';
    }

    const targetHref = link.href;
    console.log('[KIO_BOOTSTRAP] click url=' + _startUrl + ' target=' + targetHref);
    link.click();

    // Poll for URL transition to the watch page.
    // YouTube SPA navigation replaces history asynchronously.
    for (let i = 0; i < 25; i++) {
      await new Promise(r => setTimeout(r, 200));
      const _currentUrl = window.location.href;
      if (_currentUrl.includes('/watch?')) {
        console.log('[KIO_BOOTSTRAP] spa transition detected url=' + _currentUrl + ' iteration=' + i);
        return 'navigating';
      }
    }
    // Fallback: navigate directly if SPA didn't transition
    const _fallbackUrl = window.location.href;
    console.log('[KIO_BOOTSTRAP] spa timeout fallback url=' + _fallbackUrl + ' target=' + targetHref);
    window.location.href = targetHref;
    console.log('[KIO_BOOTSTRAP] fallback set newUrl=' + targetHref);
    return 'navigating';
  },
  get_page_info: () => {
    return JSON.stringify({
      url: window.location.href,
      title: document.title,
      hasVideo: !!document.querySelector('video'),
      hasWatchFlexy: !!document.querySelector('ytd-watch-flexy'),
      hasMoviePlayer: !!document.querySelector('#movie_player'),
    });
  },
};

async function handleExecuteScript(msg) {
  const fn = SCRIPTS[msg.script];
  if (!fn) {
    log("ERROR", "Unknown script", { script: msg.script });
    return { type: "result", success: false, command_id: msg.command_id, error: `unknown script: ${msg.script}` };
  }
  log("INFO", "Executing script", { scriptName: msg.script, tabId: msg.tab_id });
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: msg.tab_id },
      func: fn,
    });
    const value = result.result;
    log("SUCCESS", "Script executed", { tabId: msg.tab_id, scriptName: msg.script, result: value });

    let message_value = value;
    if (typeof value === 'string') {
      try {
        message_value = JSON.parse(value);
      } catch (e) {
        // Not JSON, keep as string
      }
    }
    return {
      type: "result",
      success: true,
      command_id: msg.command_id,
      tab_id: msg.tab_id,
      message: message_value,
    };
  } catch (err) {
    log("ERROR", "Failed to execute script", { scriptName: msg.script, error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

async function handleListTabs(msg) {
  log("INFO", "Listing tabs");
  try {
    const tabs = await chrome.tabs.query({});
    const tabList = tabs.map((t) => ({
      tab_id: t.id,
      url: t.url || t.pendingUrl || "",
      title: t.title || "",
      window_id: t.windowId,
      audible: t.audible || false,
      active: t.active || false,
      last_accessed: t.lastAccessed || 0,
    }));
    log("SUCCESS", "Tabs listed", { count: tabList.length });
    return { type: "result", success: true, command_id: msg.command_id, tabs: tabList };
  } catch (err) {
    log("ERROR", "Failed to list tabs", { error: err.message });
    return { type: "result", success: false, command_id: msg.command_id, error: err.message };
  }
}

const COMMAND_HANDLERS = {
  open_tab: handleOpenTab,
  close_tab: handleCloseTab,
  focus_tab: handleFocusTab,
  navigate_tab: handleNavigateTab,
  execute_script: handleExecuteScript,
  list_tabs: handleListTabs,
};

// ── Tab Event Listeners ────────────────────────────────────────────

chrome.tabs.onRemoved.addListener((tabId) => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "tab_closed", tab_id: tabId }));
  }
});

// ── WebSocket Connection ────────────────────────────────────────────

function connect() {
  // RACE FIX: Guard against CONNECTING state to avoid duplicate sockets
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

  log("INFO", "Connecting to " + WS_URL + (AUTH_TOKEN ? " (with token)" : " (bootstrap)"));

  try {
    socket = new WebSocket(WS_URL);
  } catch (err) {
    log("ERROR", "Failed to create WebSocket", { error: err.message });
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    log("SUCCESS", "WebSocket opened");
    const authMsg = { type: "connect", token: AUTH_TOKEN };
    socket.send(JSON.stringify(authMsg));
  };

  socket.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      log("WARN", "Invalid JSON received");
      return;
    }

    // Handle commands from KIO
    if (msg.type in COMMAND_HANDLERS) {
      try {
        const response = await COMMAND_HANDLERS[msg.type](msg);
        socket.send(JSON.stringify(response));
      } catch (err) {
        log("ERROR", "Command handler failed", { type: msg.type, error: err.message });
        const errorResp = {
          type: "result",
          success: false,
          command_id: msg.command_id,
          error: err.message,
        };
        socket.send(JSON.stringify(errorResp));
      }
      return;
    }

    // Handle protocol messages
    switch (msg.type) {
      case "connected":
        log("SUCCESS", "Authentication successful");
        startHeartbeat();
        break;
      case "pong":
        log("SUCCESS", "Pong received");
        break;
      case "set_token":
        setToken(msg.token);
        log("INFO", "Token updated");
        scheduleReconnect();
        break;
      case "ping":
        socket.send(JSON.stringify({ type: "pong" }));
        break;
      default:
        log("WARN", "Unknown message type", { type: msg.type });
    }
  };

  socket.onclose = (event) => {
    log("INFO", "WebSocket closed", { code: event.code });
    stopHeartbeat();
    scheduleReconnect();
  };

  socket.onerror = () => {
    log("ERROR", "WebSocket error");
  };
}

function sendPing() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "ping" }));
}

function startHeartbeat() {
  stopHeartbeat();
  pingInterval = setInterval(sendPing, 15000);
  sendPing();
}

function stopHeartbeat() {
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 3000);
}

// ── Init ────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  log("INFO", "Extension installed/updated");
  await loadToken();
  connect();
});

chrome.runtime.onStartup.addListener(async () => {
  log("INFO", "Browser started");
  await loadToken();
  connect();
});

// Listen for token from KIO or other extensions
chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (msg.type === "set_token" && msg.token) {
    setToken(msg.token);
    connect();
    sendResponse({ success: true });
  }
});

// Init - load token, then connect
loadToken().then(() => connect());
