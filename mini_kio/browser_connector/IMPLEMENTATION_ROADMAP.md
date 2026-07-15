# Browser Connector — Implementation Roadmap

> **Lead Architect**: KIO Architecture v1.1
> **Date**: 2026-06-05
> **Based on**: `CAPABILITY_EXPANSION.md` — capability surface map
> **Purpose**: Convert discovered capability space into actionable implementation roadmap
> **Runtime target**: i3-1315U, 8GB RAM, Intel UHD — Browser Connector must remain lightweight

---

## Table of Contents

1. [Re-Ranked Capabilities](#1-re-ranked-capabilities)
2. [Magical Capabilities](#2-magical-capabilities)
3. [Personal Operating Layer Design](#3-personal-operating-layer-design)
4. [Feature Clusters](#4-feature-clusters)
5. [Ultimate Roadmap (V1.1–V5)](#5-ultimate-roadmap)
6. [Browser Memory Opportunities](#6-browser-memory-opportunities)
7. [Browser Connector End State](#7-browser-connector-end-state)
8. [Final Strategic Recommendation](#8-final-strategic-recommendation)

---

## 1. Re-Ranked Capabilities

All capabilities re-evaluated ignoring implementation effort. Ranked solely by user value �- daily usefulness �- long-term value �- assistant usefulness �- architecture fit.

### Top 10

| Rank | Capability | Domain | Value Rationale |
|------|-----------|--------|----------------|
| 1 | **Active tab awareness** | Tabs | Foundational. Everything contextual starts with "what tab am I on?" Most asked question. Enables all downstream intelligence. |
| 2 | **Workspace management** | Workspaces | Highest multiplicative value. Save/restore/switch entire browser configurations. Changes how users think about browsing. |
| 3 | **Session restore + query** | Sessions | "I closed something" is universal. Session query by time + one-command restore is the most consistently valuable browser feature. |
| 4 | **Tab groups** | TabGroups | Chrome-native workspace primitive. Create, name, color, populate groups. Direct organizational value every time user has >3 tabs. |
| 5 | **Bookmark intelligence** | Bookmarks | Every user has bookmarks; almost nobody organizes them. Search, save, organize, deduplicate. Permanent value. |
| 6 | **Download awareness** | Downloads | Weekly use case for every user. "Where did my download go? Show recent PDFs." Universal, frequent, high satisfaction. |
| 7 | **Reading queue** | Reading | "Save for later" with progress tracking. Cross-session value. User saves pages intending to read them but never does — KIO bridges the gap. |
| 8 | **Knowledge capture** | Knowledge | "Save this page to my knowledge base." One-shot explicit capture with metadata extraction. Bridges browser and KIO memory permanently. |
| 9 | **Contextual tab nav** | Tabs | "Find the YouTube tab" vs opening another one. Smart tab resolution across all windows. Saves tabs, not creates them. |
| 10 | **Focus mode** | Focus | Distraction blocking + timer + workspace isolation. Users struggle with focus daily. KIO as productivity tool, not just assistant. |

### Top 25

| Rank | Capability | Domain | Rationale |
|------|-----------|--------|-----------|
| 11 | **Window management** | Windows | Query, focus, arrange, create, close windows. Multi-window users need orchestration. |
| 12 | **Tab capture (explicit)** | Tabs | "What's on this page?" — explicit one-shot screenshot with user confirmation. |
| 13 | **Offscreen parsing** | Offscreen | "Summarize this link" without opening tab. Parse full page content invisibly. |
| 14 | **Context menu integration** | ContextMenus | Right-click → "Ask KIO". Highest-exposure KIO touchpoint. Puts KIO everywhere. |
| 15 | **Study workspace** | Workspaces | Article + notes + resources. Tool-specific, but deeply valuable for learning users. |
| 16 | **Research workspace** | Workspaces | Multi-session research with bookmarks, PDFs, notes. Academic/professional power use. |
| 17 | **Tab mute** | Tabs | Trivially simple, requested daily. "Mute this tab with video." |
| 18 | **Tab discard** | Tabs | "Free up memory" — explicit memory reclamation. Valuable on 8GB machines. |
| 19 | **Session naming** | Sessions | "Save this session as 'Research June 5'". Persistent named browsing states. |
| 20 | **Side panel** | SidePanel | Persistent KIO while browsing. Foundation for continuous assistant presence. |
| 21 | **Keyboard shortcut** | Commands | Ctrl+Shift+K to trigger KIO. Power user essential. Daily use. |
| 22 | **Notification relay** | Notifications | Download complete, tab loaded, reminder triggered. Meaningful system notifications. |
| 23 | **Reading progress** | Reading | "Continue reading 'The Future of AI'" — resume from last position. |
| 24 | **Bookmark deduplication** | Bookmarks | High-value cleanup. Most users have duplicate bookmarks. |
| 25 | **Window tile/arrange** | Windows | "Tile two windows side by side." Explicit productivity improvement. |

### Top 50

| Rank | Capability | Domain |
|------|-----------|--------|
| 26 | **Session merge** | Sessions |
| 27 | **Tab refresh** | Tabs |
| 28 | **Tab duplicate** | Tabs |
| 29 | **Tab pin/unpin** | Tabs |
| 30 | **Tab group auto-name** | TabGroups |
| 31 | **Bookmark auto-tag** | Bookmarks |
| 32 | **Download type filter** | Downloads |
| 33 | **Download open** | Downloads |
| 34 | **Download show in folder** | Downloads |
| 35 | **Download cancel** | Downloads |
| 36 | **Reading list clear** | Reading |
| 37 | **Bulk bookmark open** | Bookmarks |
| 38 | **Bookmark dead-link check** | Bookmarks |
| 39 | **Omnibox integration** | Omnibox |
| 40 | **Action badge** | Action |
| 41 | **Idle-aware behavior** | Idle |
| 42 | **Alarm reminders** | Alarms |
| 43 | **Tab zoom** | Tabs |
| 44 | **Tab language detection** | Tabs |
| 45 | **Tab highlight** | Tabs |
| 46 | **Offscreen batch parse** | Offscreen |
| 47 | **Permission progressive** | Permissions |
| 48 | **Tab move between windows** | Tabs |
| 49 | **CSS readability injection** | Scripting |
| 50 | **Tab goBack/goForward** | Tabs |

---

## 2. Magical Capabilities

"What would make users say 'Wow, KIO actually understands my browser'?"

### Tier 1 — Instant Magic

| # | Capability | Why Magical | Anticipated User Reaction |
|---|-----------|-------------|--------------------------|
| 1 | **Workspace switch** | "Switch to my research workspace" — instant reconfiguration of windows, tabs, groups, and pinned resources. The user's entire context shifts with one command. | *"It remembered my exact setup from yesterday."* |
| 2 | **Active tab awareness** | "Help me with this article" — KIO already knows the URL, title, and can parse the page. No explanation needed. | *"How did you know what I was looking at?"* |
| 3 | **Session time travel** | "What did I have open yesterday afternoon?" — query browsing state by time. | *"I was looking for that tab for 10 minutes before I asked."* |
| 4 | **One-shot knowledge capture** | "Save this paper" — KIO captures URL, title, metadata, and key content. Permanent. Searchable. | *"It actually saved the full paper, not just a link."* |
| 5 | **Reading queue cross-session** | "What's in my reading list?" — articles saved across days, with progress tracking. | *"I saved that three weeks ago! I forgot about it."* |

### Tier 2 — Deep Utility

| # | Capability | Why Magical | Anticipated User Reaction |
|---|-----------|-------------|--------------------------|
| 6 | **Contextual tab resolution** | "Take me to the YouTube tab" — KIO finds the right tab across all windows instead of opening a new one. | *"It found my tab without me even knowing which window it was in."* |
| 7 | **Focus mode** | "Focus for 45 minutes" — tabs mute, social media close, timer starts. Environment transforms. | *"This is better than any focus app I've used."* |
| 8 | **Tab group intelligence** | "Group all my research tabs" — KIO creates named, colored groups from domain analysis. | *"It organized my chaos instantly."* |
| 9 | **Study workspace** | "Help me study this" — article parsed, key terms extracted, workspace created with related resources. | *"It set up my entire study environment in one command."* |
| 10 | **Download retrieval** | "Find that PDF I downloaded last week" — search by type, time, and source domain. | *"I didn't even remember the filename."* |

### Tier 3 — Power User Magic

| # | Capability | Why Magical |
|---|-----------|-------------|
| 11 | **Session naming + restoration** | "Continue my research from yesterday" — restores exact state including scroll position. |
| 12 | **Cross-window tab orchestration** | "Move all work tabs to the work window" — intelligent tab redistribution. |
| 13 | **Bookmark auto-organization** | "Organize my bookmarks" — domain-based folder structure. |
| 14 | **Dead-link detection** | "Find broken bookmarks" — proactive cleanup. |
| 15 | **Research export** | "Export my research as a bibliography" — structured output from browsing. |

---

## 3. Personal Operating Layer Design

### 3.1 Workspace Manager

**Purpose**: Save, restore, and switch entire browser configurations.

**Responsibilities**:
- Save named workspace: window config + tab groups + pinned tabs + sessions
- Restore workspace: recreate window(s), populate groups, open pinned resources
- Switch workspace: save current state, restore target state
- List workspaces: query all saved workspace names
- Delete workspace
- Export workspace as URL collection

**Boundaries**:
- Workspace save is **explicit** — "Save this as my research workspace"
- Workspace switch is **explicit** — "Switch to my coding workspace"
- KIO never auto-saves workspace state
- Workspace does not include: page content, scroll position, form state, cookies

**Interactions**:
- Consumes: TabGroups API, Windows API, Tabs API
- Provides: named state to Session Manager for cross-session persistence
- Stores: workspace configs in `storage.local` as JSON

### 3.2 Session Manager

**Purpose**: Time-anchored session query, save, and restore.

**Responsibilities**:
- Query recently closed tabs/windows by time window
- Restore individual or batch closed tabs
- Name a session: "Save this as 'QEC Research'"
- Query named sessions
- Merge sessions: add tabs from one session to another
- Clean old sessions: delete sessions older than N days

**Boundaries**:
- Session query is **explicit** — "What did I have open yesterday?"
- Session save is **explicit** — "Save this session"
- No passive session logging
- Session data is ephemeral KIO memory, not Chrome sync

**Interactions**:
- Consumes: Sessions API (`getRecentlyClosed`, `restore`)
- Consumes: Workspace Manager for named sessions
- Stores: session names + timestamps in `storage.local`

### 3.3 Download Manager

**Purpose**: Query, filter, and manage browser downloads.

**Responsibilities**:
- Query downloads by: date range, file type, source domain, status, filename
- Group downloads by type, day, source
- Execute download actions: cancel, pause, resume, open, show in folder
- Notify on download completion
- Report download status

**Boundaries**:
- All queries are **explicit** — "Show my recent downloads"
- No passive download tracking beyond event subscription
- Download content is never read or inspected
- File paths are metadata, not content

**Interactions**:
- Consumes: Downloads API (`search`, `cancel`, `pause`, `resume`, `open`, `show`)
- Consumes: Notification API for completion alerts
- Provides: filtered download lists to user

### 3.4 Reading Manager

**Purpose**: Cross-session reading queue with progress tracking.

**Responsibilities**:
- Save page to reading queue: URL + title + metadata + timestamp
- Query reading queue: by domain, date, read/unread
- Mark as read / remove
- Track reading position (URL anchor or scroll position)
- Prioritize: "Save for tonight" / "Save for weekend"
- Clear read items

**Boundaries**:
- All saves are **explicit** — "Save this for later"
- Reading list is separate from browsing history
- Reading position tracking is opt-in per save
- KIO reads page metadata only when explicitly saving

**Interactions**:
- Consumes: Tabs API (active tab info), Offscreen API (metadata extraction)
- Stores: reading queue in `storage.local`
- Provides: filtered, prioritized reading list

### 3.5 Bookmark Manager

**Purpose**: Search, create, organize, and maintain bookmarks.

**Responsibilities**:
- Search bookmarks by keyword, domain, folder
- Create bookmark in specified folder
- Move/remove bookmarks
- Get bookmark tree, summarize by folder
- Find and remove duplicates
- Check for dead links
- Auto-tag by domain
- Export bookmarks as structured list

**Boundaries**:
- All actions are **explicit** — "Save this page to bookmarks"
- Bookmark tree is queried only when user asks
- No automatic re-organization without user command
- Dead-link check is user-triggered batch operation

**Interactions**:
- Consumes: Bookmarks API (`search`, `create`, `remove`, `getTree`, `getChildren`)
- Stores: nothing (uses native Chrome bookmark storage)
- Provides: organized, deduplicated, checked bookmark collections

### 3.6 Focus Manager

**Purpose**: Create distraction-free browsing environments.

**Responsibilities**:
- Enter focus mode: mute non-essential tabs, close distractions, set timer
- Define distraction domains: "YouTube, Twitter, Reddit are distractions"
- Exit focus mode: restore closed tabs, unmute, stop timer
- Workspace-specific focus: "Close personal tabs during work focus"
- Report focus session summary: "You focused for 45 minutes. Closed 3 tabs."

**Boundaries**:
- Focus mode is **explicit** — "Focus for 45 minutes"
- Distraction lists are **user-defined**
- Closed tabs during focus are restored on exit
- No automatic focus detection

**Interactions**:
- Consumes: Tabs API (mute, close), Windows API (minimize), Alarms API (timer)
- Stores: distraction lists, focus sessions in `storage.local`
- Provides: structured focus environments

### 3.7 Knowledge Capture Layer

**Purpose**: One-shot explicit page content capture for KIO's knowledge base.

**Responsibilities**:
- Capture active page: URL, title, metadata, extracted text
- Parse page content via offscreen document (no visible tab)
- Extract: headings, key terms, author, publication date
- Store in KIO knowledge base with source attribution
- Search captured knowledge
- Export knowledge entry

**Boundaries**:
- Every capture is **explicit** — "Save this page to my knowledge base"
- Content is processed in isolated offscreen document
- Captured content is stored in KIO's knowledge store, not browser storage
- No automatic page saving
- User can delete any captured entry

**Interactions**:
- Consumes: Tabs API (active tab info), Offscreen API (content extraction)
- Consumes: KIO's knowledge storage (external to connector)
- Stores: structured page data in knowledge base
- Provides: searchable, attributable knowledge entries

### 3.8 Manager Interaction Map

```
                    ┌──────────────────┐
                    │  USER COMMANDS   │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │  Workspace │ │  Session   │ │  Focus     │
      │  Manager   │�-�┤  Manager   │ │  Manager   │
      └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
            │              │              │
            ▼              ▼              ▼
      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │  TabGroups │ │  Sessions  │ │  Tabs API  │
      │  Windows   │ │  API       │ │  Alarms    │
      └────────────┘ └────────────┘ └────────────┘

      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │  Download  │ │  Reading   │ │  Bookmark  │
      │  Manager   │ │  Manager   │ │  Manager   │
      └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
            │              │              │
            ▼              ▼              ▼
      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │  Downloads │ │  Reading   │ │  Bookmarks │
      │  API       │ │  List +    │ │  API       │
      │            │ │  Storage   │ │            │
      └────────────┘ └────────────┘ └────────────┘

      ┌─────────────────────────────────────────┐
      │         Knowledge Capture Layer          │
      │  (spans: Offscreen API + KIO Knowledge)  │
      └─────────────────────────────────────────┘
```

---

## 4. Feature Clusters

### 4.1 Core Cluster

The foundation. All other clusters depend on these.

| Feature | Current | V1.1 |
|---------|---------|------|
| Open tab | ✅ | ✅ |
| Close tab | ✅ | ✅ |
| Focus tab | ✅ | ✅ |
| List tabs | ✅ | ✅ |
| Active tab awareness | ❌ | ✅ |
| Tab mute/unmute | ❌ | ✅ |
| Tab refresh | ❌ | ✅ |
| Tab duplicate | ❌ | ✅ |
| Tab pin/unpin | ❌ | ✅ |

**User value**: Baseline browsing control. Users use these daily.
**Dependencies**: Tabs API
**Runtime impact**: None (metadata operations only)

### 4.2 Navigation Cluster

Moving between and within tabs.

| Feature | Phase |
|---------|-------|
| Tab go forward/back | V2 |
| Tab reload (with cache bypass) | V2 |
| Tab warmup (explicit preload) | V3 |
| Tab zoom | V1.1 |

**User value**: Medium. Navigation is a native browser behavior; KIO supplements it.
**Dependencies**: Tabs API
**Runtime impact**: None

### 4.3 Window Cluster

Multi-window orchestration.

| Feature | Phase |
|---------|-------|
| Window query (all windows + tabs) | V1.1 |
| Window create/close | V1.1 |
| Window focus | V1.1 |
| Window minimize/maximize/fullscreen | V2 |
| Window tile/arrange | V2 |
| Window state restore | V3 |
| Move tabs between windows | V2 |

**User value**: High for multi-monitor and power users.
**Dependencies**: Windows API
**Runtime impact**: None

### 4.4 Tab Group Cluster

Chrome-native workspace primitives.

| Feature | Phase |
|---------|-------|
| Create group | V1.1 |
| Add tab to group | V1.1 |
| Remove tab from group | V1.1 |
| Rename group | V1.1 |
| Recolor group | V1.1 |
| Query groups | V1.1 |
| Ungroup all tabs | V2 |
| Auto-group by domain | V3 |

**User value**: Very high. Tab groups are the most underutilized powerful Chrome feature.
**Dependencies**: TabGroups API
**Runtime impact**: None

### 4.5 Session Cluster

Temporal browsing state.

| Feature | Phase |
|---------|-------|
| Query recently closed (single) | V1.1 |
| Restore last closed tab | V1.1 |
| Query by time window (today, yesterday, this week) | V2 |
| Name current session | V2 |
| Restore named session | V2 |
| Merge sessions | V3 |
| Session save as workspace | V3 |

**User value**: Very high. Universal use case: "I closed something I needed."
**Dependencies**: Sessions API
**Runtime impact**: ~0.5MB for named session store

### 4.6 Download Cluster

File download management.

| Feature | Phase |
|---------|-------|
| Query recent downloads | V1.1 |
| Filter by type (PDF, image, zip) | V1.1 |
| Filter by date range | V2 |
| Filter by source domain | V2 |
| Cancel active download | V1.1 |
| Pause/resume download | V2 |
| Open downloaded file | V1.1 |
| Show in folder | V1.1 |
| Remove from history | V2 |
| Notify on completion | V2 |

**User value**: High. Weekly use for every user.
**Dependencies**: Downloads API, Notifications API
**Runtime impact**: None (metadata operations)

### 4.7 Bookmark Cluster

Persistent URL management.

| Feature | Phase |
|---------|-------|
| Search bookmarks by keyword | V2 |
| Save to specific folder | V2 |
| Get bookmark tree | V2 |
| Remove bookmark | V2 |
| Find duplicates | V3 |
| Dead-link check | V3 |
| Auto-tag by domain | V3 |
| Export as list | V3 |

**User value**: High. Bookmarks are permanent; most users have hundreds of unorganized ones.
**Dependencies**: Bookmarks API
**Runtime impact**: None

### 4.8 Reading Cluster

Cross-session reading queue.

| Feature | Phase |
|---------|-------|
| Save to reading queue | V2 |
| Query reading queue | V2 |
| Set priority (tonight/weekend) | V2 |
| Mark as read | V2 |
| Clear read items | V2 |
| Reading progress tracking | V3 |
| Batch save current tabs | V3 |

**User value**: High. Addresses the "I'll read this later but never do" problem.
**Dependencies**: Storage API, Tabs API
**Runtime impact**: ~0.5MB for reading queue data

### 4.9 Focus Cluster

Distraction management.

| Feature | Phase |
|---------|-------|
| Enter focus mode | V3 |
| Exit focus mode | V3 |
| Define distraction domains | V3 |
| Focus timer | V3 |
| Workspace-specific focus | V3 |
| Focus session summary | V3 |

**User value**: High for productivity users. KIO as productivity tool.
**Dependencies**: Tabs API, Windows API, Alarms API
**Runtime impact**: ~0.5MB

### 4.10 Knowledge Cluster

Explicit page capture for KIO's knowledge base.

| Feature | Phase |
|---------|-------|
| Capture active page (URL + title + meta) | V3 |
| Offscreen full content extraction | V3 |
| Extract headings, key terms | V3 |
| Store in KIO knowledge base | V3 |
| Search captured knowledge | V4 |
| Delete captured entry | V3 |
| Export knowledge entry | V4 |

**User value**: Very high. Bridges browser activity to permanent KIO memory.
**Dependencies**: Offscreen API, KIO knowledge storage
**Runtime impact**: ~10MB per offscreen parse (temporary)

### 4.11 Search Cluster

Browser-integrated search.

| Feature | Phase |
|---------|-------|
| Bookmark search | V2 |
| Download search | V2 |
| Tab search (across all windows) | V1.1 |
| Session search (by time) | V2 |
| Knowledge base search | V4 |

**User value**: High. "Find X" is a universal action pattern.
**Dependencies**: Domain-specific APIs
**Runtime impact**: None

### 4.12 Integration Cluster

Cross-cutting features that connect KIO to the browser UX.

| Feature | Phase |
|---------|-------|
| Context menu "Ask KIO" | V1.1 |
| Keyboard shortcut (Ctrl+Shift+K) | V1.1 |
| Action badge (tab count) | V1.1 |
| Omnibox "kio" keyword | V2 |
| Side panel | V2 |
| Notification relay | V2 |

**User value**: High exposure. These make KIO feel native to the browser.
**Dependencies**: ContextMenus, Commands, Action, Omnibox, SidePanel, Notifications APIs
**Runtime impact**: ~10MB side panel (shared Chrome process)

### 4.13 Intelligence Cluster

Cross-domain analysis features.

| Feature | Phase |
|---------|-------|
| Active tab awareness (global) | V1.1 |
| Workspace system | V2 |
| Study workspace | V3 |
| Research workspace | V3 |
| Reading progress | V3 |
| Tab group auto-naming | V3 |
| Bookmark auto-tagging | V3 |

**User value**: Highest long-term value. These are the "Browser OS" capabilities.
**Dependencies**: Multiple clusters
**Runtime impact**: Moderate

---

## 5. Ultimate Roadmap

### BC V1.1 — Foundation Expansion

**Theme**: Make the existing connector 3x more useful immediately.

| # | Feature | Cluster | Why Here |
|---|---------|---------|----------|
| 1 | **Active tab awareness** | Core | Single query. Zero complexity. Enables everything contextual. |
| 2 | **Tab groups CRUD** | TabGroup | Chrome API exists. Simple command mapping. Highest org value per line of code. |
| 3 | **Window query + create** | Window | Natural extension of tab commands. Users have multiple windows. |
| 4 | **Session restore (single)** | Session | One API call. "Restore last closed tab". Universal demand. |
| 5 | **Download query** | Download | Single API call. "Show recent downloads". Universal. |
| 6 | **Tab mute/unmute** | Core | Trivially simple. "Mute this tab". Daily use. |
| 7 | **Tab refresh** | Core | One API call. "Refresh". |
| 8 | **Tab duplicate** | Core | One API call. "Duplicate this tab". |
| 9 | **Tab pin/unpin** | Core | One API call. "Pin this tab". |
| 10 | **Tab zoom** | Core | One API call. "Zoom in". |
| 11 | **Context menu** | Integration | Right-click → "Ask KIO". Highest visibility integration. |
| 12 | **Keyboard shortcut** | Integration | Ctrl+Shift+K. Power user essential. |
| 13 | **Action badge** | Integration | Tab count on icon. At-a-glance awareness. |
| 14 | **Download cancel** | Download | Single API call. "Cancel this download". |
| 15 | **Download open** | Download | Single API call. "Open this file". |
| 16 | **Download show in folder** | Download | Single API call. "Where is my download?". |
| 17 | **Tab search** | Search | Query tabs by title/URL across all windows. "Find the YouTube tab". |
| 18 | **Tab move between windows** | Window | Move tabs across windows. |

**User value**: 3x current. Every user will find something useful daily.
**Runtime impact**: Negligible (~1MB additional at most)
**RAM impact**: None significant (<0.5MB)
**Risk**: Very low. All operations are single-API-call commands.

### BC V2 — Organizational Layer

**Theme**: Give users control over their browser state.

| # | Feature | Cluster | Why Here |
|---|---------|---------|----------|
| 1 | **Workspace save/restore** | Intelligence | Requires V1.1 foundations. The first truly transformative feature. |
| 2 | **Bookmark search + create** | Bookmark | Users have hundreds of bookmarks they can't find. Search is the fix. |
| 3 | **Session query by time** | Session | "What did I have open yesterday?" Needs session API + date filtering. |
| 4 | **Session naming** | Session | Named sessions persist across restarts. "Save as 'Research'". |
| 5 | **Reading queue** | Reading | "Save for later". Needs storage layer + reading list management. |
| 6 | **Window tile/arrange** | Window | "Tile two windows". Useful for multi-monitor. |
| 7 | **Window state control** | Window | Minimize, maximize, fullscreen. |
| 8 | **Omnibox integration** | Integration | Keyboard-first KIO access. Type "kio youtube" in address bar. |
| 9 | **Side panel** | Integration | Persistent KIO companion while browsing. |
| 10 | **Notification relay** | Integration | Download complete, tab loaded, session remembered. |
| 11 | **Reading priority** | Reading | "Save for tonight" / "Save for weekend". |
| 12 | **Download domain filter** | Download | "Show downloads from YouTube this week". |
| 13 | **Download pause/resume** | Download | Manage in-progress downloads. |
| 14 | **Download history erase** | Download | "Remove from download history". |
| 15 | **Bookmark folder tree** | Bookmark | "Show my bookmarks organized by folder". |
| 16 | **Bookmark remove** | Bookmark | "Delete this bookmark". |
| 17 | **Bookmark move** | Bookmark | "Move to folder". |
| 18 | **Alarm reminders** | Integration | "Remind me about this page in 30 minutes". |

**User value**: 5x current. The workspace system alone changes how users think about KIO.
**Runtime impact**: Moderate (~5MB additional)
**RAM impact**: ~2MB for persistent stores (workspace configs, reading queue, session names)
**Risk**: Low to moderate. Mostly read-only queries. Write operations have revert capability.

### BC V3 — Knowledge Layer

**Theme**: Bridge browser activity to KIO's permanent memory.

| # | Feature | Cluster | Why Here |
|---|---------|---------|----------|
| 1 | **Knowledge capture** | Knowledge | Requires offscreen + storage + KIO integration. The crown jewel feature. |
| 2 | **Offscreen content extraction** | Knowledge | Parse page content without visible tab. For summarization, knowledge capture. |
| 3 | **Focus mode** | Focus | Requires mute, close, timer, window management — all built in V1.1-V2. |
| 4 | **Study workspace** | Workspace | Article + parsed content + notes + related resources. Knowledge capture + workspace. |
| 5 | **Research workspace** | Workspace | Multi-session research with bookmarks, PDFs, knowledge captures. |
| 6 | **Reading progress** | Reading | Track reading position per article. Resume where you left off. |
| 7 | **Bookmark deduplication** | Bookmark | Find and remove duplicates. Cleanup operation. |
| 8 | **Bookmark dead-link check** | Bookmark | Batch-verify bookmark URLs. |
| 9 | **Bookmark auto-tag by domain** | Bookmark | Organize bookmarks by domain automatically. |
| 10 | **Tab group auto-name** | TabGroup | Name groups based on common domain. |
| 11 | **Batch reading save** | Reading | "Save all current research tabs to reading list". |
| 12 | **Focus timer** | Focus | "Focus for 45 minutes" with alarm. |
| 13 | **Distraction domain list** | Focus | User-defined distraction domains closed during focus. |
| 14 | **Workspace-specific focus** | Focus | "Close personal tabs during work focus". |
| 15 | **Session merge** | Session | "Add today's session to my research workspace". |

**User value**: 10x current. Knowledge capture makes KIO permanently useful beyond browsing.
**Runtime impact**: Moderate (~15MB) — mainly offscreen document overhead (temporary)
**RAM impact**: ~10MB for offscreen parse (temporary), ~5MB for knowledge store
**Risk**: Moderate. Offscreen parsing requires careful resource management on 8GB machines.

### BC V4 — Intelligence Layer

**Theme**: Connected, queryable browser intelligence.

| # | Feature | Cluster | Why Here |
|---|---------|---------|----------|
| 1 | **Knowledge base search** | Knowledge | Search all captured knowledge. |
| 2 | **Knowledge export** | Knowledge | Export as markdown, JSON, or bibliography. |
| 3 | **Research export** | Knowledge | Full research workspace → structured bibliography. |
| 4 | **Cross-session knowledge graph** | Knowledge | Linked knowledge entries across sessions. |
| 5 | **Full workspace orchestrator** | Workspace | Save/restore/switch/share complete workspace configurations. |
| 6 | **Permission manager** | Integration | Progressive permission requests. User consent per capability. |
| 7 | **Idle-aware behavior** | Intelligence | "Don't notify me when I'm away." Respect user presence. |
| 8 | **Offscreen batch processing** | Knowledge | Queue for offscreen page parsing (sequential, explicit). |
| 9 | **Focus session summary** | Focus | "You focused 3 hours this week. Closed 12 distractions." |
| 10 | **Bookmark export** | Bookmark | Generate structured bookmark lists. |

**User value**: 15x current. Knowledge graph creates a persistent second brain from browsing.
**Runtime impact**: Moderate (~10MB) — knowledge graph storage
**RAM impact**: ~5MB for knowledge graph, ~10MB for offscreen (temporary)
**Risk**: Moderate. Knowledge graph requires careful design to avoid uncontrolled growth.

### BC V5 — Browser OS Layer

**Theme**: Maximum practical browser operating layer.

| # | Feature | Cluster | Why Here |
|---|---------|---------|----------|
| 1 | **User action journal** | Intelligence | Explicitly saved action records. "What did I do in the browser yesterday?" User-opt-in. |
| 2 | **Browser health dashboard** | Integration | RAM usage, tab count, download activity, extension status. |
| 3 | **Multi-profile support** | Workspace | Multiple Chrome profiles with distinct workspaces. |
| 4 | **Declarative automation scripts** | Workspace | User-authored scripts: "When I say 'morning routine', open email, calendar, news." Deterministic, named, user-triggered. |
| 5 | **Browser resource optimizer** | Intelligence | "Free up memory" — smart tab discard based on user patterns. |
| 6 | **Workspace sharing** | Workspace | Export workspace as shareable URL collection. |
| 7 | **Cross-device session hints** | Session | Local-only session notes for multi-device workflow continuity. |
| 8 | **Advanced permission manager** | Integration | Granular per-capability consent. "KIO can access bookmarks always/once/never." |

**User value**: 20x current. Maximum useful browser integration while remaining compliant.
**Runtime impact**: Low to moderate (~5MB)
**RAM impact**: ~5MB for journal (user-controlled retention)
**Risk**: Low. All features are explicit, user-triggered, and reversible.

### Roadmap Visual Timeline

```
Phase:   V1.1         V2            V3            V4            V5
        ┌──────┐    ┌──────┐     ┌──────┐      ┌──────┐     ┌──────┐
Now     │Core  │    │Org   │     │Knowl │      │Intel │     │OS    │
───────▶│ +18  │───▶│ +18  │────▶│ +15  │─────▶│ +10  │────▶│ +8   │
        │feat  │    │feat  │     │feat  │      │feat  │     │feat  │
        └──────┘    └──────┘     └──────┘      └──────┘     └──────┘
Time:   1-2 weeks   3-6 weeks    7-12 weeks     13-20 wks    21-30 wks
RAM:    5.5 MB       7-8 MB      15-20 MB       20-25 MB     25-30 MB
Val:    3x           5x           10x            15x           20x
```

---

## 6. Browser Memory Opportunities

### 6.1 Context Sources and Memory Integration

| Source | Description | Should Integrate? | Storage Model |
|--------|------------|-------------------|---------------|
| **Active tab** | Current tab URL, title, favicon | ✅ Working memory | **Ephemeral** — queried live, not stored |
| **Open tabs** | All tab URLs, titles, status | ✅ Ephemeral context | **Ephemeral** — queried on demand, not stored |
| **Workspace state** | Named workspace configurations | ✅ Saved permanently | **Persistent** — stored in `storage.local` as JSON configs |
| **Bookmarks** | Full bookmark tree | ✅ Referenced permanently | **Chrome-owned** — KIO queries but doesn't duplicate |
| **Downloads** | Download history | ✅ Temporary query | **Ephemeral** — queried live, no persistent copy |
| **Reading queue** | Saved-for-later URLs | ✅ Saved permanently | **Persistent** — stored in `storage.local` |
| **Sessions** | Recently closed tabs/windows | ✅ Time-anchored query | **Ephemeral** — queried live, named sessions only are stored |
| **Knowledge captures** | Saved page content + metadata | ✅ Knowledge base | **Persistent** — stored in KIO knowledge store, user-managed |
| **Navigation history** | Full visit history + timestamps | ❌ NEVER | **Never accessed** — violates no-surveillance |
| **Visit timestamps** | When user visits which sites | ❌ NEVER | **Never accessed** — creates implicit profiling |
| **Page content (unsaved)** | DOM, text, images | ❌ NEVER without capture | **Never accessed** — offscreen parse only on explicit save |
| **Form data / autofill** | Saved form entries | ❌ NEVER | **Never accessed** — credential boundary |
| **Cookies / storage** | Site data | ❌ NEVER | **Never accessed** — privacy boundary |
| **Network requests** | All URLs loaded | ❌ NEVER | **Never accessed** — surveillance boundary |

### 6.2 Memory Integration Rules

```
Rule 1:  Query Live, Don't Store
         Tab lists, download lists, sessions are queried from Chrome when user asks.
         KIO never maintains a local cache of browser state.

Rule 2:  Store Only on Explicit Save
         Bookmarks, reading queue items, knowledge captures are stored only when
         user says "save". No automatic persistence of browser state.

Rule 3:  User Owns All Stored Data
         Every stored item can be listed, searched, and deleted by the user.
         No hidden persistence.

Rule 4:  Ephemeral by Default
         The default is live query. Persistence is the exception, not the rule.

Rule 5:  Named Things Persist
         Workspaces, sessions, and reading items that the user names or saves
         explicitly may persist. Unnamed state is always ephemeral.
```

### 6.3 Ephemeral vs Persistent

| Ephemeral (queried live, never stored) | Persistent (stored, user-managed) |
|---------------------------------------|-----------------------------------|
| Active tab URL/title | Workspace configurations |
| All open tabs list + URLs | Session names + timestamps |
| Recently closed tabs (Chrome API) | Reading queue items |
| Recent downloads list | Knowledge captures |
| Download status | User-defined distraction lists |
| Bookmark tree | Bookmark deduplication results (temporary) |
| Tab group state | Focus session summaries (opt-in) |
| Window state | User action journal (opt-in, V5) |
| Tab mute/zoom/pin state | Permission grants |

---

## 7. Browser Connector End State

### 7.1 What Would Exist

At maximum useful form while remaining KIO-compliant:

**Capabilities** (56 safe + 12 conditional = **68 total**):

```
Tabs:          open, close, focus, list, query (active), mute, unmute,
               refresh, duplicate, pin, unpin, discard, move, zoom,
               detect language, capture (explicit, confirmed)

TabGroups:     create group, add tab, remove tab, rename group,
               recolor group, query groups, ungroup, auto-group

Windows:       create, close, focus, minimize, maximize, fullscreen,
               query, tile, arrange, move tabs between windows

Sessions:      query recently closed, restore single, query by time,
               name session, restore named, merge sessions

Downloads:     query, filter by type/date/domain, cancel, pause,
               resume, open, show in folder, remove from history,
               notify on completion

Bookmarks:     search, create, remove, move, get tree, find duplicates,
               dead-link check, auto-tag, export

Reading:       save to queue, query queue, set priority, mark read,
               clear read, track progress, batch save

Focus:         enter mode, exit mode, define distractions, timer,
               workspace-specific, session summary

Knowledge:     capture page, extract content, search captured,
               delete entry, export entry, batch process

Integration:   context menu (Ask KIO), keyboard shortcut (Ctrl+Shift+K),
               action badge, omnibox keyword, side panel,
               notification relay, alarm reminders, permission manager,
               idle awareness, system diagnostics

Workspace:     save named, restore named, switch, delete, export,
               share (URL collection), multi-profile

Automation:    declarative user-authored scripts (deterministic, named,
               user-triggered only)
```

**Infrastructure**:

```
Consumer:
  - Event loop for command dispatch
  - WebSocket server for extension communication
  - Composable command handlers (one per API group)
  - Result formatter for natural language responses

Storage:
  - chrome.storage.local for KIO configs and user data
  - KIO's own knowledge store for captured content
  - No external databases, no cloud sync

Permission:
  - Progressive permission model
  - User consent per capability group
  - "Always / Once / Never" pattern
```

### 7.2 What Would NOT Exist

| Category | What | Why Not |
|----------|------|---------|
| **No autonomy** | Autonomous browsing, agentic research, self-directed tab management | Core KIO constraint |
| **No surveillance** | Passive history logging, page view tracking, visit timestamps, behavior profiling | Core KIO constraint |
| **No content scripts** | `executeScript`, manifest content_scripts, DOM injection | Core KIO constraint |
| **No arbitrary code** | User scripts, debugger, automation API | Core KIO constraint |
| **No credential access** | Password reading, form autofill, payment data | Core KIO constraint |
| **No network interception** | WebRequest blocking, proxy control, network diagnostics | Core KIO constraint |
| **No cloud sync** | chrome.storage.sync, Google account data access | Architecture boundary |
| **No AGI drift** | Predictive features, "you might like", auto-organization without command | Core KIO constraint |
| **No hidden instances** | Offscreen documents for processing only (no hidden browsing) | Core KIO constraint |
| **No file system access** | Local file reading, native messaging for file operations | Architecture boundary |

### 7.3 User Experience

The end-state user experience:

```
User opens Chrome normally. The KIO extension is loaded but silent.

───── User Actions ─────

"Open YouTube"
  → KIO creates a tab, registers ownership

"What tab am I on?"
  → "You're on YouTube — 'KIO Browser Connector V1 — Architecture Review'"

"Save this for later"
  → "Saved to reading queue. You have 14 unread items."

"Show my reading queue"
  → "5 articles saved today: 2 tech, 1 research, 2 recipes"

"Switch to my research workspace"
  → "Research workspace restored: 12 tabs in 3 groups, 2 windows"

"What did I download this week?"
  → "24 downloads. 3 PDFs, 12 images, 2 zips, 7 other."

"Find my bookmark about transformers"
  → "3 bookmarks found: 'Attention Is All You Need', 'BERT Paper', 'Transformer Tutorial'"

"Save this paper to my knowledge base"
  → "Saved 'Attention Is All You Need'. Extracted: Vaswani et al., 2017, 7 sections."

"Focus for 45 minutes"
  → "Focus mode active. Muted 4 tabs. Closed 2 social media tabs. Timer set."

"Restore last session"
  → "Restored 1 tab: 'Transformer Architecture Explained'"

"Group all my AI tabs"
  → "Created group 'AI Research' with 5 tabs."

"Continue my research from yesterday"
  → "Research workspace restored: ArXiv, Scholar, 3 papers."

"What's on this page?"
  → [captures visible area] "This page appears to be a research paper about..."

───── What KIO Never Does ─────

  �- Logs pages I visit without asking
  �- Mines my browsing history
  �- Predicts what I want
  �- Browses autonomously
  �- Reads my saved passwords
  �- Intercepts my network traffic
  �- Runs code on pages I visit
  �- Syncs my data to the cloud
```

### 7.4 Interaction with Other KIO Systems

| KIO System | Browser Connector Interaction |
|-----------|------------------------------|
| **Memory** | Knowledge captures → KIO's knowledge store. Workspace configs → Memory for context recall. No passive browsing goes to memory. |
| **Knowledge** | Primary knowledge intake channel. "Save this page" = one-shot capture → structured knowledge entry. Link to source URL preserved. |
| **Search** | Bookmark search, download search, tab search, knowledge search — all browser-scoped. Not KIO's general search. |
| **Sessions** | Browser sessions are separate from KIO conversation sessions. Named browser sessions can be referenced in conversation. |
| **Projects** | Workspace configs map to projects. "Open my KIO project workspace" restores project-related tabs, resources, and notes. |
| **Productivity** | Focus mode, reading queue, download management — all productivity adjuncts. KIO as daily tool, not just Q&A assistant. |

---

## 8. Final Strategic Recommendation

### 8.1 Top 20 Features KIO Should Actually Build

In recommended build order:

| Order | Feature | Phase | Why This Order |
|-------|---------|-------|----------------|
| 1 | **Active tab awareness** | V1.1 | Foundation. Single query. Enables all context. |
| 2 | **Tab groups CRUD** | V1.1 | Highest org value per line of code. Chrome-native. |
| 3 | **Window query + management** | V1.1 | Multi-window support. Natural extension. |
| 4 | **Session restore (single)** | V1.1 | "Restore last closed tab". One API call. Universal. |
| 5 | **Download awareness** | V1.1 | "Show recent downloads". One API call. Universal. |
| 6 | **Context menu** | V1.1 | Right-click → "Ask KIO". Highest visibility integration. |
| 7 | **Keyboard shortcut** | V1.1 | Ctrl+Shift+K. Power user essential. |
| 8 | **Tab mute + refresh + duplicate + pin** | V1.1 | Four trivial features for completeness. |
| 9 | **Download actions** | V1.1 | Cancel, open, show in folder. Completes download management. |
| 10 | **Workspace save/restore** | V2 | First transformative feature. Requires V1.1 foundations. |
| 11 | **Bookmark search + create** | V2 | Users have hundreds of unorganized bookmarks. Search is the unlock. |
| 12 | **Session query by time** | V2 | "What did I have open yesterday?" High daily usefulness. |
| 13 | **Reading queue** | V2 | "Save for later". Solves universal user problem. |
| 14 | **Side panel** | V2 | Persistent KIO while browsing. Foundation for ambient presence. |
| 15 | **Knowledge capture** | V3 | Crown jewel. Bridges browser to KIO's permanent knowledge. |
| 16 | **Offscreen parsing** | V3 | Content extraction without visible tab. Powers summarization + capture. |
| 17 | **Focus mode** | V3 | Productivity tool. Distraction blocking + timer. |
| 18 | **Study workspace** | V3 | Article + parsed content + notes. Deep learning support. |
| 19 | **Knowledge base search** | V4 | Find captured knowledge. Makes knowledge capture permanently useful. |
| 20 | **Focus session summary + automation scripts** | V5 | Productivity analytics and user-authored deterministic routines. |

### 8.2 Top 10 Features to Ignore

| # | Feature | Why Ignore |
|---|---------|-----------|
| 1 | **Tab highlighting** | Chrome's native multi-select is better. Low value. |
| 2 | **Tab warmup** | Pre-rendering wastes memory on 8GB machines. Performance-only. |
| 3 | **Tab zoom control** | Users use Ctrl+0/Ctrl+wheel. KIO adds no value. |
| 4 | **Tab language detection** | Niche. Users rarely need to detect page language. |
| 5 | **Power keep-awake** | Only relevant during large downloads. Too niche for general use. |
| 6 | **Tab goBack/goForward** | Browser back/forward buttons are faster than asking KIO. |
| 7 | **Download shelf toggle** | Chrome is deprecating the download shelf. |
| 8 | **Fullscreen toggle** | F11 exists. Users know it. |
| 9 | **Enterprise APIs** | Device attributes, networking — irrelevant for personal assistant. |
| 10 | **Cross-extension messaging** | No value to users. Adds complexity and permission surface. |

### 8.3 Highest Leverage Roadmap

The order that maximizes user value per unit of engineering effort:

```
PHASE 1 — "Make it 3x more useful in 2 weeks"
───────────────────────────────────────────────
Active tab → Tab groups → Windows → Session restore → Downloads
↓
Context menu → Keyboard shortcut → Tab mute/refresh/duplicate/pin
↓
Download actions (cancel, open, show)
───────────────────────────────────────────────
→ 18 features added. ~100 lines of command handler code.
→ Every feature is a single Chrome API call mapped to a natural language command.
→ User value increased 3x. RAM increase: negligible.

PHASE 2 — "Give users control of their browser state"
──────────────────────────────────────────────────────
Workspace system → Bookmark search → Session by time
↓
Reading queue → Window tile → Side panel → Notifications
↓
Bookmark tree → Alarm reminders → Window state control
───────────────────────────────────────────────────────
→ 18 features added. ~500 lines of command handler + storage code.
→ Workspace system is the first "wow" feature.
→ User value increased 5x. RAM increase: ~2MB.

PHASE 3 — "Bridge browser to permanent memory"
─────────────────────────────────────────────────
Knowledge capture → Offscreen parsing → Focus mode
↓
Study workspace → Research workspace → Reading progress
↓
Bookmark dedup → Dead-link check → Auto-group → Batch save
─────────────────────────────────────────────────────────
→ 15 features added. ~1000 lines of extraction + storage logic.
→ Knowledge capture is the crown jewel — makes KIO permanently valuable.
→ User value increased 10x. RAM increase: ~10-15MB (temporary).

PHASE 4 — "Intelligent browser layer"
──────────────────────────────────────
Knowledge search → Knowledge export → Research export
↓
Workspace orchestrator → Permission manager → Idle awareness
↓
Offscreen batch → Focus summary → Bookmark export
─────────────────────────────────────────────────
→ 10 features added. ~800 lines of query + export logic.
→ Knowledge graph connects everything.
→ User value increased 15x. RAM increase: ~5MB.

PHASE 5 — "Maximum practical browser operating layer"
─────────────────────────────────────────────────────
User action journal (opt-in) → Health dashboard → Multi-profile
↓
Declarative automation scripts → Resource optimizer
↓
Workspace sharing → Cross-device session hints → Permissions V2
───────────────────────────────────────────────────────────────
→ 8 features added. ~600 lines.
→ Maximum useful integration without violating constraints.
→ User value increased 20x. RAM increase: ~5MB (user-managed).
```

### 8.4 Biggest Risks

| Risk | Phase | Impact | Mitigation |
|------|-------|--------|------------|
| **Offscreen memory on 8GB** | V3 | Offscreen documents use ~10MB RAM. On i3-1315U + 8GB, multiple simultaneous offscreen operations could strain resources. | Single-parse queue. No parallel offscreen operations. Explicit user invocation only. Kill offscreen after parse completes. |
| **Knowledge store growth** | V3+ | Untracked knowledge captures could grow unbounded, consuming RAM and storage. | User-configurable retention. Delete-oldest-when-full policy. Explicit export before delete. |
| **Permission creep** | V2+ | Progressive permission requests could overwhelm users. "KIO needs access to X" every time they use a new feature. | Group permissions by capability cluster. One permission per cluster. "Always / Once / Never" with "Always" default for low-risk metadata APIs. |
| **Chrome API deprecation** | V3+ | Chrome may deprecate Sessions, TabGroups, or Downloads APIs in future MV4. | Monitor Chrome extension API changelog. Abstract API calls behind adapter layer. Fallback to degraded behavior. |
| **Workspace complexity** | V2 | Workspace save/restore with multiple windows, groups, and pinned tabs is complex state management. | Keep workspace configs simple (URLs + group names + window count). No attempt to preserve scroll position, form state, or tab history. |
| **Focus mode overreach** | V3 | Closing "distraction tabs" could close something the user needed. | Reopen all closed tabs on focus exit. Preview what will close before action. Never close pinned tabs. |
| **Side panel memory** | V2 | Chrome side panel adds ~10MB persistent RAM cost. | Side panel is opt-in. User must enable explicitly. Disabled by default. |

### 8.5 Biggest Opportunities

| Opportunity | Phase | Why |
|------------|-------|-----|
| **Workspace system** | V2 | No Chrome extension does comprehensive workspace management. This is a blue ocean. Users will tell friends. |
| **Knowledge capture** | V3 | Bridging browser activity to personal knowledge base is the holy grail of AI-assisted browsing. No existing tool does it well. |
| **Reading queue with progress** | V2 | Every browser has "bookmarks" but no browser has a good "read later" with progress tracking. Pocket charges for this. |
| **Tab groups intelligence** | V1.1 | Chrome's tab groups API is powerful but invisible. KIO makes it accessible through natural language. |
| **Context menu integration** | V1.1 | Right-click "Ask KIO" is the highest-exposure integration point. Works on every page, every link, every selection. |
| **Focus mode** | V3 | Browser-native focus mode doesn't exist. KIO can create it through tab/window orchestration. |
| **Session time travel** | V2 | "What did I have open yesterday" — Chrome's session restore is binary (restore everything or nothing). KIO can query, filter, and selectively restore. |

### 8.6 Recommended Browser Connector Development Order

This is the master development order — from the very next implementation step to the final mature state.

```
STEP 1:  Active Tab Awareness
         └─ "What tab am I on?" — single query, zero complexity, foundational

STEP 2:  Tab Groups
         └─ Create, add, remove, rename, recolor, query groups

STEP 3:  Window Management
         └─ Query, create, close, focus windows. Move tabs between windows.

STEP 4:  Session Restore
         └─ "Restore last closed tab" — single API call

STEP 5:  Download Awareness
         └─ Query recent downloads by type, status, domain. Show in folder. Open.

STEP 6:  Tab Utilities
         └─ Mute, unmute, refresh, duplicate, pin, unpin, zoom

STEP 7:  Context Menu + Keyboard Shortcut
         └─ Right-click "Ask KIO" everywhere. Ctrl+Shift+K global hotkey.

STEP 8:  Action Badge + Tab Search
         └─ Tab count on icon. Search tabs across all windows.

─── V1.1 COMPLETE (18 features) ───

STEP 9:  Workspace System (MVP)
         └─ Save named workspace, restore named workspace, list workspaces

STEP 10: Bookmark Intelligence
         └─ Search bookmarks, create in folder, get tree, remove

STEP 11: Session by Time
         └─ "What did I have open yesterday?" — query sessions with time windows

STEP 12: Reading Queue
         └─ Save for later, query queue, set priority, mark read, clear read

STEP 13: Side Panel
         └─ Persistent KIO companion while browsing

STEP 14: Notification Relay + Alarm Reminders
         └─ Download complete alerts, "remind me about this page"

STEP 15: Window Arrangement
         └─ Tile windows, arrange, minimize/maximize all

─── V2 COMPLETE (18 features) ───

STEP 16: Knowledge Capture
         └─ Capture active page: URL, title, meta, content. Store in KIO knowledge.

STEP 17: Offscreen Content Extraction
         └─ Parse full page content in offscreen document. Extract headings, key terms.

STEP 18: Focus Mode
         └─ Enter/exit focus. Distraction domains. Timer. Workspace-specific focus.

STEP 19: Study Workspace
         └─ Article + extracted content + notes + related resources. Learning environment.

STEP 20: Research Workspace
         └─ Multi-session research. Bookmarks + PDFs + knowledge captures.

STEP 21: Reading Progress
         └─ Track reading position. "Continue reading" resumes from last position.

STEP 22: Bookmark Maintenance
         └─ Deduplication, dead-link check, auto-tag by domain

STEP 23: Tab Group Intelligence
         └─ Auto-name groups by domain. Batch ungroup.

─── V3 COMPLETE (15 features) ───

STEP 24: Knowledge Base Search + Export
         └─ Search all captured knowledge. Export as markdown/JSON.

STEP 25: Full Workspace Orchestrator
         └─ Save/restore/switch/share complete workspace configurations.

STEP 26: Permission Manager
         └─ Progressive permission grants. Per-cluster consent.

STEP 27: Idle-Aware Behavior
         └─ Respect user presence. Suppress notifications when away.

STEP 28: Offscreen Batch Processing
         └─ Sequential queue for offscreen parsing. User-triggered batch operations.

STEP 29: Focus Session Summary
         └─ Report focus time, tabs closed, distractions blocked.

─── V4 COMPLETE (10 features) ───

STEP 30: User Action Journal (Opt-In)
         └─ Explicitly saved action records. User-owned. User-deletable.

STEP 31: Browser Health Dashboard
         └─ RAM, tabs, downloads, extension status.

STEP 32: Declarative Automation Scripts
         └─ User-authored: "When I say 'morning routine', do X, Y, Z." Deterministic, named.

STEP 33: Multi-Profile Support
         └─ Workspace system extended to Chrome profiles.

STEP 34: Browser Resource Optimizer
         └─ "Free up memory" — smart tab discard.

STEP 35: Workspace Sharing
         └─ Export workspace as shareable URL collection.

─── V5 COMPLETE (8 features) — MAXIMUM USEFUL FORM ───
```

---

## Final Verdict

**The Browser Connector can reach a state where it manages the user's entire browser activity through natural language — without ever violating KIO Architecture v1.1.**

The boundary is clean:
- **68 capabilities** across 5 phases
- **25 permanently rejected** capabilities
- **30MB peak RAM** at maximum useful form (acceptable for 8GB target)
- **20x user value** improvement over baseline

The path is clear. The constraints are respected. The opportunity is massive.

Build workspaces first. Everything follows.

---

*End of Implementation Roadmap*
