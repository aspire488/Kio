# MCP Server Ecosystem — 2026 Catalog

Research date: 2026-08-16. Star counts verified via GitHub API where noted. All URLs verified reachable at research time. Items marked **UNVERIFIED** could not be confirmed from a primary source.

---

## 1. The Protocol: Transports

Per the official spec (revision `2025-06-18`), there are exactly **two standard transports**:

| Transport | Notes |
|---|---|
| **stdio** | Local subprocess servers. Clients **SHOULD** support stdio. Most reference/community servers are stdio. |
| **Streamable HTTP** | Remote servers over HTTP(S). Replaced the older HTTP+SSE transport (2024-11-05 revision). Used by Todoist, Home Assistant, GitLab.com, Google's hosted Calendar/Gmail servers. |

Custom transports are permitted by the spec. Source: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

---

## 2. Registries & Directories

### Official registry
- **URL:** https://registry.modelcontextprotocol.io/ — "an app store for MCP servers."
- **Repo:** https://github.com/modelcontextprotocol/registry (Go, ~7.2k stars, MIT-ish "Other" license).
- Maintained by Anthropic + community; launched in preview **September 2025**.
- Purpose: machine-readable discovery for MCP clients, not casual browsing. REST API with OpenAPI spec, `server.json` spec, CLI.
- Docs: `docs/modelcontextprotocol-io/quickstart.mdx` (publishing), `docs/reference/api/` (API spec).
- Namespaced server IDs, e.g. `io.github.dgahagan/weather-mcp`, `ai.pubfi/mcp`.

### Third-party directories (as of mid-2026)

| Directory | Server count | Curation | Notes |
|---|---|---|---|
| **PulseMCP** — pulsemcp.com | 11,840+ | Hand-reviewed, daily | Also catalogs MCP *clients*; "Agentic Loop" newsletter; free, MIT. |
| **Glama** — glama.ai/mcp/servers | 21,000+ | Automated + community | Largest volume; daily updates. |
| **mcp.so** — mcp.so | 19,700+ | Community-submitted | GitHub-issue submissions; strong for third-party/unofficial tools. |
| **Smithery** — smithery.ai | 7,000+ | Community + hosted | Registry **plus hosting** + `Toolbox` meta-MCP router; CLI install; freemium. Joined **Arcade.dev** (2026). **UNVERIFIED:** exact current count. |
| **mcp.directory** | 3,000+ | — | One-click IDE install. |
| **mcpmarket.com** | — | — | Daily rankings + top-100 leaderboard by GitHub stars. |
| **GitHub awesome list** — punkpeye/awesome-mcp-servers | ~92,300 stars | Community | The canonical human-curated list. |

Sources: https://automationswitch.com/mcp, https://automationswitch.com/ai-workflows/where-to-find-mcp-servers-2026, https://thinkneo.ai/blog/mcp-registries-compared-20260714

---

## 3. Official SDKs & Reference Servers

### SDKs (all `github.com/modelcontextprotocol/*`)
| SDK | Stars | Notes |
|---|---|---|
| python-sdk | 24,016 | `mcp` package. Docs: py.sdk.modelcontextprotocol.io |
| typescript-sdk | 13,178 | Docs: ts.sdk.modelcontextprotocol.io/v2 |
| csharp, go, java, kotlin, php, ruby, rust, swift | — | Full official SDK family |

### Reference servers — `modelcontextprotocol/servers` (89,599 stars)
**Active:** Everything (test server), Fetch, Filesystem, Git, Memory (knowledge-graph), Sequential Thinking, Time.
**Archived** (now in `servers-archived`; several replaced by official/vendor servers): AWS KB, Brave Search (→ brave/brave-search-mcp-server), GitHub (→ github/github-mcp-server), GitLab, Google Drive, Google Maps, PostgreSQL, Puppeteer, Redis, Sentry, Slack (→ zencoderai/slack-mcp-server), SQLite.

> Repo explicitly warns these are **reference implementations, not production-ready**.

Run examples: `npx -y @modelcontextprotocol/server-memory`, `uvx mcp-server-git`, `uvx mcp-server-fetch`. On Windows, wrap `npx` entries with `cmd /c`.

---

## 4. Building Servers: FastMCP

- **Repo:** https://github.com/PrefectHQ/fastmcp (formerly jlowin/fastmcp) — **27,233 stars**. Docs: https://gofastmcp.com/
- **Install:** `uv add fastmcp` or `pip install fastmcp` (latest stable is 3.x; **v4 is in prerelease** as `4.0.0b3`, MCP 2.0.0).
- "The Framework for MCP" — high-level Python framework over the official SDK. Handles schema generation, validation, transport, auth.
- Feature surface (docs index): `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` decorators; transforms (rename/reshape tools, code-mode, tool-search, namespaces); middleware; dependency injection; lifespans; storage backends; auth from API keys to full **OAuth 2.1** (+ remote OAuth, OIDC/OAuth proxies, multi-auth, authorization callables); **FastMCP Apps** (interactive UIs in chat — charts, forms, approvals, file upload); a client library; `fastmcp` CLI (run/install/inspect); `fastmcp-remote` bridge for stdio-only hosts; OpenAPI→server generation.
- Minimal server:
  ```python
  from fastmcp import FastMCP
  mcp = FastMCP("Demo")
  @mcp.tool
  def add(a: int, b: int) -> int: return a + b
  mcp.run()
  ```

---

## 5. Most-Starred Projects (GitHub API, 2026-08-16)

Note: several of these are libraries/platforms *with* an MCP server, not standalone MCP servers — flagged below.

| # | Repo | Stars | What it is |
|---|---|---|---|
| 1 | microsoft/markitdown | 173,946 | Convert files/Office docs → Markdown (library; MCP variant exists) |
| 2 | browser-use/browser-use | 109,358 | AI browser automation (includes MCP server) |
| 3 | punkpeye/awesome-mcp-servers | 92,332 | Curated server list (directory, not a server) |
| 4 | modelcontextprotocol/servers | 89,599 | Official reference servers |
| 5 | netdata/netdata | 80,194 | Observability platform (includes MCP server) |
| 6 | upstash/context7 | 60,808 | Docs context for LLMs (MCP server) |
| 7 | mindsdb/mindshub | 39,583 | AI workspace / model hub (MCP-related) |
| 8 | microsoft/playwright-mcp | 36,166 | Browser automation MCP server |
| 9 | github/github-mcp-server | 32,281 | Official GitHub MCP server |
| 10 | eyaltoledano/claude-task-master | 28,002 | Task-management system for AI agents |
| 11 | PrefectHQ/fastmcp | 27,233 | Server framework |
| 12 | modelcontextprotocol/python-sdk | 24,016 | Official Python SDK |
| 13 | modelcontextprotocol/typescript-sdk | 13,178 | Official TS SDK |

---

## 6. Free / Open-Source Servers by Capability Class

### Development & coding
- **GitHub** — github/github-mcp-server (Go, 32,281★). OAuth or `GITHUB_PERSONAL_ACCESS_TOKEN`; GitHub Enterprise Server via `GITHUB_HOST`. Repo/issue/PR/actions ops.
- **GitLab** — jmrplens/gitlab-mcp-server (Go, MIT, stdio + Streamable HTTP, read-only & safe modes). Exposes **850+ GitLab CE / 1,000+ GitLab.com operations**; self-hosted + CE/EE. Also: GitLab's own hosted remote MCP at `https://<instance>/api/v4/mcp` (OAuth).
- **Browser automation** — microsoft/playwright-mcp (TypeScript, 36,166★, Apache-2.0). Runs on accessibility snapshots (no vision model). Tools incl. `browser_navigate`, `browser_click`, `browser_snapshot`, `browser_take_screenshot`, `browser_type`, `browser_evaluate`, `browser_tabs`, `browser_network_requests`. Install: `npx @playwright/mcp@latest`. **Not a security boundary** per its own README.
- **Task management** — eyaltoledano/claude-task-master (JS, 28,002★). Task system for Cursor, Lovable, Windsurf, Roo.

### Documentation / context
- **context7** — upstash/context7 (60,808★). Fetches current library/framework docs for LLMs (used by this session's research).
- **Web fetch** — official `mcp-server-fetch` (`uvx mcp-server-fetch`). Fetch + convert web pages for LLM consumption.

### Data / knowledge / research
- **arXiv** — haegyung/arxiv-consensus-mcp (Python, MIT). arXiv search works with **no credentials**; Consensus integration needs `CONSENSUS_API_KEY`.
- **Wikidata** — ryge/wikidata-mcp (Python, BSD-2-Clause). SPARQL query access to the Wikidata endpoint.
- **Weather (NOAA)** — weather-mcp/weather-mcp (TypeScript, MIT; npm `@dangahagan/weather-mcp`). **17 tools, zero API keys**: forecasts, alerts, air quality, marine, radar, lightning, rivers, wildfires, historical to 1940. Data from NOAA, Open-Meteo, USGS, NIFC, MeteoAlarm. US data richer than international. Install: `claude mcp add weather -- npx -y @dangahagan/weather-mcp@latest`.
- **Weather (simple)** — isdaniel/mcp_weather_server (Python, PyPI `mcp-weather-server`). Open-Meteo only, no key; supports Streamable HTTP.
- **Finance** — barvhaim/yfinance-mcp-server (Python). Unofficial Yahoo Finance wrapper; ~10 tools.
- **File/document conversion** — microsoft/markitdown (Python, 173,946★). Office/media → Markdown; MCP server variant available.

### Productivity / communication
- **Todoist** — Doist/todoist-mcp (Node, `npx @doist/todoist-mcp`). **Hosted** Streamable HTTP at `https://ai.todoist.net/mcp`, OAuth. Tools incl. `findTasksByDate`, `addTasks`.
- **Google Workspace** — taylorwilsdon/google_workspace_mcp (Python, MIT). 12 services / **100+ tools** (Gmail, Drive, Docs, Sheets, Calendar, Slides, Forms, Chat, Tasks, Contacts, Apps Script). OAuth 2.1, your own GCP credentials, stateless mode. Install: `uvx workspace-mcp`.
- **Google Calendar (hosted, official)** — `https://calendarmcp.googleapis.com/mcp/v1` (OAuth client ID/secret needed). Docs: developers.google.com/workspace/calendar/api/guides/configure-mcp-server.
- **Gmail (hosted, official)** — `https://gmailmcp.googleapis.com/mcp/v1` (OAuth). Docs: developers.google.com/workspace/gmail/api/guides/configure-mcp-server.
- **Google Calendar (self-hosted)** — nspady/google-calendar-mcp (Node, OAuth). Multi-calendar, recurring events, free/busy.
- **Email (self-hosted)** — shinzo-labs/gmail-mcp (`npx @shinzolabs/gmail-mcp`), bastienchabal/gmail-mcp (Python, Gmail + Calendar).
- **YouTube transcripts** — suckerfish/yttranscript_mcp (Python/FastMCP, uses `yt-dlp`). No API key.

### Media / music
- **Spotify** — GraysonCAdams/spotify-mcp (playback, search, playlists; OAuth) or llyfn/spotify-mcp (PyPI `mcp-server-spotify`, Authorization-Code OAuth, tokens in `~/.spotify-mcp/credentials.json`). Both require a Spotify Developer app + Premium.

### Mapping
- **simple-maps-mcp** — GlacianNex/simple-maps-mcp (Node/TS). OpenStreetMap static tiles + Nominatim geocoding, **no API key**.

### Smart home
- **Home Assistant (official built-in)** — the `mcp_server` integration exposes `Assist` at `http://<ha>/api/mcp` (Streamable HTTP), **OAuth**, tools+prompts+resources. Reference: home-assistant.io/integrations/mcp_server.
- **Home Assistant (community)** — homeassistant-ai/ha-mcp (~4.3k stars, FastMCP-based, HACS install, "unofficial and awesome") and tevonsb/homeassistant-mcp (TypeScript, Apache-2.0).

### Health / fitness
- **Apple Health** — the-momentum/apple-health-mcp-server (Python). Queries Apple Health XML exports via natural language. **Superseded by** the-momentum/open-wearables (multi-wearable: Garmin, Polar, WHOOP, Suunto, Apple Health).
- **WHOOP** — JedPattersonn/whoop-mcp (TypeScript/Bun, MIT; OAuth; sleep/recovery/strain/HRV) or xokvictor/whoop-mcp (Go).

### Observability / infrastructure
- **netdata** — netdata/netdata (80,194★, GPL-3.0). AI-powered observability platform; ships an MCP server for node health/queries.

---

## 7. Security Notes

Primary source: SlowMist **MCP Security Checklist** — github.com/slowmist/MCP-Security-Checklist (English + CN). High-priority (must-not-omit) items, condensed:

**Server side**
- Strict input validation on all APIs and tool inputs (injection defense).
- RBAC / least privilege; secure credential management (no hard-coded secrets, key rotation); secure auth to third-party services.
- Run in an isolated env (container/VM/sandbox), hardened, non-root.
- Verify third-party interface responses before inserting into context (tool-description / data injection).
- Supply chain: verify package integrity, manage dependencies.
- Logging, anomaly detection, real-time alerting, data encryption + minimization.

**Client / host side**
- UI must make AI's scope visible; **explicit user confirmation for high-risk ops** (file deletion, fund transfers).
- Prompt-injection layered defense; separate system vs user prompts; filter sensitive data.
- Verify server identity; strict TLS (1.2+); TLS cert validation (MitM).
- Token least privilege; control auto-approve; function-name conflict checks before registering tools.
- Implement OAuth 2.1+ correctly; use `state` param against CSRF.

**Multi-MCP scenarios**
- Enabling many servers at once is itself risky (no official store audits plugins). Watch function-priority hijacking and **cross-MCP tool-call injection** (malicious server returns prompts that trigger other servers' sensitive ops).

**Notable incidents / ecosystem warnings**
- Smithery had a 2026 vulnerability (build-config directory-traversal) reported to affect **3,000+ hosted servers** and thousands of API keys before patching — **UNVERIFIED**, per third-party writeups.
- A dev.to scan of 100 Smithery-listed servers found findings on **22**, mostly **tool-description injection** — **UNVERIFIED**.
- Playwright MCP explicitly states it is "**not a security boundary**" and recommends client-level permissions.
- Self-assessment tool: Tencent **AI-Infra-Guard** (github.com/Tencent/AI-Infra-Guard).

---

## 8. Key URLs

- Spec transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- Official registry: https://registry.modelcontextprotocol.io/ · repo: https://github.com/modelcontextprotocol/registry
- Reference servers: https://github.com/modelcontextprotocol/servers
- Python SDK: https://github.com/modelcontextprotocol/python-sdk · TS SDK: https://github.com/modelcontextprotocol/typescript-sdk
- FastMCP: https://github.com/PrefectHQ/fastmcp · https://gofastmcp.com/
- Awesome list: https://github.com/punkpeye/awesome-mcp-servers
- Directories: https://pulsemcp.com · https://glama.ai/mcp/servers · https://mcp.so · https://smithery.ai
- Security checklist: https://github.com/slowmist/MCP-Security-Checklist

---

### Method & caveats
- Star counts from GitHub REST API (2026-08-16) or the listed third-party source; the "stars" of directory items (punkpeye list) reflect popularity, not server quality.
- "Free/open-source" verified per README/license of each linked repo at research time; licenses change.
- The MCP spec and registry evolve quickly — treat counts (registry size, directory sizes, star deltas) as point-in-time.