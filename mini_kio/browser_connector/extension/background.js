// KIO Browser Connector V1 - Full Command Support
// WebSocket ↔ Chrome Extension bridge

const WS_URL = "ws://127.0.0.1:9877";

// Build fingerprint: the runtime compares this against its expected build so
// a stale service worker (Chrome serving a cached copy of background.js) is
// detected and reported clearly instead of producing cryptic "non-state
// payload" failures. Bump together with manifest.json version AND the Python
// constant in mini_kio/browser_connector/build.py (single source of truth;
// keep all three in sync).
const BUILD_VERSION = "0.3.6";

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

// Focusing a MINIMIZED window does not restore it: chrome.windows.update with
// {focused:true} leaves the window minimized, so a requested visible action
// ("play this video", "open github") would load and even play audio inside a
// window the user cannot see — a hidden user-facing action. Restore only when
// minimized; a maximized/fullscreen window is a deliberate user choice and is
// never resized here.
async function ensureWindowVisible(windowId) {
  if (windowId === undefined || windowId === null) return;
  try {
    const win = await chrome.windows.get(windowId);
    if (win && win.state === "minimized") {
      log("FOCUS", "Restoring minimized window", { windowId });
      await chrome.windows.update(windowId, { state: "normal" });
    }
  } catch (err) {
    log("WARN", "Window state check failed", { windowId, error: err.message });
  }
  try {
    await chrome.windows.update(windowId, { focused: true });
  } catch (err) {
    log("WARN", "Window focus failed", { windowId, error: err.message });
  }
}

async function handleOpenTab(msg) {
  log("INFO", "Opening tab", { url: msg.url });
  try {
    const tab = await chrome.tabs.create({ url: msg.url });
    log("FOCUS", "Window focus requested", { windowId: tab.windowId });
    await ensureWindowVisible(tab.windowId);
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
    await ensureWindowVisible(tab.windowId);
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
    await ensureWindowVisible(tab.windowId);
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

// NOTE: chrome.scripting.executeScript({func}) serializes ONLY the function
// body and re-injects it into the page context. Outer-scope identifiers
// (helpers defined in this service worker, BUILD_VERSION, etc.) are NOT
// visible inside the injected function — referencing them makes the script
// return undefined ("success" with no payload). Every script below must
// therefore be FULLY SELF-CONTAINED: inline the #movie_player resolution and
// the build literal. Do not call shared helpers from inside a SCRIPTS fn.

// Player resolution used by the injected scripts. Kept here only as the
// reference implementation; each SCRIPTS fn inlines this exact logic.
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
    // Self-contained player resolution (see SCRIPTS header note).
    const _playerVideoLocal = () => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    };

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

    let v = _playerVideoLocal();
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
      v = _playerVideoLocal();
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
    // Root-cause fix (BUG 3): a raw `video.play()` on YouTube is reconciled
    // back by the player controller — the promise resolves (or the call is
    // silently ignored) but the video stays paused, so currentTime never
    // advances. The canonical programmatic path is the player API
    // `#movie_player.playVideo()`, which the controller recognizes as a
    // first-party play. Prefer it, then fall back to the raw element play
    // (which still works for non-YouTube players / pages without the API).
    //
    // AUTOPLAY POLICY (verified against the live profile): Chrome's strict
    // autoplay policy suspends unmuted programmatic play in this profile.
    // Strategy: try with the current audio state first (the site may be
    // autoplay-whitelisted via user media engagement, giving real sound);
    // if playback is not observed, fall back to MUTED play (always
    // allowed), verify, then best-effort restore audio — re-muting and
    // re-verifying if the restore suspends playback. The final verdict
    // always reflects the state observed AFTER any audio change.
    diag.player_status = 'play_attempted';
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    const _playerApi = document.getElementById('movie_player');
    const _hasApi = !!(_playerApi && typeof _playerApi.playVideo === 'function');

    const _playWithTimeout = async () => {
      // Invoke play (API first, raw fallback) without ever awaiting a
      // permanently-pending promise: when autoplay is blocked/reconciled,
      // Chrome can leave play() pending forever, which would hang the whole
      // connector command (the old 30s freeze). Always race it.
      if (_hasApi) {
        try {
          _playerApi.playVideo();
        } catch (e) {
          console.log('[PLAY_SCRIPT] playVideo threw', e.name, e.message);
        }
        await new Promise(r => setTimeout(r, 600));
      }
      let cur = _playerVideoLocal();
      if (!cur) return null;
      if (cur.paused) {
        try {
          const p = cur.play();
          if (p && typeof p.then === 'function') {
            await Promise.race([
              p.then(() => {
                console.log('[PLAY_SCRIPT] PLAY_RESOLVED');
              }).catch(err => {
                console.log('[PLAY_SCRIPT] PLAY_REJECTED', err.name, err.message);
              }),
              new Promise(r => setTimeout(r, 3000)),
            ]);
          }
        } catch (e) {
          console.log('[PLAY_SCRIPT] raw play threw', e.name, e.message);
        }
      }
      return _playerVideoLocal();
    };

    const _observePlaying = async (budgetMs) => {
      const t0 = (_playerVideoLocal() || v).currentTime || 0;
      const deadline = Date.now() + budgetMs;
      while (Date.now() < deadline) {
        const cur = _playerVideoLocal();
        if (cur && !cur.paused && cur.currentTime > t0) return cur;
        if (cur && !cur.paused && cur.currentTime > 0 && cur.readyState >= 2) return cur;
        await new Promise(r => setTimeout(r, 250));
      }
      return null;
    };

    // Try 1: unmuted play (site may be whitelisted -> real sound).
    let playingEl = await _observePlaying(0); // no-op init
    v = await _playWithTimeout();
    playingEl = v ? await _observePlaying(2500) : null;

    let _muted_play_used = false;
    if (!playingEl) {
      // Try 2: muted play (always allowed by the autoplay policy).
      _muted_play_used = true;
      if (v) v.muted = true;
      v = await _playWithTimeout();
      playingEl = v ? await _observePlaying(4000) : null;
    }

    let _audio_restored = true;
    if (playingEl && _muted_play_used) {
      // Best-effort audio restore: unmute, then RE-VERIFY playback. If the
      // policy suspends it (this profile's behavior), re-mute and re-play
      // so the final state is genuinely playing (muted) — and report that
      // truthfully in the payload.
      playingEl.muted = _before_muted;
      playingEl.volume = _before_volume;
      const after = await _observePlaying(2500);
      if (!after) {
        console.log('[PLAY_SCRIPT] unmute suspended playback - re-muting');
        playingEl.muted = true;
        v = await _playWithTimeout();
        playingEl = v ? await _observePlaying(2500) : null;
        _audio_restored = false;
      } else {
        playingEl = after;
        _audio_restored = true;
      }
    }

    // Final observed snapshot (always post-audio-change).
    v = playingEl || v;
    const _final_playing = !!playingEl;
    console.log('[PLAY_SCRIPT] play_verdict final_playing=' + _final_playing + ' muted_play=' + _muted_play_used + ' audio_restored=' + _audio_restored,
      { currentTime: v ? v.currentTime : 0, paused: v ? v.paused : true, muted: v ? v.muted : false, volume: v ? v.volume : 0 });

    if (!_final_playing) {
      // Truthful: playback is NOT observed (paused / currentTime stuck).
      // Report the observed state so KIO never claims "Playing" without
      // playback.
      diag.player_status = 'paused';
      return JSON.stringify({
        ...diag,
        status: 'paused',
        player_status: 'paused',
        currentTime: v ? v.currentTime : 0,
        duration: v ? v.duration : 0,
        volume: v ? v.volume : 0,
        muted: v ? v.muted : false,
        paused: v ? v.paused : true,
        ended: v ? v.ended : false,
        readyState: v ? v.readyState : 0,
        _play_api_used: _hasApi,
        _muted_play_used,
        _audio_before_muted: _before_muted,
        _audio_before_volume: _before_volume,
        _audio_restored,
      });
    }

    // Success — playback observed in the final state: element is unpaused
    // and currentTime advanced.
    console.log('[PLAY_SCRIPT] play_succeeded (observed)');
    diag.player_status = 'playing';

    // ── AD DETECTION (conservative) ──────────────────────────────────
    // Ad DOM elements can persist in the page even after an ad finishes.
    // We only flag as ad_playing when there is an ACTIVE, VISIBLE ad
    // indicator — specifically a skip button that is rendered and visible.
    // Stale/hidden ad containers do NOT constitute a live ad.
    let _ad_detected = false;
    try {
      // Check for an ACTIVE skip button (only present during a live ad)
      const _skipCandidates = document.querySelectorAll(
        '.ytp-ad-skip-button-modern, .ytp-ad-skip-button, .ytp-skip-ad-button'
      );
      for (const btn of _skipCandidates) {
        if (btn && btn.offsetHeight > 0) {
          const style = window.getComputedStyle(btn);
          if (style.display !== 'none' && style.visibility !== 'hidden') {
            _ad_detected = true;
            console.log('[PLAY_SCRIPT] AD_SKIP_BUTTON_VISIBLE — live ad detected');
            break;
          }
        }
      }
      // If no skip button, check for active ad overlay that covers the player
      if (!_ad_detected) {
        const _overlay = document.querySelector('.ytp-ad-player-overlay');
        if (_overlay && _overlay.offsetHeight > 0) {
          const style = window.getComputedStyle(_overlay);
          if (style.display !== 'none' && style.visibility !== 'hidden') {
            _ad_detected = true;
            console.log('[PLAY_SCRIPT] AD_OVERLAY_VISIBLE — live ad overlay detected');
          }
        }
      }
    } catch (_e) { /* ad detection is best-effort */ }

    if (_ad_detected) {
      console.log('[PLAY_SCRIPT] AD_DETECTED (active) — returning ad_playing status');
      return JSON.stringify({
        ...diag,
        status: 'ad_playing',
        player_status: 'ad_playing',
        currentTime: v.currentTime,
        duration: v.duration,
        volume: v.volume,
        muted: v.muted,
        paused: v.paused,
        ended: v.ended,
        readyState: v.readyState,
        _play_api_used: _hasApi,
        _muted_play_used,
        _audio_before_muted: _before_muted,
        _audio_before_volume: _before_volume,
        _audio_restored,
      });
    }

    return JSON.stringify({
      ...diag,
      status: 'playing',
      player_status: 'playing',
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
      paused: v.paused,
      ended: v.ended,
      readyState: v.readyState,
      _play_api_used: _hasApi,
      _muted_play_used,
      _audio_before_muted: _before_muted,
      _audio_before_volume: _before_volume,
      _audio_restored,
    });
  },
  pause: () => {
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
    if (!v) return JSON.stringify({ status: 'no media' });
    try {
      v.pause();
    } catch (e) {
      return JSON.stringify({ status: 'error', error: e.name || 'pause_exception' });
    }
    // Truthfulness: report the observed state, not the intention. An ACK
    // without proof let KIO claim "Paused" while the video kept playing.
    if (v.paused !== true) {
      return JSON.stringify({ status: 'error', error: 'pause_failed', paused: v.paused });
    }
    return JSON.stringify({
      status: 'paused',
      paused: true,
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  stop: () => {
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
    if (!v) return JSON.stringify({ status: 'no media' });
    try {
      v.pause();
      v.currentTime = 0;
    } catch (e) {
      return JSON.stringify({ status: 'error', error: e.name || 'stop_exception' });
    }
    if (v.paused !== true) {
      return JSON.stringify({ status: 'error', error: 'stop_failed', paused: v.paused });
    }
    return JSON.stringify({
      status: 'stopped',
      paused: true,
      currentTime: v.currentTime,
      duration: v.duration,
      volume: v.volume,
      muted: v.muted,
    });
  },
  mute: () => {
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
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
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
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
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
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
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
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
  seek_forward: (amount = 10) => {
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
    if (!v) return JSON.stringify({ status: 'no media' });
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    const _amt = typeof amount === 'number' ? amount : 10;
    v.currentTime = Math.min(v.duration || 0, v.currentTime + _amt);
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
  seek_backward: (amount = 10) => {
    const v = (() => {
      const player = document.getElementById('movie_player');
      if (player) {
        const inner = player.querySelector('video');
        if (inner) return inner;
      }
      return document.querySelector('video,audio');
    })();
    if (!v) return JSON.stringify({ status: 'no media' });
    const _before_muted = v.muted;
    const _before_volume = v.volume;
    const _amt = typeof amount === 'number' ? amount : 10;
    v.currentTime = Math.max(0, v.currentTime - _amt);
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
  next_track: async () => {
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
    // Wait up to 4s for the SPA route change so url_changed is truthful,
    // not a synchronous read racing the player's navigation.
    const deadline = Date.now() + 4000;
    let url_after = location.href;
    while (Date.now() < deadline && url_after === url_before) {
      await new Promise(r => setTimeout(r, 250));
      url_after = location.href;
    }
    const url_changed = url_after !== url_before;
    return JSON.stringify({ status: url_changed ? 'navigating' : 'no_change', action: 'next', button_found, clicked, url_before, url_after, url_changed });
  },
  previous_track: async () => {
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
    const deadline = Date.now() + 4000;
    let url_after = location.href;
    while (Date.now() < deadline && url_after === url_before) {
      await new Promise(r => setTimeout(r, 250));
      url_after = location.href;
    }
    const url_changed = url_after !== url_before;
    return JSON.stringify({ status: url_changed ? 'navigating' : 'no_change', action: 'previous', button_found, clicked, url_before, url_after, url_changed });
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
  get_build_info: () => {
    // MV3-safe build fingerprint. The build literal is INLINED because the
    // injected function cannot see the outer BUILD_VERSION const (see SCRIPTS
    // header note). Keep in sync with BUILD_VERSION above and manifest.json
    // and mini_kio/browser_connector/build.py.
    return JSON.stringify({ build: '0.3.6' });
  },
  search_results: () => {
    // MV3-safe candidate scrape for controlled YouTube search (R11).
    // Returns the top results as [{title, url, video_id}] — never plays.
    const selectors = [
      'ytd-video-renderer',
      'ytd-grid-video-renderer',
      'ytd-rich-item-renderer',
      'ytd-item-section-renderer',
    ];
    const nodes = Array.from(document.querySelectorAll(selectors.join(',')));
    const results = [];
    for (const node of nodes) {
      const anchor = node.querySelector('a#video-title');
      if (!anchor || !anchor.href) continue;
      let videoId = null;
      try {
        videoId = new URL(anchor.href).searchParams.get('v');
      } catch (e) {
        continue;
      }
      if (!videoId) continue;
      const title = (anchor.title || anchor.textContent || '').trim();
      if (!title) continue;
      results.push({ title: title, url: anchor.href, video_id: videoId });
      if (results.length >= 8) break;
    }
    return JSON.stringify(results);
  },
  sample_media: () => {
    // State probe used by the verification pipeline. NEVER mutates playback.
    // Returns an idempotent snapshot of the current media element so the
    // connector can prove time progression (currentTime advancing) instead of
    // trusting the play ACK alone. Fully self-contained (see SCRIPTS header
    // note) — _playerVideo/_playerIdentity logic inlined below.
    const playerEl = document.getElementById('movie_player');
    const v = (playerEl && playerEl.querySelector('video')) || document.querySelector('video,audio');
    const identity = {
      hasMoviePlayer: !!playerEl,
      isPlayerVideo: !!(playerEl && v && playerEl.contains(v)),
    };
    let playerState = -1;
    try {
      if (playerEl && typeof playerEl.getPlayerState === 'function') {
        playerState = playerEl.getPlayerState();
      }
    } catch (e) {
      console.warn("[KIO_SAMPLE_MEDIA] Failed to get player state:", e);
    }
    if (!v) {
      return JSON.stringify({
        ok: false, status: 'no media', url: location.href,
        currentTime: 0, duration: 0, paused: true, playerState,
        ...identity,
      });
    }
    return JSON.stringify({
      ok: true, status: v.paused ? 'paused' : 'playing',
      url: location.href, paused: v.paused, ended: v.ended,
      currentTime: v.currentTime, duration: v.duration,
      readyState: v.readyState, networkState: v.networkState,
      muted: v.muted, volume: v.volume, playerState,
      ...identity,
    });
  },

  run_js: (code) => {
    const _fn = new Function('return ' + code);
    const _val = _fn();
    return typeof _val === 'string' ? _val : JSON.stringify(_val);
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
    const injectArgs = msg.args || [];
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: msg.tab_id },
      func: fn,
      args: injectArgs,
      // NOTE: chrome.scripting.ScriptInjection has NO userGesture property
      // (verified against the live Chrome 151 schema — it rejects the key).
      // Strict-autoplay handling therefore lives INSIDE the play script:
      // unmuted attempt first, then muted play (always allowed), then
      // best-effort audio restore with re-verification (see SCRIPTS.play).
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
    const authMsg = { type: "connect", token: AUTH_TOKEN, build: BUILD_VERSION };
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
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.417 }, () => {
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
