# Browser Connector V1 — Capability Expansion Architecture

> **Lead Architect**: KIO Architecture v1.1
> **Date**: 2026-06-05
> **Constraint model**: Deterministic, explicit, user-triggered, no autonomy, no surveillance
> **Scope**: Complete browser-extension capability space discovery
> **Runtime base**: Existing V1 connector (WebSocket, auth, registry, open/close/focus/list)

---

## Table of Contents

1. [Browser Capability Surface Map](#1-browser-capability-surface-map)
2. [Maximum-Value Opportunities](#2-maximum-value-opportunities)
3. [Browser OS Vision](#3-browser-os-vision)
4. [100 Real User Scenarios](#4-100-real-user-scenarios)
5. [Architecture Compliance Review](#5-architecture-compliance-review)
6. [Browser Connector Expansion Roadmap](#6-browser-connector-expansion-roadmap)
7. [Hard Rejection List](#7-hard-rejection-list)
8. [Final Strategic Recommendation](#8-final-strategic-recommendation)

---

## 1. Browser Capability Surface Map

Every Chrome extension API analyzed for KIO utility. Grouped by capability domain.

### 1.1 Tabs API (`chrome.tabs`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Tab query | `tabs.query()` | Get all tabs with URL, title, status, window | High | Low (metadata only) | None | ✅ Full |
| Tab create | `tabs.create()` | Open new tab with URL | High | None | <0.1MB (per tab) | ✅ Full |
| Tab remove | `tabs.remove()` | Close tab by ID | High | None | None | ✅ Full |
| Tab update | `tabs.update()` | Navigate existing tab, change URL | High | Low (knows URL) | None | ✅ Full |
| Tab activate | `tabs.update({active:true})` | Focus/activate a tab | High | None | None | ✅ Full |
| Tab mute | `tabs.update({muted:true})` | Mute/unmute tab audio | Medium | None | None | ✅ Full |
| Tab reload | `tabs.reload()` | Refresh a tab | Medium | None | None | ✅ Full |
| Tab duplicate | `tabs.duplicate()` | Duplicate an existing tab | Medium | Low | <0.1MB | ✅ Full |
| Tab highlight | `tabs.highlight()` | Select multiple tabs | Low | None | None | ✅ Full |
| Tab capture | `tabs.captureVisibleTab()` | Screenshot visible area of a tab | High | **High** (page content) | ~5MB per capture | ⚠️ Conditional |
| Tab move | `tabs.move()` | Rearrange tabs within/across windows | Medium | None | None | ✅ Full |
| Tab warmup | `tabs.warmup()` | Pre-render tab for faster loading | Medium (perf) | None | ~10MB | ⚠️ Conditional |
| Tab detect language | `tabs.detectLanguage()` | Detect language of tab content | Low | Low (page lang only) | None | ✅ Full |
| Tab group | `tabs.group()` | Add tabs to a group | High | None | None | ✅ Full |
| Tab ungroup | `tabs.ungroup()` | Remove tabs from group | Medium | None | None | ✅ Full |
| Tab group query | `tabs.query({groupId})` | Get tabs in a group | High | None | None | ✅ Full |
| Tab events | `tabs.onUpdated`, `onActivated`, `onRemoved`, `onCreated`, `onMoved`, `onDetached`, `onAttached`, `onReplaced` | Real-time tab lifecycle notifications | High | Low (metadata only) | None | ✅ Full |
| Tab discard | `tabs.discard()` | Unload tab to free memory | Medium (perf) | None | None | ✅ Full |
| Tab goForward/goBack | `tabs.goForward()`, `tabs.goBack()` | Navigate tab history | Medium | None | None | ✅ Full |
| Tab zoom | `tabs.setZoom()`, `tabs.getZoom()` | Control tab zoom level | Low | None | None | ✅ Full |

### 1.2 Windows API (`chrome.windows`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Window create | `windows.create()` | Open new browser window | High | None | ~20MB per window | ✅ Full |
| Window close | `windows.remove()` | Close browser window | High | None | None | ✅ Full |
| Window focus | `windows.update({focused:true})` | Focus a window | High | None | None | ✅ Full |
| Window minimize | `windows.update({state:"minimized"})` | Minimize window | Medium | None | None | ✅ Full |
| Window maximize | `windows.update({state:"maximized"})` | Maximize window | Medium | None | None | ✅ Full |
| Window fullscreen | `windows.update({state:"fullscreen"})` | Fullscreen window | Medium | None | None | ✅ Full |
| Window query | `windows.getAll()` / `getCurrent()` / `getLastFocused()` | Get window info (tabs, state, bounds) | High | None | None | ✅ Full |
| Window bounds | `windows.update({left,top,width,height})` | Position/resize window | Medium | None | None | ✅ Full |
| Window events | `onCreated`, `onRemoved`, `onFocusChanged`, `onBoundsChanged` | Window lifecycle notifications | Medium | None | None | ✅ Full |

### 1.3 Navigation API (`chrome.webNavigation`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Navigation listener | `webNavigation.onCompleted` | Page load complete | High | Medium (URL visibility) | None | ⚠️ Conditional |
| Frame navigation | `webNavigation.onDOMContentLoaded` | DOM ready | Low | Medium | None | ⚠️ Conditional |
| Error frames | `webNavigation.onErrorOccurred` | Navigation failed | Low | Low | None | ✅ Full |
| Before navigate | `webNavigation.onBeforeNavigate` | Navigation started | Low | Low | None | ⚠️ Conditional |
| History state | `webNavigation.onHistoryStateUpdated` | PushState/replaceState (SPA nav) | Medium | Medium | None | ⚠️ Conditional |
| Reference fragment | `webNavigation.onReferenceFragmentUpdated` | Hash/anchor navigation | Low | Low | None | ⚠️ Conditional |
| Navigation domain | `webNavigation.getAllFrames()` | Get all frames in a tab | Low | Low | None | ⚠️ Conditional |
| Tab index | `tabGroup` for keyboard keyboard for accessibility controls for accessibility and aid | N/A | N/A | N/A | N/A | N/A |

### 1.4 Downloads API (`chrome.downloads`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Download query | `downloads.search()` | Find downloads by query | High | Low (filenames, URLs) | None | ✅ Full |
| Download cancel | `downloads.cancel()` | Cancel active download | Medium | None | None | ✅ Full |
| Download pause/resume | `downloads.pause()` / `downloads.resume()` | Pause/resume downloads | Medium | None | None | ✅ Full |
| Download open | `downloads.open()` | Open downloaded file | Medium | None | None | ✅ Full |
| Download show | `downloads.show()` | Show file in folder | High | None | None | ✅ Full |
| Download remove | `downloads.erase()` | Remove from download history | Low | None | None | ✅ Full |
| Download accept danger | `downloads.acceptDanger()` | Accept dangerous download | Low | None | None | ❌ Unsafe |
| Download drag | `downloads.drag()` | Drag downloaded file | Low | None | None | ✅ Full |
| Download set icon | `downloads.setShelfEnabled()` | Show/hide download shelf | Low | None | None | ✅ Full |
| Download events | `onCreated`, `onChanged`, `onErased` | Download lifecycle notifications | High | Low (metadata only) | None | ✅ Full |

### 1.5 Bookmarks API (`chrome.bookmarks`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Bookmark query | `bookmarks.search()` | Search bookmarks | High | Low (URLs, titles) | None | ✅ Full |
| Bookmark create | `bookmarks.create()` | Create bookmark | High | None | None | ✅ Full |
| Bookmark move | `bookmarks.move()` | Move/r organize bookmark | Low | None | None | ✅ Full |
| Bookmark remove | `bookmarks.remove()` | Delete bookmark | Medium | None | None | ✅ Full |
| Bookmark tree | `bookmarks.getTree()` | Full bookmark hierarchy | High | Medium (all bookmarks exposed) | None | ⚠️ Conditional |
| Bookmark children | `bookmarks.getChildren()` | Get child bookmarks | Medium | Low | None | ✅ Full |
| Bookmark events | `onCreated`, `onRemoved`, `onChanged`, `onMoved`, `onChildrenReordered` | Bookmark change notifications | Medium | None | None | ✅ Full |

### 1.6 Sessions API (`chrome.sessions`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Session query | `sessions.getRecentlyClosed()` | Recently closed tabs/windows | High | Medium (URLs of closed tabs) | None | ✅ Full |
| Session restore | `sessions.restore()` | Reopen closed tab/window | High | None | ~0.1MB | ✅ Full |
| Session list devices | `sessions.getDevices()` | Cross-device sessions | High | **High** (session data from all synced devices) | None | ❌ Unsafe |
| Session events | `onChanged` | When session list changes | Low | None | None | ✅ Full |

### 1.7 History API (`chrome.history`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| History search | `history.search()` | Search browsing history | High | **High** (full history exposed) | None | ❌ Unsafe |
| History getVisits | `history.getVisits()` | Visit timestamps for URL | Medium | **High** (timestamps + URLs) | None | ❌ Unsafe |
| History add | `history.addUrl()` | Add URL to history | Low | None | None | ✅ Full |
| History delete | `history.deleteUrl()` / `deleteRange()` | Delete history | Medium | Medium | None | ⚠️ Conditional |
| History events | `onVisited`, `onVisitRemoved` | History change notifications | Low | **High** (passively observes browsing) | None | ❌ Unsafe |

### 1.8 Notifications API (`chrome.notifications`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Notification create | `notifications.create()` | Show system notification | High | None | None | ✅ Full |
| Notification clear | `notifications.clear()` | Dismiss notification | Low | None | None | ✅ Full |
| Notification events | `onClicked`, `onButtonClicked`, `onClosed` | User interaction with notifications | Medium | None | None | ✅ Full |

### 1.9 Omnibox API (`chrome.omnibox`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Omnibox suggestion | `omnibox.setDefaultSuggestion()` | Custom suggestion in address bar | High | None | None | ✅ Full |
| Omnibox input changed | `omnibox.onInputChanged` | User typing in address bar | Medium | Low (what user types) | None | ⚠️ Conditional |
| Omnibox input entered | `omnibox.onInputEntered` | User selected suggestion | High | None | None | ✅ Full |
| Omnibox input started | `omnibox.onInputStarted` | User started typing | Low | Low | None | ⚠️ Conditional |

### 1.10 Context Menus API (`chrome.contextMenus`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Context menu create | `contextMenus.create()` | Add items to right-click menu | High | None | None | ✅ Full |
| Context menu update | `contextMenus.update()` | Modify context menu item | Medium | None | None | ✅ Full |
| Context menu onClicked | `contextMenus.onClicked` | User clicked context menu | High | None (user triggered) | None | ✅ Full |

### 1.11 Commands / Hotkeys API (`chrome.commands`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Keyboard commands | `commands.onCommand` | Keyboard shortcut to extension | High | None | None | ✅ Full |
| Command manifest | `commands` in manifest | Declare keyboard shortcuts | High | None | None | ✅ Full |

### 1.12 Side Panel API (`chrome.sidePanel`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Side panel open | `sidePanel.open()` | Open extension side panel | Medium | None | ~10MB | ✅ Full |
| Side panel close | `sidePanel.close()` | Close side panel | Low | None | None | ✅ Full |
| Side panel set options | `sidePanel.setOptions()` | Configure panel per-tab | Medium | Low (per-tab panel) | None | ✅ Full |

### 1.13 Clipboard API (`chrome.clipboard`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Clipboard read (text) | `clipboard.read()` (from content script) | Read clipboard text | Medium | **High** (clipboard content) | None | ❌ Unsafe |
| Clipboard write (text) | `clipboard.write()` (from content script) | Write to clipboard | High | None | None | ❌ Unsafe |
| Clipboard read (image) | `clipboard.readImage()` | Read clipboard image | Low | **High** | ~5MB | ❌ Unsafe |
| Clipboard write (image) | `clipboard.writeImage()` | Write image to clipboard | Medium | None | ~5MB | ❌ Unsafe |

### 1.14 Storage API (`chrome.storage`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Local storage | `storage.local` | Extension-local persistent data | High | Medium (stored data) | Varies | ✅ Full |
| Sync storage | `storage.sync` | Cross-device synced storage | High | **High** (syncs to Google) | Varies | ❌ Unsafe |
| Session storage | `storage.session` | In-memory session data | High | Low | Varies | ✅ Full |
| Managed storage | `storage.managed` | Enterprise-policy storage | Low | None | None | ✅ Full |

### 1.15 Search API (`chrome.search`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Search query | `search.query()` | Search via default engine | High | Medium (search terms sent to SE) | None | ⚠️ Conditional |
| Search engine list | `search.getEngines()` | List search engines | Low | Low | None | ✅ Full |

### 1.16 File Handling

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| File download URL | `downloads.download()` | Download file from URL | High | Medium (file URL) | ~1MB+ per file | ✅ Full |
| File reader | File System Access API | Read local files | Medium | **High** (file content) | Varies | ❌ Unsafe |
| Screen capture | `desktopCapture.chooseDesktopMedia()` | Screen/window sharing | Low | **High** (screen content) | ~50MB | ❌ Unsafe |
| File save dialog | `fileSystem.showSaveFilePicker()` | Save blob to file | Medium | None | Varies | ✅ Full |

### 1.17 Browser Actions

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Action badge text | `action.setBadgeText()` | Show text on extension icon | Medium | None | None | ✅ Full |
| Action badge color | `action.setBadgeBackgroundColor()` | Color the badge | Low | None | None | ✅ Full |
| Action popup | `action.setPopup()` | Show popup on icon click | Medium | None | ~1MB | ✅ Full |
| Action icon | `action.setIcon()` | Change extension icon | Low | None | None | ✅ Full |
| Action enabled | `action.enable()` / `action.disable()` | Enable/disable per tab | Low | None | None | ✅ Full |

### 1.18 Permissions API (`chrome.permissions`)

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Permission request | `permissions.request()` | Request optional permissions | Medium | None (user consent) | Varies | ✅ Full |
| Permission check | `permissions.contains()` | Check if permission granted | Medium | None | None | ✅ Full |
| Permission remove | `permissions.remove()` | Remove optional permission | Low | None | None | ✅ Full |

### 1.19 Extension Messaging

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Extension to extension | `runtime.sendMessage` (cross-ext) | Communication between extensions | Low | Medium | None | ⚠️ Conditional |
| Native messaging | `runtime.connectNative()` | Communication with native app | Medium | Low (pipe) | Varies | ⚠️ Conditional |
| Tab messaging | `tabs.sendMessage()` | Message content script | N/A | N/A | N/A | N/A (no content script in current arch) |

### 1.20 Content Scripts

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Script injection | `scripting.executeScript()` | Inject JS into page | High | **High** (arbitrary code) | Varies | ❌ Unsafe |
| CSS injection | `scripting.insertCSS()` | Inject CSS into page | Medium | Low | None | ⚠️ Conditional |
| CSS removal | `scripting.removeCSS()` | Remove injected CSS | Low | None | None | ✅ Full |
| Content script (manifest) | `content_scripts` in manifest | Auto-inject into pages | N/A | N/A | N/A | ❌ Unsafe (current arch) |
| World isolation | `scripting.executeScript({world:"MAIN"})` / `"ISOLATED"` | Control JS execution context | Medium | **High** (page access) | Varies | ❌ Unsafe |

### 1.21 Offscreen APIs

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Offscreen document | `offscreen.createDocument()` | Hidden DOM document for processing | Medium | Low (controlled) | ~10MB | ✅ Full |
| Offscreen close | `offscreen.closeDocument()` | Close offscreen doc | Low | None | None | ✅ Full |
| Offscreen DOM | Offscreen document + DOMParser | Parse HTML without visible browser | High | None | ~10MB | ✅ Full |

### 1.22 Tab Groups API

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Group create | `tabs.group()` | Create tab group | High | None | None | ✅ Full |
| Group ungroup | `tabs.ungroup()` | Remove tab from group | Medium | None | None | ✅ Full |
| Group move | `tabGroups.move()` | Move group position | Medium | None | None | ✅ Full |
| Group update | `tabGroups.update()` | Rename/recolor group | Medium | None | None | ✅ Full |
| Group events | `tabGroups.onCreated`, `onUpdated`, `onMoved`, `onRemoved` | Group lifecycle | Medium | None | None | ✅ Full |
| Group query | `tabGroups.query()` | Get all groups in window | High | None | None | ✅ Full |

### 1.23 Additional APIs

| Capability | Chrome API | Description | User Value | Privacy Impact | RAM Impact | Arch Compat |
|-----------|-----------|-------------|-----------|---------------|-----------|-------------|
| Alarm scheduling | `alarms.create()` | Scheduled background tasks | High | None | None | ✅ Full |
| Idle detection | `idle.queryState()` / `onStateChanged` | Detect user idle state | Medium | Low (idle/present) | None | ✅ Full |
| Power management | `power.requestKeepAwake()` | Prevent system sleep | Low | None | None | ✅ Full |
| Network status | `network.getHops()` / `network.getTrafficInfo()` | Network diagnostics | Low | Medium (network data) | None | ❌ Unsafe |
| User scripts | `userScripts` | Custom user scripts (MV3) | Low | **High** | Varies | ❌ Unsafe |
| Reading list | `readingList` API | Chrome reading list | High | Low (URLs) | None | ✅ Full |
| PDF handling | `pdfViewerPrivate` | PDF viewer integration | Medium | Low | Varies | ✅ Full |
| Printing | `printing` / `printingMetrics` | Print pages/collect metrics | Low | Medium | None | ❌ Unsafe |
| Proxy control | `proxy.settings` | Configure proxy settings | Low | **High** (all traffic) | None | ❌ Unsafe |
| Runtime platform | `runtime.getPlatformInfo()` / `getBrowserInfo()` | Detect OS/browser info | Low | None | None | ✅ Full |
| Runtime restart | `runtime.restart()` | Restart extension | Low | None | None | ✅ Full |
| Display metrics | `system.display.getInfo()` | Monitor info | Low | None | None | ✅ Full |
| CPU info | `system.cpu.getInfo()` | CPU info | Low | None | None | ✅ Full |
| Memory info | `system.memory.getInfo()` | Memory info | Medium | None | None | ✅ Full |
| Storage info | `system.storage.getInfo()` | Storage device info | Low | None | None | ✅ Full |
| Enterprise device | `enterprise.deviceAttributes` | Device attributes | Low | **High** (device identity) | None | ❌ Unsafe |
| Enterprise networking | `enterprise.networkingAttributes` | Network info | Low | **High** (IP, network) | None | ❌ Unsafe |
| Web request | `webRequest` (observing) | Intercept/modify network requests | High | **Very High** (all network traffic) | Varies | ❌ Unsafe |
| Debugger | `debugger.attach()` | Chrome DevTools protocol | Low | **Very High** (full page control) | Varies | ❌ Unsafe |
| Automation | `chrome.automation` | Accessibility tree access | Low | **High** | Varies | ❌ Unsafe |

---

## 2. Maximum-Value Opportunities

Top 50 browser capabilities ranked by value for a personal AI assistant.

### Critical (10)

| Rank | Capability | Domain | Why Critical |
|------|-----------|--------|-------------|
| 1 | **Active tab awareness** | Tabs | The assistant needs to know what the user is looking at to provide context-aware help. `tabs.query({active:true})` is lightweight, explicit, and privacy-safe. |
| 2 | **Workspace management** | TabGroups + Windows | Users organize work into contexts (research, coding, entertainment). Workspace management lets KIO switch between entire browser configurations on demand. Highest multiplicative value. |
| 3 | **Session restore** | Sessions | "Restore yesterday's session" is one of the most common user scenarios. Currently only Chrome's built-in restore exists — no assistant-driven session management. |
| 4 | **Download awareness** | Downloads | Users constantly lose track of downloaded files. Query downloads by date, type, status, or domain. Show recent downloads, alert on completion. |
| 5 | **Bookmark intelligence** | Bookmarks | Bookmark search + create + organize. Users bookmark frequently but never organize them. KIO can save, categorize, and retrieve bookmarks on demand. |
| 6 | **Tab groups** | TabGroups | Tab groups are Chrome's native workspace primitive. KIO can create, name, color, and populate groups based on user intent. |
| 7 | **Reading queue** | Reading List + Tabs | Save pages as "read later" items. Track reading progress. Build a personal reading queue across devices. |
| 8 | **Contextual tab navigation** | Tabs | Navigate existing tabs by querying all tabs and finding the right one. "Take me to the YouTube tab" — activates rather than creates. |
| 9 | **Window management** | Windows | Organize windows by theme (work window, personal window). Move tabs between windows. Create focused workspace windows. |
| 10 | **Quick downloads** | Downloads | Download files programmatically. "Download this PDF", "Save this image" — explicit user-cued actions. |

### High Value (20)

| Rank | Capability | Domain | Why High Value |
|------|-----------|--------|---------------|
| 11 | **Tab muting** | Tabs | "Mute this tab", "Unmute all" — highly requested, trivially simple. |
| 12 | **Tab discarding** | Tabs | "Free up memory" — discard inactive tabs to recover RAM. |
| 13 | **Notification relay** | Notifications | KIO shows system notifications for download complete, tab state changes, or task reminders. |
| 14 | **Command hotkeys** | Commands | Define Ctrl+Shift+K for "ask KIO" — direct voice-to-action from anywhere. |
| 15 | **Context menu integration** | ContextMenus | Right-click a link → "Ask KIO about this" or "Save this to reading list". Right-click text → "Explain this to KIO". |
| 16 | **Tab duplicate** | Tabs | "Copy this tab" — duplicate the current tab for side-by-side comparison. |
| 17 | **Tab refresh** | Tabs | "Refresh this page" or "Reload all" for development workflows. |
| 18 | **Window arrange** | Windows | "Tile two windows side by side" — arrange windows for multitasking. |
| 19 | **Tab capture (visible)** | Tabs | "What's on this page?" — capture visible area to share context with assistant. **Must be explicit, user-triggered, confirmed.** |
| 20 | **Zoom control** | Tabs | "Zoom in", "Zoom to 100%" — accessibility and reading aid. |
| 21 | **Tab language detection** | Tabs | "What language is this page in?" — lightweight content metadata. |
| 22 | **Offscreen page parsing** | Offscreen | Parse a URL's content (title, meta, text) without loading it visibly. For "summarize this link" without opening a new tab. |
| 23 | **Session query** | Sessions | "What did I have open yesterday?" — query recently closed sessions without restoring. |
| 24 | **Bookmark organization** | Bookmarks | "Organize my bookmarks by domain" or "Find duplicate bookmarks" — lightweight command-driven organization. |
| 25 | **Download filter** | Downloads | "Show my PDF downloads from this week" — filter by type, date, source. |
| 26 | **Omnibox search** | Omnibox | Type "kio youtube" in address bar → KIO opens YouTube. Direct keyboard engagement without talking. |
| 27 | **Badge indicators** | Action | Show count of open tabs, active downloads, or unread items on the extension icon. At-a-glance status. |
| 28 | **Side panel toggle** | SidePanel | Open KIO side panel for persistent chat while browsing. Contextual assistant without leaving the page. |
| 29 | **Alarm scheduling** | Alarms | "Remind me about this page in 30 minutes" — scheduled background notifications tied to browser content. |
| 30 | **Window state control** | Windows | "Minimize all", "Restore window" — quick desktop organization. |

### Nice to Have (15)

| Rank | Capability | Domain | Why Nice to Have |
|------|-----------|--------|-----------------|
| 31 | **Tab move between windows** | Tabs | "Move this tab to my work window" — window-level organization. |
| 32 | **CSS injection** | Content Scripts | "Dark mode this site" — explicit CSS injection for readability. Low risk when user-triggered. |
| 33 | **Tab highlighting** | Tabs | "Show all my YouTube tabs" — highlight multiple tabs for visibility. |
| 34 | **Tab warmup** | Tabs | "Preload this link" — speed up navigation for known destinations. |
| 35 | **System memory display** | System | "How much RAM is Chrome using?" — diagnostic insight. |
| 36 | **Download open** | Downloads | "Open that PDF I just downloaded" — directly open downloaded files. |
| 37 | **Tab go back/forward** | Tabs | "Go back" — nav within existing tab. |
| 38 | **Download show in folder** | Downloads | "Show that file" — open file location in Explorer. |
| 39 | **Notification buttons** | Notifications | "Download complete — Open / Show in Folder" via notification buttons. |
| 40 | **Idle detection** | Idle | "Don't notify me when I'm away" — respect user presence. |
| 41 | **Reading list sync** | Reading List | Save cross-device reading list using Chrome's native reading list. |
| 42 | **Tab detect restore** | Sessions | Track which tabs were restored from a session for post-restore workflows. |
| 43 | **Window events** | Windows | "You closed your research window" — awareness without surveillance. |
| 44 | **Reconnect sync** | Sessions | On reconnect, auto-sync registry with Chrome's current tab state. |
| 45 | **Permission progressive** | Permissions | Request optional permissions only when needed. "KIO needs bookmark access to save this — allow?" |

### Not Worth It (5)

| Rank | Capability | Domain | Why Not Worth It |
|------|-----------|--------|------------------|
| 46 | **Tab fullscreen toggle** | Windows | Low value — users use F11. |
| 47 | **Download drag** | Downloads | Drag-and-drop from extension is rarely used. |
| 48 | **Download shelf toggle** | Downloads | Chrome's download shelf is being deprecated. |
| 49 | **Enterprise device attributes** | Enterprise | Not relevant to personal assistant use case. |
| 50 | **Power management** | Power | "Keep Chrome awake" has limited use cases. |

---

## 3. Browser OS Vision

> "If KIO became the operating system for browser activity, what would that look like?"

### 3.1 The Principle

KIO does not replace the browser. KIO **operates** the browser — the same way an operating system manages processes, windows, and resources. The browser is the application layer. KIO is the orchestration layer.

The user speaks. KIO acts. The browser responds.

### 3.2 Design Pillars

1. **All actions are user-triggered.** KIO never does anything in the browser unless the user explicitly asks.
2. **All state is queryable.** If the user asks "what's happening in the browser?" KIO can answer — but only when asked.
3. **All organization is intent-driven.** The user says "I want to research quantum computing" and KIO creates the workspace, loads the sessions, opens the bookmarks.
4. **No persistence without consent.** KIO does not record, store, or index browsing activity unless the user explicitly saves something.

### 3.3 Browser OS Subsystems

#### Workspace System

```
User: "Open my research workspace"
KIO:
  1. Query tab groups for "Research" group
  2. If exists → focus window, expand group
  3. If not → create window, create "Research" group
  4. Open pinned research resources (ArXiv, Scholar, Wikipedia)
  5. Restore previous research session tabs
  6. Arrange window to primary monitor, left half
```

Properties:
- Workspaces are named collections of: window config + tab groups + sessions + bookmarks
- Multiple workspaces can coexist (research window, coding window, personal window)
- Workspaces can be saved ("Save this as my research workspace")
- Workspaces can be shared (export as a collection of URLs)

#### Session System

```
User: "Restore my session from last night"
KIO:
  1. Query chrome.sessions.getRecentlyClosed()
  2. Filter by time window (last 12 hours, excluding current)
  3. Present options: "Restore all 12 tabs?" / "Restore specific tab 7 (YouTube)"
  4. Execute user choice
```

Properties:
- Session is time-anchored: "this morning", "yesterday", "last week"
- Session can be named: "Save this session as 'Research Session June 5'"
- Session can merge: "Add these tabs to my research workspace"
- Session query is explicit — KIO only accesses sessions when asked

#### Reading System

```
User: "Save this page for later"
KIO:
  1. Query active tab URL + title
  2. Add to Chrome reading list (native API)
  3. Or add to KIO-managed reading queue with notes
  4. Notify: "Saved. You have 14 saved pages."
```

```
User: "What's in my reading list?"
KIO:
  1. Query reading list API (or saved URLs)
  2. Group by domain, priority, or save date
  3. Show: "5 tech articles, 3 research papers, 2 recipes"
```

Properties:
- Reading queue has priorities: "Save for tonight" / "Save for weekend"
- Reading progress tracking: "Continue reading 'The Future of AI'" resumes from saved tab
- Reading list can be filtered by read/unread, domain, save date
- Reading list can be cleaned: "Clear all read items"

#### Download System

```
User: "What did I download this week?"
KIO:
  1. Query chrome.downloads.search({})
  2. Filter: startTime=this_week, orderBy=-startTime
  3. Group by type (PDFs, images, zips)
  4. Show: "24 downloads this week. 3 PDFs, 12 images, 2 zips, 7 other."
```

```
User: "Show my recent PDF downloads"
KIO:
  1. Query with {filenameRegex: ".pdf"}
  2. Show: "1. paper.pdf (today)\n2. report.pdf (yesterday)"
```

Properties:
- Download queries are rich: by type, date range, source domain, file size, status
- Download actions: open, show in folder, cancel, pause, resume
- Download auto-categorization: "Sort my downloads into /documents, /images, /archives"

#### Bookmark System

```
User: "Save this page to my research bookmarks"
KIO:
  1. Get active tab URL + title
  2. chrome.bookmarks.create({parentId: "Research", title, url})
  3. Add tags via title convention: "My Page (research, AI, transformers)"
```

```
User: "Find bookmarks about Python"
KIO:
  1. chrome.bookmarks.search("python")
  2. Show: "12 bookmarks found. 5 in 'Coding' folder, 3 in 'Tutorials'."
```

Properties:
- Bookmark search is full-text across titles, URLs, and folders
- Bookmark organization can be automated: "Sort this folder by domain" / "Remove dead links"
- Bookmark import/export: "Save my bookmarks as a markdown list"

#### Knowledge Capture System

```
User: "Save this research paper"
KIO:
  1. Capture visible tab info (URL, title, meta description)
  2. Open offscreen document to parse full page content
  3. Extract: author, date, abstract, key findings
  4. Save to KIO knowledge base + bookmark in "Research" folder
  5. Confirm: "Saved 'Attention Is All You Need' to research."
```

Properties:
- One-shot, explicit save — never automatic
- Content is parsed in offscreen document (no visible tab needed)
- Saved knowledge includes: source URL, capture date, extracted metadata, user notes
- Knowledge base is separate from browser data

#### Study System

```
User: "Help me study this article"
KIO:
  1. Get current tab URL
  2. Parse content via offscreen document
  3. Extract: headings, key terms, summary
  4. Show: "Article has 5 sections. Key terms: attention, transformer, encoder."
  5. Create study workspace with article + related resources
```

Properties:
- Study is active, focused, timeboxed: "Study mode for 45 minutes"
- Study session creates: grouped tabs, notes, highlights
- Study session is saved as a workspace

#### Research System

```
User: "I'm researching quantum error correction"
KIO:
  1. Open research workspace (if not already open)
  2. Query bookmarks for "quantum error correction"
  3. Query recent downloads for related PDFs
  4. Open known resources: arXiv search, Google Scholar
  5. Create tab group "QEC Research"
  6. Show: "I found 4 bookmarks and 2 PDFs. Opening research tools."
```

Properties:
- Research is multi-session: "Continue my research from yesterday"
- Research builds a knowledge graph from saved pages, notes, and citations
- Research can be exported: "Export my research as a markdown bibliography"

#### Focus System

```
User: "Focus mode"
KIO:
  1. Detect current workspace
  2. Mute all non-essential tabs
  3. Discard inactive tabs to free RAM
  4. Close distracting tabs (social media, news)
  5. Enter a timer: "45 minutes of focus remaining"
  6. Minimize other windows
```

Properties:
- Focus is temporary, reversible, and explicit
- Distraction lists are user-defined: "YouTube, Twitter, Reddit"
- Focus can be workspace-specific: "Focus mode for work closes personal tabs"
- Focus can schedule breaks: "25 minutes focus, 5 minutes break"

### 3.4 Browser OS Principles

```
1. Query Only When Asked   — No background scanning of browser state
2. Act Only On Command     — Every action is a direct response to user intent
3. State Is Ephemeral      — No persistent logging of browsing activity
4. Save Is Intentional     — Nothing is saved without explicit user command
5. Organize Is Explicit    — Organization requires user direction or confirmation
6. Automate Is Scripted    — Any automation is a saved, named, user-triggered script
```

### 3.5 Anti-Principles (What Browser OS Is Not)

```
�- Not a tracker           — No page view logging, no history mining
�- Not a profiler          — No user behavior analytics
�- Not a recommender       — No "you might like" suggestions from browsing
�- Not an agent            — No autonomous browsing sessions
�- Not a recorder          — No screen recording, no DOM snapshots without explicit capture
�- Not a feed              — No reading your content for AI training
```

---

## 4. 100 Real User Scenarios

Ranked by estimated real-world usefulness.

### Essential (Scenarios 1-30)

| # | User Says | System Action | Domain |
|---|-----------|--------------|--------|
| 1 | "What tab am I on right now?" | Query active tab in current window | Tabs |
| 2 | "Open YouTube" | Create new tab with URL, register ownership | Tabs |
| 3 | "Close this tab" | Close active tab | Tabs |
| 4 | "List my open tabs" | Query all tabs, format by window/group | Tabs |
| 5 | "Focus YouTube tab" | Find tab matching "youtube", activate it | Tabs |
| 6 | "Go to my downloads" | Query recent downloads, show summary | Downloads |
| 7 | "Show me PDFs I downloaded this week" | Search downloads by type and time | Downloads |
| 8 | "Where did my download go?" | Show in folder for last completed download | Downloads |
| 9 | "Save this page" | Bookmark active tab URL | Bookmarks |
| 10 | "Save this page to my research folder" | Bookmark to specific folder | Bookmarks |
| 11 | "Find my bookmark about Python" | Search bookmarks by keyword | Bookmarks |
| 12 | "Show all my bookmarks" | Get bookmark tree, summarize by folder | Bookmarks |
| 13 | "What did I have open yesterday?" | Query recently closed sessions | Sessions |
| 14 | "Restore last session" | Restore most recently closed tab/window | Sessions |
| 15 | "Open my study workspace" | Create/find workspace, open pinned resources | Workspaces |
| 16 | "Create a workspace for project KIO" | Create tab group + window config | Workspaces |
| 17 | "Mute this tab" | Mute active tab | Tabs |
| 18 | "Unmute all tabs" | Query all tabs, unmute each | Tabs |
| 19 | "Refresh this page" | Reload active tab | Tabs |
| 20 | "Duplicate this tab" | Clone active tab | Tabs |
| 21 | "Open this link in a new tab" | (Context menu) Open link URL | Context Menus |
| 22 | "Save this link for later" | (Context menu) Add URL to reading list | Bookmarks |
| 23 | "Move this tab to my work window" | Move tab between windows | Windows |
| 24 | "Open a new window" | Create empty browser window | Windows |
| 25 | "Close this window" | Close current window | Windows |
| 26 | "Minimize all windows" | Minimize each window | Windows |
| 27 | "Restore my windows" | Restore minimized windows | Windows |
| 28 | "Tile my two windows side by side" | Position windows left/right | Windows |
| 29 | "Zoom in" | Zoom active tab 110% | Tabs |
| 30 | "Zoom to 100%" | Reset zoom on active tab | Tabs |

### Productivity (Scenarios 31-65)

| # | User Says | System Action | Domain |
|---|-----------|--------------|--------|
| 31 | "Sort my tabs by domain" | Query tabs, group by domain, reorder | Tabs |
| 32 | "Close all YouTube tabs" | Find + close all tabs matching domain | Tabs |
| 33 | "Close all tabs except this one" | Close all tabs except active | Tabs |
| 34 | "Close tabs from yesterday" | Query+close tabs opened before today | Tabs |
| 35 | "Discard inactive tabs" | Discard tabs not active in >1 hour | Tabs |
| 36 | "How much memory is Chrome using?" | Query system memory info | System |
| 37 | "Show me open tabs with video" | Filter tabs with audio/muted state | Tabs |
| 38 | "Pin this tab" | Pin active tab | Tabs |
| 39 | "Unpin this tab" | Unpin active tab | Tabs |
| 40 | "Add this tab to a new group called Research" | Create group, add active tab | TabGroups |
| 41 | "Move all code tabs to the Coding group" | Query code-domain tabs, group them | TabGroups |
| 42 | "Color the Research group blue" | Update group color | TabGroups |
| 43 | "Rename this tab group" | Update group name | TabGroups |
| 44 | "Show my tab groups" | Query all groups, summarize | TabGroups |
| 45 | "Ungroup these tabs" | Remove tabs from group | TabGroups |
| 46 | "What's in my reading list?" | Query reading list | Reading List |
| 47 | "Save this for tonight" | Add URL to reading queue with priority | Reading List |
| 48 | "Mark this as read" | Remove from reading list | Reading List |
| 49 | "Clear my reading list" | Remove all read items | Reading List |
| 50 | "Cancel this download" | Find and cancel active download | Downloads |
| 51 | "Pause all downloads" | Pause all active downloads | Downloads |
| 52 | "Resume downloads" | Resume paused downloads | Downloads |
| 53 | "Open this downloaded file" | Open completed download | Downloads |
| 54 | "Delete this download from history" | Erase download record | Downloads |
| 55 | "Show my recent downloads from YouTube" | Search downloads by domain | Downloads |
| 56 | "Remove duplicate bookmarks" | Find+remove duplicate bookmarks | Bookmarks |
| 57 | "Organize my bookmarks by domain" | Sort bookmarks into domain folders | Bookmarks |
| 58 | "Export my bookmarks" | Generate markdown/JSON of bookmarks | Bookmarks |
| 59 | "Find expired bookmarks" | Check bookmark URLs for 404s | Bookmarks |
| 60 | "Show me what I downloaded last month" | Query downloads by date range | Downloads |
| 61 | "What pages do I have open about AI?" | Search tab titles/URLs for "AI" | Tabs |
| 62 | "Group all my work tabs" | Heuristic group by domain patterns | TabGroups |
| 63 | "Count my open tabs" | Count and return number | Tabs |
| 64 | "Show only pinned tabs" | Filter by pinned status | Tabs |
| 65 | "Find the tab with the spreadsheet" | Search tabs by title "spreadsheet" | Tabs |

### Power User (Scenarios 66-85)

| # | User Says | System Action | Domain |
|---|-----------|--------------|--------|
| 66 | "Open my research workspace" | Restore named workspace | Workspaces |
| 67 | "Save this workspace as 'Research'" | Persist workspace config | Workspaces |
| 68 | "Switch to my coding workspace" | Activate different workspace | Workspaces |
| 69 | "Close all workspaces except coding" | Close non-coding windows/groups | Workspaces |
| 70 | "Share this workspace" | Export workspace as URL collection | Workspaces |
| 71 | "Continue my research from yesterday" | Restore yesterday's session in workspace | Sessions |
| 72 | "Save this session as 'QEC Research'" | Name current session for later restore | Sessions |
| 73 | "Merge today's session into my main workspace" | Combine workspaces | Sessions |
| 74 | "Help me study this article" | Parse+summarize current page | Reading |
| 75 | "Save this research paper to my knowledge base" | Extract+save page metadata | Knowledge |
| 76 | "Take a note on this page" | Capture user note with URL reference | Knowledge |
| 77 | "Show me everything I saved about transformers" | Search knowledge base | Knowledge |
| 78 | "Focus mode for 45 minutes" | Minimize distractions, set timer | Focus |
| 79 | "Block social media during focus" | Define distraction list | Focus |
| 80 | "End focus mode" | Restore closed/muted tabs | Focus |
| 81 | "Preload the next article" | Warmup tab for known URL | Tabs |
| 82 | "Open all bookmarks in this folder" | Bulk open bookmarks | Bookmarks |
| 83 | "Categorize my bookmarks" | Auto-tag bookmarks by domain | Bookmarks |
| 84 | "Find dead links in my bookmarks" | Batch-check bookmark URLs | Bookmarks |
| 85 | "Archive old bookmarks" | Move untouched bookmarks to archive | Bookmarks |

### Advanced (Scenarios 86-100)

| # | User Says | System Action | Domain |
|---|-----------|--------------|--------|
| 86 | "Type 'kio youtube' in the address bar" | Omnibox → open YouTube | Omnibox |
| 87 | "Add a KIO button to right-click links" | Create context menu item | Context Menus |
| 88 | "Set a keyboard shortcut to ask KIO" | Register command hotkey | Commands |
| 89 | "Show KIO icon count of open tabs" | Set badge text to tab count | Action |
| 90 | "Remind me about this page in 30 minutes" | Schedule alarm + notification | Alarms |
| 91 | "Open KIO in the side panel" | Open side panel | SidePanel |
| 92 | "Read the content of the last article I saved" | Offscreen parse + relay | Offscreen |
| 93 | "Summarize the page I'm on" | Capture+parse+summarize | Knowledge |
| 94 | "What's the word count of this page?" | Offscreen DOM parse | Offscreen |
| 95 | "Find all mentions of 'KIO' in my open tabs" | Search tab content | Tabs |
| 96 | "Save this selection to my notes" | (Context menu) Save selected text | Context Menus |
| 97 | "Translate this page" | Navigate to translate URL | Tabs |
| 98 | "Show me my top 10 most visited domains" | Query history (with confirmation) | History |
| 99 | "Restore the tab I just accidentally closed" | Restore most recent session | Sessions |
| 100 | "Open all my bookmarked research papers" | Bulk open from folder | Bookmarks |
| 101 | "Tell me if anyone messages me while I'm away" | Idle-based notification relay | Idle |
| 102 | "Keep Chrome awake while I download this" | Power keep-awake during active download | Power |
| 103 | "Show extension diagnostics" | Display system + runtime info | System |
| 104 | "Reset all permissions" | Remove optional permissions | Permissions |
| 105 | "Show my available browser extensions" | Query management API | Permissions |

---

## 5. Architecture Compliance Review

### 5.1 Safe — Fully Compatible with KIO Architecture v1.1

These capabilities involve **metadata-only** operations, explicit user triggers, no content observation, and no autonomous behavior.

| # | Capability | Justification |
|---|-----------|---------------|
| 1 | Tab query (title, URL, status) | Metadata only. User asks, KIO answers. |
| 2 | Tab create | Explicit user command: "open X" |
| 3 | Tab remove | Explicit user command: "close X" |
| 4 | Tab update (navigate) | Explicit: "go to X in this tab" |
| 5 | Tab activate (focus) | Explicit: "focus X" — already implemented |
| 6 | Tab mute/unmute | Explicit: "mute this" |
| 7 | Tab reload | Explicit: "refresh" |
| 8 | Tab duplicate | Explicit: "duplicate" |
| 9 | Tab highlight | Explicit: "select these tabs" |
| 10 | Tab move | Explicit tab rearrangement |
| 11 | Tab detect language | Explicit query about page |
| 12 | Tab discard | Explicit: "free up memory" |
| 13 | Tab go forward/back | Explicit: "go back" |
| 14 | Tab zoom | Explicit: "zoom in" |
| 15 | Tab pin/unpin | Explicit: "pin this tab" |
| 16 | Tab group CRUD | Explicit: "create group", "add to group" |
| 17 | Tab ungroup | Explicit: "ungroup these" |
| 18 | Tab group query | Explicit: "show my groups" |
| 19 | Tab group events | Notification when group changes |
| 20 | Window create/close/focus | Explicit window management |
| 21 | Window minimize/maximize/fullscreen | Explicit: "minimize all" |
| 22 | Window query | Explicit: "what windows are open?" |
| 23 | Window bounds | Explicit: "tile windows" |
| 24 | Window events | Awareness when explicitly queried |
| 25 | Download query | Explicit: "show my downloads" |
| 26 | Download cancel/pause/resume | Explicit download management |
| 27 | Download open | Explicit: "open this file" |
| 28 | Download show in folder | Explicit: "where is my download" |
| 29 | Download remove from history | Explicit: "remove from history" |
| 30 | Download events | Notifications for user-initiated downloads |
| 31 | Bookmark search | Explicit: "find bookmark" |
| 32 | Bookmark create | Explicit: "save this page" |
| 33 | Bookmark remove | Explicit: "delete bookmark" |
| 34 | Bookmark move | Explicit: "move to folder" |
| 35 | Bookmark tree | Explicit: "show my bookmarks" |
| 36 | Bookmark events | Awareness when asked |
| 37 | Session query (recently closed) | Explicit: "what did I have open" |
| 38 | Session restore | Explicit: "restore session" |
| 39 | Notification create | Explicit relay to user |
| 40 | Notification events | User clicking notification |
| 41 | Omnibox default suggestion | Explicit user typing keyword |
| 42 | Omnibox input entered | Explicit user selects suggestion |
| 43 | Context menu create | Explicit: "add right-click option" |
| 44 | Context menu onClicked | Explicit user click |
| 45 | Keyboard commands | Explicit shortcut registration |
| 46 | Side panel open/close | Explicit: "open side panel" |
| 47 | Storage local/session | Persistence for user data |
| 48 | Offscreen document | Controlled processing, no visibility |
| 49 | Alarm scheduling | Explicit: "remind me in 30 min" |
| 50 | Idle detection | Non-invasive, binary (active/away) |
| 51 | Power keep-awake | Explicit download protection |
| 52 | System diagnostics | Explicit: "show system info" |
| 53 | Runtime platform info | Non-sensitive metadata |
| 54 | Permission request/check | User-consent-gated |
| 55 | Action badge text/color | Status display only |
| 56 | Action popup/pages | UI element, no data collection |
| 57 | Reading list (native Chrome) | Explicit: "save for later" |
| 58 | Tab capture (visible, explicit) | ✅ **Safe ONLY if**: user says "capture this screen", single explicit capture, shown to user before sending, never automatic |

### 5.2 Conditional — Possible with Safeguards

These capabilities provide value but require explicit KIO-compliant guardrails.

| # | Capability | Safeguards Required |
|---|-----------|---------------------|
| 1 | Tab warmup | Only when user explicitly says "preload this link". Never prefetch based on prediction. |
| 2 | Navigation events (onCompleted) | Only for explicit user queries. "Tell me when this page loads." Never passive logging. |
| 3 | Navigation history state (SPA) | Only for user-cued awareness. "Is this the same page?" |
| 4 | Search query via `search.query()` | Only with explicit user keyword. Search terms go to default engine — must inform user. |
| 5 | CSS injection | Only when user says "make this site dark". Single-site, reversible, explicit. |
| 6 | Bookmark tree (full) | Require explicit consent: "KIO needs to read your bookmarks to organize them. Allow?" |
| 7 | Session all devices | Never. Session query is local-only. Cross-device sessions require user consent + confirmation. |
| 8 | History delete | Only on explicit user command. Never auto-delete. "Delete history for site.com" |
| 9 | WebRequest (observation) | Only for explicit single-interception use. Never blanket monitoring. |
| 10 | Tab capture (visible) | Must show preview before sending to LLM. "Here's what I captured. Send to KIO?" |
| 11 | Offscreen page full parse | Only on explicit: "summarize this link". One URL at a time. No batch/background. |
| 12 | Cross-extension messaging | Only for explicit interop features. User must enable each bridge. |

### 5.3 Unsafe — Violates KIO Architecture v1.1

These capabilities conflict with the explicit, deterministic, no-surveillance constraints.

| # | Capability | Why Unsafe |
|---|-----------|------------|
| 1 | History search (full) | **Surveillance risk.** Full browsing history is a complete record of user activity. Automatically accessible history violates KIO's "no uncontrolled observers" constraint. |
| 2 | History getVisits | **Timeline surveillance.** Visit timestamps reveal when and how often user visits sites. Creates implicit profiling capability. |
| 3 | History events (onVisited) | **Passive tracking.** Every page visit would notify KIO without user intent. Direct surveillance violation. |
| 4 | Content script injection | **Arbitrary JS execution.** Injecting JavaScript into web pages grants access to page content, DOM, cookies, and user input. Violates "no arbitrary JavaScript execution". |
| 5 | Scripting executeScript | Same as above — arbitrary code execution in page context. |
| 6 | Content script (manifest) | Persistent injection into every page — passive observation of all browsing. |
| 7 | WebRequest blocking | **Network surveillance.** Intercepting network requests reveals all URLs, headers, and traffic patterns. |
| 8 | Debugger attach | **Full browser control.** DevTools protocol grants arbitrary access to page JS, network, DOM, storage. |
| 9 | Automation / accessibility tree | **Full page reading.** Accessibility tree contains all visible text and structure — essentially screen-reading every page. |
| 10 | Proxy settings | **Traffic redirection.** Setting a proxy routes ALL browser traffic through a controlled endpoint. |
| 11 | Clipboard read | **Data exfiltration.** Reading clipboard without explicit user action captures sensitive copied data. |
| 12 | Sync storage | **Data sync to Google.** KIO data should not sync through Google's infrastructure without explicit policy. |
| 13 | Session getDevices (cross-device) | **Cross-device surveillance.** Reveals browsing activity on all user devices. Too broad. |
| 14 | Screen/desktop capture | **Full screen surveillance.** Captures all monitor content including non-browser apps. |
| 15 | File reader (local files) | **File system access.** Reading local files creates arbitrary read capability. |
| 16 | Network diagnostics | **Network profiling.** Reveals network topology, latency, connectivity patterns. |
| 17 | User scripts | **Uncontrolled code execution.** Third-party scripts bypass KIO's deterministic model. |
| 18 | Download acceptDanger | **Safety bypass.** Accepting dangerous downloads bypasses Chrome's security warnings. |
| 19 | Enterprise device attributes | **Device fingerprinting.** Reveals hardware identity, serial numbers. |
| 20 | Enterprise networking | **Network fingerprinting.** Hostname, IP, domain information. |
| 21 | Autonomous browsing | **Agency violation.** KIO navigating without explicit user intent violates fundamental design constraint. |
| 22 | Agentic research loops | **Uncontrolled iteration.** "Research X and report back" creates unknown-scope action sequences. |
| 23 | Form filling | **Data exposure.** Filling forms requires access to PII, credentials, payment data. |
| 24 | CAPTCHA solving | **Adversarial automation.** Bypassing human-verification systems. |
| 25 | Credential extraction | **Password theft.** Accessing saved passwords violates core security boundary. |

---

## 6. Browser Connector Expansion Roadmap

### 6.1 BC V1.1 — Highest-Value Additions (Next)

Target: First expansion after current freeze items.

| Feature | Why First | User Value | Complexity | RAM Impact | Risk |
|---------|-----------|-----------|------------|-----------|------|
| Active tab awareness | Trivial (single query), foundational for all context work | Critical | Very Low | None | None |
| Tab groups CRUD | Chrome-native workspace primitive | High | Low | None | None |
| Window query + management | Natural extension of tab commands | High | Low | None | None |
| Sessions (local) | "Restore last session" — consistently high-demand | High | Low | None | None |
| Download awareness | Query recent downloads — top user ask | High | Low | None | None |
| Tab mute/unmute | Trivially simple, consistently requested | Medium | Very Low | None | None |
| Tab refresh | One-line implementation | Medium | Very Low | None | None |
| Tab duplicate | One-line implementation | Medium | Very Low | None | None |
| Context menu "Ask KIO" | High visibility integration point | High | Low | None | None |
| Keyboard shortcut | Ctrl+Shift+K to trigger KIO | High | Very Low | None | None |
| Action badge (tab count) | At-a-glance awareness | Low | Very Low | None | None |
| Tab discard | Memory management | Medium | Low | None | None |

**Total V1.1**: 12 features, very low complexity, zero new dependencies.

### 6.2 BC V2 — Major Capability Expansion

Target: Comprehensive tab/window/session management.

| Feature | Value | Complexity | RAM |
|---------|-------|-----------|------|
| Workspace system (save/restore named workspaces) | Highest value | Medium (~200 lines) | ~1MB per workspace config |
| Bookmark intelligence (search + create + organize) | High | Medium | ~0.1MB |
| Session query by time (today, yesterday, this week) | High | Low | None |
| Session naming + search | High | Medium | ~0.5MB for named session store |
| Download categorization (by type/domain/date) | High | Low | None |
| Notification relay (download complete, tab state) | Medium | Low | None |
| Side panel KIO integration | High | Medium | ~10MB (Chrome side panel) |
| Omnibox "kio" keyword | Medium | Low | None |
| Tab capture (explicit, confirmed) | High | Medium | ~5MB per capture |
| Offscreen page parsing (single URL) | High | Low | ~10MB (offscreen doc) |
| Tab zoom control | Low | Very Low | None |
| Reading list integration | Medium | Low | None |
| Window tile/arrange | Medium | Low | None |
| Scheduled reminders (alarms + notifications) | Medium | Low | None |
| Pin/unpin tabs | Low | Very Low | None |
| Idle-aware behavior | Low | Low | None |

**Total V2**: 16 features, moderate complexity, ~2 new capabilities requiring permission grants.

### 6.3 BC V3 — Deep Browser Integration

Target: Knowledge capture, study/research workflows.

| Feature | Value | Complexity | RAM |
|---------|-------|-----------|------|
| Knowledge capture system | Highest | High (~500 lines across modules) | ~10MB for local knowledge store |
| Offscreen content extraction | High | Medium | ~10MB |
| Study workspace (article + notes + resources) | High | Medium | ~1MB |
| Research workspace (multi-session + bookmarks + PDF) | High | Medium | ~1MB |
| Focus mode (distraction blocking + timer) | Medium | Medium | ~0.5MB |
| Reading queue with priorities | Medium | Low | ~0.5MB |
| Bookmark auto-organization | Medium | Medium | None |
| Bookmark dead-link detection | Low | Low | None |
| Session merge/combine | Medium | Medium | None |
| Tab group auto-naming by domain | Low | Low | None |
| Download auto-organization | Low | Low | None |

**Total V3**: 11 features, higher complexity, deeper integration with KIO knowledge systems.

### 6.4 BC V4 — Maximum Practical Capability

Target: Complete Browser OS vision.

| Feature | Value | Complexity | RAM |
|---------|-------|-----------|------|
| Full workspace system (save/restore/switch/share) | Highest | High | ~2MB |
| Cross-session knowledge graph | High | Very High | ~50MB+ |
| Research export (bibliography, markdown, PDF) | High | Medium | ~1MB |
| Study session with AI tutoring context | High | High | ~10MB |
| Browser resource management dashboard | Medium | Medium | ~1MB |
| Extension diagnostics + health monitoring | Low | Low | None |
| Multi-window workspace orchestrator | High | High | ~2MB |
| Offscreen batch processing (queued) | Medium | Medium | ~20MB |
| User action history (local, opt-in, user-controlled) | Medium | High | ~5MB |
| Permission manager (progressive grant) | Medium | Medium | None |

**Total V4**: 10 features, highest complexity, significant new infrastructure.

### 6.5 Cumulative Roadmap

```
Phase      Features   Total Features   RAM (estimated)   User Value
──────────────────────────────────────────────────────────────────
Current:  7 (open,   7                 5MB               Baseline
          close,
          focus, list,
          auth, mock,
          WS transport)

V1.1:     +12        19                5MB + negligible  2x current
V2:       +16        35                5MB + ~15MB       5x current
V3:       +11        46                5MB + ~25MB       10x current
V4:       +10        56                5MB + ~50MB       15x current
```

**Key note**: The connector itself stays ~5MB throughout. Additional RAM is for:
- Offscreen documents (temporary, per-parse)
- Knowledge store (persistent, user-controlled)
- Side panel (shared Chrome process)
- Workspace configurations (negligible JSON)

---

## 7. Hard Rejection List

Capabilities that must **never** be implemented in Browser Connector, regardless of value.

### Permanently Rejected

| # | Capability | Rejection Rationale | KIO Principle Violated |
|---|-----------|---------------------|----------------------|
| 1 | Autonomous browsing | KIO cannot navigate without explicit user command. "Browse the web and find X" is an agent loop. | No autonomous agents |
| 2 | Agentic research loops | "Research quantum computing and summarize" creates an unbounded action sequence with unknown scope and duration. | No autonomous agents; No AGI drift |
| 3 | History-based passive learning | Mining browsing history to learn user preferences without explicit consent. | No surveillance behavior; No uncontrolled observers |
| 4 | Content script auto-injection | Automatically injecting JS into every page to observe content. | No uncontrolled observers; No surveillance behavior |
| 5 | WebRequest blanket monitoring | Observing all network requests to analyze user browsing patterns. | No surveillance behavior |
| 6 | Debugger protocol access | DevTools-level access grants full control over page execution context. | No hidden browser instances; No arbitrary JavaScript execution |
| 7 | Form autofill | Storing and auto-filling forms accesses PII, addresses, payment data. | No arbitrary data access (KIO is not a password manager) |
| 8 | Credential management | Reading/writing saved passwords bypasses Chrome's password manager boundary. | No credential extraction |
| 9 | CAPTCHA solving | Automating human-verification challenges is adversarial to web platforms. | No agentic automation |
| 10 | Clipboard auto-read | Reading clipboard content without explicit user action and confirmation. | No surveillance behavior |
| 11 | Proxy configuration | Routing all browser traffic through a controlled proxy creates a Man-in-the-Middle capability. | No hidden browser instances |
| 12 | Screen/desktop capture | Capturing non-browser application content violates user's desktop privacy. | No surveillance behavior |
| 13 | Background page scanning | Periodically scanning tabs/open pages for changes without user request. | No uncontrolled observers |
| 14 | User behavior profiling | Building behavioral profiles from browsing patterns, visit times, or content preferences. | No surveillance behavior; No AGI drift |
| 15 | Auto-accept dangerous downloads | Bypassing Chrome's Safe Browsing warnings compromises system security. | No autonomous agents (security boundary) |
| 16 | Native file system scan | Reading/writing arbitrary local files outside browser storage. | No hidden browser instances |
| 17 | Microphone/camera access | Accessing hardware without explicit browser-level permission (beyond KIO). | No uncontrolled observers |
| 18 | Network proxy bypass detection | Actively probing user's network configuration. | No surveillance behavior |
| 19 | Browser fingerprinting | Collecting browser/device fingerprint data. | No surveillance behavior |
| 20 | Extension management | Disabling/enabling other extensions without user consent. | No autonomous agents |
| 21 | Tab group auto-classification | Automatically categorizing tabs without user direction. | No AGI drift (creates implicit user model) |
| 22 | "Read my mind" features | Predicting user intent from browsing patterns. | No AGI drift; No autonomous agents |
| 23 | Social media auto-posting | Posting content to social platforms without explicit user action. | No autonomous agents |
| 24 | Auto-save all pages | Automatically saving every page visited. | No surveillance behavior; No uncontrolled observers |
| 25 | Cross-origin data extraction | Extracting data from one origin and sending it to another. | No arbitrary JavaScript execution |

### Design Boundary Principles

```
The Hard Rejection List follows from first principles:

1. USER TRIGGERED   → No action without explicit user intent
2. NO OBSERVERS     → No passive monitoring of user behavior
3. NO AGENCY        → No autonomous decisions or action sequences
4. NO SURVEILLANCE  → No collection of user activity data
5. EXPLICIT INTENT  → Every capability maps 1:1 to a user command
6. DETERMINISTIC    → Same input → same output, always
7. TRANSPARENT      → User can see exactly what KIO knows and does
```

---

## 8. Final Strategic Recommendation

### 8.1 The Final Vision

**Browser Connector should not attempt to be all browsers. It should be the best intentional browser operator.**

The highest-value connector is not one that mines every API. It is one that:

1. **Knows what the user is doing** (active tab awareness) — only when asked
2. **Organizes what the user has** (tabs, windows, groups, workspaces) — on command
3. **Remembers what the user saved** (bookmarks, reading list, sessions) — explicitly
4. **Tracks what the user downloaded** (downloads) — when queried
5. **Helps the user focus** (mute, discard, workspace) — on demand
6. **Captures what the user wants saved** (knowledge capture) — one-shot, explicit

It does NOT:
- Watch what the user does
- Predict what the user wants
- Act without being told
- Learn from passive observation
- Execute unrestricted code

### 8.2 Final Capability Map

```
SAFE (always available):    56 capabilities
CONDITIONAL (with guard):   12 capabilities
UNSAFE (never):             25 capabilities
                             ─────
Total discovered:           93 capabilities
Keep (Safe + Conditional):  68 capabilities
Reject (Unsafe):            25 capabilities
```

### 8.3 Final Boundaries

| Boundary | Line | Why |
|----------|------|-----|
| **Observation** | Query only, never subscribe | User asks → KIO queries. No background listeners. |
| **Navigation** | Must be explicit | Every URL opened or tab navigated requires a direct user command. |
| **Content** | Must be captured explicitly | No DOM scraping, no content scripts. "Save this page" = one-shot offscreen parse. |
| **History** | Query only, never mine | User can ask "did I visit site.com?" but KIO never reads history without a specific query. |
| **Storage** | Local only, user-controlled | All persistent data in `storage.local` or KIO's own database. No cloud sync without explicit export. |
| **Execution** | No arbitrary JS | CSS injection for readability only. No `executeScript`. |
| **Network** | KIO-initiated only | KIO opens URLs, downloads files, searches. Never intercepts user network traffic. |
| **Permissions** | Progressive, explicit | Each API group requested when first needed. User sees: "KIO needs bookmark access to save this page. Allow?" |

### 8.4 Recommended Roadmap

```
IMMEDIATE (V1.1)
  ┌─ Active tab awareness
  ├─ Tab groups CRUD
  ├─ Window query + management
  ├─ Sessions (local)
  ├─ Download awareness
  ├─ Tab mute/unmute
  ├─ Tab refresh
  ├─ Tab duplicate
  ├─ Context menu "Ask KIO"
  ├─ Keyboard shortcut
  └─ Action badge

SHORT-TERM (V2)
  ┌─ Workspace system
  ├─ Bookmark intelligence
  ├─ Session query by time
  ├─ Notification relay
  ├─ Side panel integration
  ├─ Omnibox keyword
  ├─ Tab capture (explicit)
  ├─ Offscreen parsing
  └─ Reading list

MEDIUM-TERM (V3)
  ┌─ Knowledge capture system
  ├─ Study workspace
  ├─ Research workspace
  ├─ Focus mode
  ├─ Bookmark automation
  └─ Reading queue

LONG-TERM (V4)
  ┌─ Full workspace orchestrator
  ├─ Cross-session knowledge graph
  ├─ Research export
  └─ Permission manager
```

### 8.5 Top 20 Features for Real-World Impact

Ranked by a composite score of: user value �- implementation simplicity �- architecture compatibility.

| Rank | Feature | Phase | Why Top 20 |
|------|---------|-------|-----------|
| **1** | **Active tab awareness** | V1.1 | Trivial implementation. Foundational for all contextual features. "What am I looking at?" is the most asked question. |
| **2** | **Tab groups** | V1.1 | Chrome-native workspace primitive. Enables all organizational features downstream. ~5 lines of JS per operation. |
| **3** | **Window management** | V1.1 | Users have multiple windows. Query, focus, and arrange them on command. Low complexity, high visibility. |
| **4** | **Session restore** | V1.1 | "I accidentally closed that tab" — consistently the most common user regret. One Chrome API call. |
| **5** | **Download query** | V1.1 | "Where did my download go?" — every user, every week. Download search by type/date/domain is invaluable. |
| **6** | **Tab mute** | V1.1 | Trivial. Users love muting autoplay video tabs. |
| **7** | **Context menu** | V1.1 | Highest visibility integration point. Right-click → "Ask KIO" puts KIO everywhere the user already works. |
| **8** | **Keyboard shortcut** | V1.1 | Ctrl+Shift+K for "ask KIO" from any tab. Power user essential. |
| **9** | **Workspace system** | V2 | Most transformative feature. Save/restore named workspaces (Research, Coding, Personal). Changes how users think about their browser. |
| **10** | **Bookmark intelligence** | V2 | "Find my bookmark about X" — every user has too many bookmarks and can't find them. Search + organize + save. |
| **11** | **Tab capture (explicit)** | V2 | "What's on this page?" — send visible area to KIO for analysis. Must show preview before sending. |
| **12** | **Offscreen parsing** | V2 | "Summarize this link" without opening a new tab. One-shot, user-triggered. |
| **13** | **Notification relay** | V2 | Download complete, tab loaded, reminder triggered. Meaningful system notifications. |
| **14** | **Side panel** | V2 | Persistent KIO sidebar while browsing. Contextual assistant without tab switching. |
| **15** | **Reading list** | V2 | "Save for later" with Chrome's native reading list. Cross-device reading queue. |
| **16** | **Knowledge capture** | V3 | "Save this page to my knowledge base" — extract metadata, store locally, make searchable. |
| **17** | **Study workspace** | V3 | "Help me study this article" — create focused study environment with notes. |
| **18** | **Focus mode** | V3 | "Focus for 45 minutes" — mute distractions, close social media, set timer. |
| **19** | **Research workspace** | V3 | "Continue my research" — multi-session workspace with bookmarks, PDFs, notes. |
| **20** | **Permission manager** | V4 | Progressive permission model. "KIO needs tab group access to create your workspace. Allow once / Always?" |

### 8.6 Strategic Principle

**Build the most capable browser operator in existence — while making every capability 100% transparent, 100% user-triggered, and 100% compliant.**

Do not compromise on architecture. The constraint is not a limitation. It is the reason users will trust KIO with their browser activity.

The browser is the user's window to the internet. KIO should be the curtain puller — not the peephole.

---

*End of Capability Expansion Architecture Document*
