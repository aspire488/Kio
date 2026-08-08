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

// Player identity: YouTube pages host the real player in #movie_player.
// Every script that touches a media element resolves through _playerVideo()
// so a stray ad/hover <video> is never mistaken for (or controlled as) the
// actual YouTube player. _playerIdentity() reports what was resolved so the
// verification pipeline can reject false "playing" snapshots.
function _playerVideo() {
  const player = document.getElementById('movie_player');
  if (player) {
    const inner = player.querySelector('video');
    if (inner) return inner;
  }
  return document.querySelector('video,audio');
}

function _playerIdentity(v) {
  const player = document.getElementById('movie_player');
  return {
    hasMoviePlayer: !!player,
    isPlayerVideo: !!(player && v && player.contains(v)),
  };
}

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

    let v = _playerVideo();
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
      v = _playerVideo();
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
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    v.muted = true;
    console.log('[PLAY_SCRIPT] PLAY_START',
      { readyState: v.readyState, duration: v.duration, src: v.currentSrc ? 'set' : 'empty', before_muted: _before_muted, before_volume: _before_volume });

    try {
      const p = v.play();

      p.then(() => {
        console.log('[PLAY_SCRIPT] PLAY_RESOLVED');
      }).catch(err => {
        console.log('[PLAY_SCRIPT] PLAY_REJECTED');
        console.log('[PLAY_SCRIPT] exception_name', err.name);
        console.log('[PLAY_SCRIPT] exception_message', err.message);
        if (err.stack) console.log('[PLAY_SCRIPT] exception_stack', err.stack.substring(0, 500));
      });

      await p;

      // Restore audio state that was changed for autoplay bypass
      v.muted = _before_muted;
      v.volume = _before_volume;
      console.log('[PLAY_SCRIPT] audio_restored', { before_muted: _before_muted, before_volume: _before_volume, now_muted: v.muted, now_volume: v.volume });

      // Success
      console.log('[PLAY_SCRIPT] play_succeeded');
      diag.player_status = 'playing';
      return JSON.stringify({
        status: 'playing',
        currentTime: v.currentTime,
        duration: v.duration,
        volume: v.volume,
        muted: v.muted,
        _audio_before_muted: _before_muted,
        _audio_before_volume: _before_volume,
        _audio_restored: true,
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
    const v = _playerVideo();
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
    const v = _playerVideo();
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
    const v = _playerVideo();
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
    const v = _playerVideo();
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
    const v = _playerVideo();
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
    const v = _playerVideo();
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
  set_volume: (level) => {
    try {
      const player = document.getElementById('movie_player');
      if (player && typeof player.setVolume === 'function') {
        player.setVolume(level * 100);
        return JSON.stringify({ success: true, volume: player.getVolume() });
      }
      const video = document.querySelector('video');
      if (video) {
        video.volume = level;
        return JSON.stringify({ success: true, volume: video.volume });
      }
    } catch (e) {
      console.warn("[KIO_VOLUME] Failed to set volume:", e);
    }
    return JSON.stringify({ success: false, error: 'no player found' });
  },
  seek_forward: () => {
    const v = _playerVideo();
    if (!v) return JSON.stringify({ status: 'no media' });
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    v.currentTime = Math.min(v.duration || 0, v.currentTime + 10);
    if (v.muted !== _before_muted) v.muted = _before_muted;
    if (v.volume !== _before_volume) v.volume = _before_volume;
    return JSON.stringify({
      status: 'seeked',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
      _audio_before_muted: _before_muted,
      _audio_before_volume: _before_volume,
      _audio_restored: v.muted === _before_muted && v.volume === _before_volume,
    });
  },
  seek_backward: () => {
    const v = _playerVideo();
    if (!v) return JSON.stringify({ status: 'no media' });
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    v.currentTime = Math.max(0, v.currentTime - 10);
    if (v.muted !== _before_muted) v.muted = _before_muted;
    if (v.volume !== _before_volume) v.volume = _before_volume;
    return JSON.stringify({
      status: 'seeked',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
      _audio_before_muted: _before_muted,
      _audio_before_volume: _before_volume,
      _audio_restored: v.muted === _before_muted && v.volume === _before_volume,
    });
  },
  next_track: () => {
    const url_before = location.href;
    const btn = document.querySelector('.ytp-next-button') || document.querySelector('a[aria-label="Next (Shift+N)"]') || document.querySelector('a[aria-label="Next video"]');
    let clicked = false;
    let button_found = false;
    if (btn) {
      button_found = true;
      btn.click();
      clicked = true;
    } else {
      // Fallback to YouTube keyboard shortcut Shift+N
      const ev = new KeyboardEvent('keydown', { key: 'N', code: 'KeyN', shiftKey: true, bubbles: true });
      document.dispatchEvent(ev);
      clicked = true;
    }
    const url_after = location.href;
    return JSON.stringify({ status: 'navigating', action: 'next', button_found, clicked, url_before, url_after });
  },
  previous_track: () => {
    const url_before = location.href;
    const btn = document.querySelector('.ytp-prev-button') || document.querySelector('a[aria-label="Back (Shift+P)"]') || document.querySelector('a[aria-label="Previous video"]');
    let clicked = false;
    let button_found = false;
    if (btn) {
      button_found = true;
      btn.click();
      clicked = true;
    } else {
      // Fallback to YouTube keyboard shortcut Shift+P
      const ev = new KeyboardEvent('keydown', { key: 'P', code: 'KeyP', shiftKey: true, bubbles: true });
      document.dispatchEvent(ev);
      clicked = true;
    }
    const url_after = location.href;
    return JSON.stringify({ status: 'navigating', action: 'previous', button_found, clicked, url_before, url_after });
  },
  get_page_info: () => {
    return JSON.stringify({
      url: location.href,
      title: document.title,
      hasVideo: !!document.querySelector('video'),
      hasMoviePlayer: !!document.getElementById('movie_player'),
      hasWatchFlexy: !!document.querySelector('ytd-watch-flexy'),
    });
  },
  youtube_bootstrap: async () => {
    const _startUrl = window.location.href;
    
    // If we're already on a watch page, we might just need to wait a bit
    if (_startUrl.includes('/watch?v=')) {
        console.log('[KIO_BOOTSTRAP] already on watch page');
        return 'navigating';
    }

    const s = [
      'ytd-video-renderer a#video-title',
      'ytd-grid-video-renderer a#video-title',
      'ytd-rich-grid-media a#video-title',
      'a#video-title[href*="/watch?"]',
      'a[href*="/watch?v="]',
      'h3 a[href*="/watch?"]',
      'a#thumbnail[href*="/watch?"]',
      'a.yt-simple-endpoint[href*="/watch?"]',
      'ytd-reel-item-renderer a[href*="/watch?"]',
      'ytd-video-renderer a[href*="/watch?"]',
      'ytd-compact-video-renderer a[href*="/watch?"]',
      'ytd-rich-item-renderer a#video-title',
      'ytd-rich-item-renderer a#thumbnail[href*="/watch?"]',
    ];
    
    let link = null;
    // Try standard selectors
    for (const sel of s) {
      const a = document.querySelector(sel);
      if (a && a.href && a.href.includes('/watch?')) {
        link = a;
        break;
      }
    }
    
    if (!link) {
      console.log('[KIO_BOOTSTRAP] not found url=' + _startUrl);
      // Try ANY anchor with /watch? in href
      const allLinks = document.querySelectorAll('a[href*="/watch?"]');
      if (allLinks && allLinks.length > 0) {
        link = allLinks[0];
        console.log('[KIO_BOOTSTRAP] found via fallback selector, count=' + allLinks.length);
      }
    }
    
    if (!link) {
      console.log('[KIO_BOOTSTRAP] not found url=' + _startUrl);
      // Try to click the first thumbnail if title link failed
      const thumb = document.querySelector('ytd-thumbnail a[href*="/watch?"]');
      if (thumb) {
          link = thumb;
      }
    }

    if (!link) {
        return 'not found';
    }

    const targetHref = link.href;
    console.log('[KIO_BOOTSTRAP] click url=' + _startUrl + ' target=' + targetHref);
    link.click();

    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 200));
      const _currentUrl = window.location.href;
      if (_currentUrl.includes('/watch?v=') && _currentUrl !== _startUrl) {
        console.log('[KIO_BOOTSTRAP] spa transition detected url=' + _currentUrl + ' iteration=' + i);
        return 'navigating';
      }
    }
    const _fallbackUrl = window.location.href;
    console.log('[KIO_BOOTSTRAP] spa timeout fallback url=' + _fallbackUrl + ' target=' + targetHref);
    if (!_fallbackUrl.includes('/watch?v=')) {
        window.location.href = targetHref;
    }
    return 'navigating';
  },
  get_player_state: () => {
    // Attempt to get YouTube's internal player state (0-5)
    // -1: unknown, 0: ended, 1: playing, 2: paused, 3: buffering, 5: cued
    try {
      const player = document.getElementById('movie_player');
      if (player && typeof player.getPlayerState === 'function') {
        return JSON.stringify({ playerState: player.getPlayerState() });
      }
    } catch (e) {
      console.warn("[KIO_PLAYER_STATE] Failed to get player state:", e);
    }
    return JSON.stringify({ playerState: -1 }); // Unknown or not available
  },
  sample_media: () => {
    // State probe used by the verification pipeline. NEVER mutates playback.
    // Returns an idempotent snapshot of the current media element so the
    // connector can prove time progression (currentTime advancing) instead of
    // trusting the play ACK alone.
    const v = _playerVideo();
    let playerState = -1;
    try {
      const player = document.getElementById('movie_player');
      if (player && typeof player.getPlayerState === 'function') {
        playerState = player.getPlayerState();
      }
    } catch (e) {
      console.warn("[KIO_SAMPLE_MEDIA] Failed to get player state:", e);
    }
    if (!v) {
      return JSON.stringify({
        ok: false, status: 'no media', url: location.href,
        currentTime: 0, duration: 0, paused: true, playerState,
        ..._playerIdentity(null),
      });
    }
    return JSON.stringify({
      ok: true, status: v.paused ? 'paused' : 'playing',
      url: location.href, paused: v.paused, ended: v.ended,
      currentTime: v.currentTime, duration: v.duration,
      readyState: v.readyState, networkState: v.networkState,
      muted: v.muted, volume: v.volume, playerState,
      ..._playerIdentity(v),
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

// R9: MV3 service workers are terminated after ~30s idle, killing
// setInterval/setTimeout (heartbeat + reconnect). chrome.alarms survives
// termination and wakes the worker, so the extension reconnects even after
// an idle kill instead of waiting for a browser restart / extension reload.
const KEEPALIVE_ALARM = "kio-keepalive";

function ensureKeepaliveAlarm() {
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 1 }, () => {
    if (chrome.runtime.lastError) {
      log("WARN", "alarm create failed", { error: chrome.runtime.lastError.message });
    }
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== KEEPALIVE_ALARM) return;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    log("INFO", "Keepalive alarm fired while disconnected — reconnecting");
    connect();
  } else {
    sendPing();
  }
});

// ── Init ────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  log("INFO", "Extension installed/updated");
  ensureKeepaliveAlarm();
  await loadToken();
  connect();
});

chrome.runtime.onStartup.addListener(async () => {
  log("INFO", "Browser started");
  ensureKeepaliveAlarm();
  await loadToken();
  connect();
});

chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (msg.type === "set_token" && msg.token) {
    setToken(msg.token);
    connect();
    sendResponse({ success: true });
  }
});

ensureKeepaliveAlarm();
loadToken().then(() => connect());
