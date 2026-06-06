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

async function handleListTabs(msg) {
  log("INFO", "Listing tabs");
  try {
    const tabs = await chrome.tabs.query({});
    const tabList = tabs.map((t) => ({
      tab_id: t.id,
      url: t.url || t.pendingUrl || "",
      title: t.title || "",
      window_id: t.windowId,
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
