# KIO — OpenCode MCP Stack: Full Windows Setup

Target: Windows 11, PowerShell, Node LTS, npm, OpenCode latest.
Stack: Filesystem, Git, Memory, Sequential Thinking, Context7, Playwright — official/first-party only, nothing else.

Every command below assumes PowerShell (not cmd.exe, not Git Bash) unless stated.

---

## Variables used throughout

Paste this into your PowerShell session first — every script and command below reuses these instead of hardcoding your username.

```powershell
$KioRoot   = "$env:USERPROFILE\OneDrive\Desktop\Kio\kio_final"
$OcGlobal  = "$env:USERPROFILE\.config\opencode"
$OcGlobalConfig  = "$OcGlobal\opencode.json"
$OcProjectConfig = "$KioRoot\opencode.json"
$BackupDir = "$env:USERPROFILE\.kio-mcp-backups"
```

**Note on `<USER>` in your original path**: don't hardcode it. `$env:USERPROFILE` resolves it automatically and survives you renaming the Windows account or running this on another machine. Use `$KioRoot` everywhere instead of the literal path from here on.

**OneDrive warning**: your project root is inside OneDrive Desktop sync. OneDrive actively locks files it's mid-syncing, which breaks `npm install`/`npx` cache writes intermittently — this is the #1 cause of phantom "permission denied" errors that aren't actually permission errors. If you hit unexplained npx failures, right-click the `kio_final` folder → "Always keep on this device" and pause OneDrive sync during install (`OneDrive icon in tray → Settings → Pause syncing → 2 hours`).

---

## Phase 1 — Prerequisite Verification

Run each line, confirm the expected output shape (not exact versions — just "a version prints, not an error").

```powershell
node -v                                    # expect: v20.x.x or v22.x.x (LTS)
npm -v                                     # expect: 10.x.x or higher
npx -v                                     # expect: same as npm
git --version                              # expect: git version 2.x.x
Get-ExecutionPolicy -List                  # check CurrentUser / LocalMachine scopes
opencode --version                         # expect: a version string, not "not recognized"
where.exe opencode                         # confirms it's on PATH
where.exe npx                              # confirms npx.cmd location — you'll need this path later
```

If `Get-ExecutionPolicy -List` shows `Restricted` for `CurrentUser`, the .ps1 scripts in this package won't run. Fix once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

This is the standard, safe setting — it allows locally-authored scripts to run while still blocking unsigned scripts downloaded from the internet without review. Don't use `Unrestricted` or `Bypass` as a permanent policy.

### uv / uvx — required for the Git MCP server

The official Git MCP server is a **Python package**, not npm. You need `uv` installed:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then restart PowerShell and verify:

```powershell
uv --version
uvx --version
```

If `opencode` itself isn't found in Phase 1, install/update it per OpenCode's own install docs at opencode.ai — this guide assumes it's already installed, since your prompt specified "OpenCode: Latest version" as a given.

---

## Phase 2 — Install Each MCP

You are **not** pre-installing these as global npm packages (except where noted) — `npx -y` fetches and caches on first run, then reuses the cache. This is the officially recommended pattern and avoids version drift. Run each once manually so the cache is warm and you catch errors before OpenCode does:

```powershell
# Filesystem (official)
npx -y @modelcontextprotocol/server-filesystem --help

# Memory (official)
npx -y @modelcontextprotocol/server-memory --help

# Sequential Thinking (official)
npx -y @modelcontextprotocol/server-sequential-thinking --help

# Context7
npx -y @upstash/context7-mcp --help

# Playwright (official) — this one pulls a Chromium binary, expect it to take longer
npx -y @playwright/mcp@latest --help
npx -y playwright install chromium
```

Git MCP server (Python, via `uvx` — do NOT use npx for this one):

```powershell
uvx mcp-server-git --help
```

If any `--help` invocation prints usage text (even with warnings), the package resolved correctly. If it hangs indefinitely, kill it (Ctrl+C) — that usually means npm's registry is unreachable (check firewall/proxy in Phase 7).

### Context7 API key (free tier)

1. Go to `context7.com/dashboard` in a browser.
2. Sign in (GitHub OAuth or email).
3. Generate an API key from the dashboard.
4. Save it — you'll put it in an environment variable, not hardcoded in the JSON (see Phase 5).

### Version pinning

Don't pin these to exact versions in your config. All six are actively maintained with frequent patches; pinning creates silent staleness on a stack this small. The one place pinning matters is Playwright, because the MCP server version and the installed browser binary version must match — always update both together (`update-mcps.ps1` handles this).

---

## Phase 3 — Production Configuration

### Directory structure

```
%USERPROFILE%\.config\opencode\
  └─ opencode.json          ← GLOBAL config: your 6 trusted MCP servers live here
  └─ mcp-auth.json           ← auto-created by OpenCode, don't hand-edit

<KioRoot>\
  └─ opencode.json           ← PROJECT config: KIO-specific overrides only, NO mcp block
  └─ .env.local              ← CONTEXT7_API_KEY lives here, gitignored

%USERPROFILE%\.kio-mcp-backups\
  └─ opencode.<timestamp>.json   ← created by backup-mcps.ps1
```

**Why global, not project**: this is the security point from earlier in this conversation, made mechanical. Your `mcp` block goes in `%USERPROFILE%\.config\opencode\opencode.json` (global), never in `<KioRoot>\opencode.json` (project). OpenCode merges global + project config, with project taking precedence for overlapping keys — but if a malicious `opencode.json` shows up inside a repo you `git clone` into `external/`, it can only add project-scoped keys, and your global `mcp` definitions win the merge for any server *name* it tries to override. It cannot silently redefine `filesystem`, `git`, etc. to point at a malicious command, because those names are already locked in globally. It could still define a *new* server name — which is why Phase 8 covers not blindly running `opencode` inside freshly cloned repos at all.

### Global config — `%USERPROFILE%\.config\opencode\opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\<USER>\\OneDrive\\Desktop\\Kio\\kio_final"],
      "enabled": true
    },
    "git": {
      "type": "local",
      "command": ["uvx", "mcp-server-git", "--repository", "C:\\Users\\<USER>\\OneDrive\\Desktop\\Kio\\kio_final"],
      "enabled": true
    },
    "memory": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-memory"],
      "enabled": true
    },
    "sequential-thinking": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
      "enabled": true
    },
    "context7": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@upstash/context7-mcp"],
      "environment": {
        "CONTEXT7_API_KEY": "{env:CONTEXT7_API_KEY}"
      },
      "enabled": true
    },
    "playwright": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@playwright/mcp@latest"],
      "enabled": true
    }
  }
}
```

**Field-by-field, because you asked for no unexplained placeholders:**

- `"type": "local"` — tells OpenCode this is a subprocess it spawns itself (stdio transport), as opposed to `"remote"` (an HTTP/SSE URL, which none of your six are).
- `"command"` — an array, not a string. First element is the actual executable OpenCode's `child_process.spawn` calls; everything after is arguments. **The `["cmd", "/c", "npx", ...]` wrapper is Windows-mandatory** — without it, `spawn` tries to execute `npx` directly, fails to resolve `npx.cmd` (a batch file, not a `.exe`), and throws `ENOENT`. This is not optional on Windows.
- `filesystem`'s last arg (`C:\Users\...\kio_final`) is the **allowed root directory** — the filesystem MCP refuses to touch anything outside it. Replace `<USER>` with your actual Windows username, or better, build this string from `$KioRoot` if you're scripting the JSON (see `install-mcps.ps1`).
- `git`'s `--repository` flag points it at the KIO repo specifically — it won't operate on arbitrary repos on your disk.
- `memory` and `sequential-thinking` take no arguments — they're self-contained, no filesystem/network scope to restrict.
- `context7`'s `"environment"` block injects `CONTEXT7_API_KEY` from your **shell environment variable** (`{env:CONTEXT7_API_KEY}` syntax — OpenCode substitutes this at launch) rather than hardcoding the key in this JSON file. This matters because this file may end up in a dotfiles backup or screen-share someday; the key shouldn't be sitting in plaintext where you're not expecting it.
- `playwright` takes no path arguments — it launches an isolated browser profile by default (see Phase 4 troubleshooting for the CDP/existing-profile alternative, which you don't need yet).
- `"enabled": true` on every entry — explicit, not relying on default-enabled, so `repair-mcps.ps1` can toggle one off cleanly without deleting its config block.

### Project config — `<KioRoot>\opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json"
}
```

Deliberately empty of an `mcp` block. Project config is for KIO-specific model/permission/agent settings later — not MCP servers. Keeping MCP definitions exclusively in global config is the enforcement mechanism from Phase 8.

### Setting `CONTEXT7_API_KEY` as a persistent user environment variable (Windows)

```powershell
[System.Environment]::SetEnvironmentVariable("CONTEXT7_API_KEY", "YOUR_KEY_HERE", "User")
```

Then **close and reopen PowerShell** (env vars set this way don't propagate to already-open shells or already-running OpenCode instances). Verify:

```powershell
[System.Environment]::GetEnvironmentVariable("CONTEXT7_API_KEY", "User")
```

---

## Phase 5 — Environment Variables Reference

| Variable | Purpose | Where to set it | Required? |
|---|---|---|---|
| `CONTEXT7_API_KEY` | Auth for higher Context7 rate limits | User env var (`SetEnvironmentVariable ... "User"`) | Optional — works without it at low rate limits, but you already have a free key from Phase 2 |
| `PATH` | Must include npm global bin (`%APPDATA%\npm`) and uv's install dir (`%USERPROFILE%\.local\bin` or wherever the uv installer put it) | System/User PATH via `sysdm.cpl` → Environment Variables, or `[System.Environment]::SetEnvironmentVariable("Path", ..., "User")` | Required |
| `NODE_OPTIONS` | Not required for this stack. Only set `--max-old-space-size` if you see OOM crashes from a specific server (unlikely on this stack — none are memory-heavy) | N/A unless troubleshooting | Not required |
| `OPENCODE_MCP_PATH` | Not a real OpenCode variable — OpenCode reads MCP definitions from `opencode.json`'s `mcp` key, not a separate path variable. Don't set this; it does nothing. | — | N/A (does not exist — flagging so you don't waste time) |

I'm flagging `OPENCODE_MCP_PATH` explicitly rather than inventing a plausible-sounding config for it, per your own instruction not to invent fields.

---

## Phase 6 — Verification Procedures

### Step 1: OpenCode sees all six servers

```powershell
opencode mcp list
```

**Expected output**: six entries — `filesystem`, `git`, `memory`, `sequential-thinking`, `context7`, `playwright` — each showing `enabled` and (after first successful connection) a status indicator, not an error.

**Failure output looks like**: a server listed with `disabled`, `error`, or missing entirely (means OpenCode didn't parse it out of the JSON — check for a JSON syntax error with `Get-Content $OcGlobalConfig | ConvertFrom-Json` in PowerShell, which throws a clear parse error if the file is malformed).

### Step 2: Inside an OpenCode session

```
/mcp
```

This shows live connection status per server inside the TUI/chat session itself — use this after `opencode mcp list` looks right but you want to confirm actual runtime connectivity, not just config parsing.

### Step 3: Functional test prompts (run inside an OpenCode session, one at a time)

| Server | Test prompt | Expected | Failure signal |
|---|---|---|---|
| Filesystem | `List the files in the KIO repo root` | A real directory listing of `kio_final` | "I don't have access to..." / tool not found |
| Git | `What's the current git branch and last 3 commits in this repo?` | Real branch name + commit log | Error mentioning `uvx` or "command not found" |
| Memory | `Remember that KIO's current blocker is Gate C-09.` then in a **new** session: `What's KIO's current blocker?` | Second session recalls it | No memory tool called, or recall fails |
| Sequential Thinking | `Use sequential thinking to break down how you'd debug a stale cache bug.` | Visible multi-step reasoning trace | Falls back to normal single-pass answer |
| Context7 | `use context7 — show me the current React useEffect cleanup pattern` | Current, cited docs snippet | "I don't have a context7 tool" or stale/generic answer |
| Playwright | `Open a browser and navigate to example.com, then tell me the page title.` | Returns "Example Domain" | Browser launch error, or Chromium-not-found error |

### Diagnostic commands if something's silently wrong

```powershell
# Confirm the JSON itself is valid
Get-Content $OcGlobalConfig -Raw | ConvertFrom-Json | Format-List

# Confirm each binary resolves independently of OpenCode
where.exe npx
where.exe uvx
uvx mcp-server-git --repository $KioRoot --help

# Check OpenCode's own logs (path varies by version — check its docs if not here)
Get-ChildItem "$env:USERPROFILE\.local\share\opencode" -Recurse -Filter *.log -ErrorAction SilentlyContinue
```

---

## Phase 7 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `node: command not found` | Node not installed or not on PATH | Reinstall Node LTS from nodejs.org, ensure "Add to PATH" checked during install |
| `npx: command not found` inside OpenCode but works in terminal | Missing `cmd /c` wrapper — OpenCode's spawn doesn't inherit your interactive shell's PATH resolution the same way | Add `["cmd", "/c", "npx", ...]` as shown in Phase 3 |
| `spawn npx ENOENT` | Same root cause as above — Windows `child_process.spawn` won't resolve `.cmd` files without a shell wrapper (this is a documented Node/CVE-2024-27980 mitigation issue, confirmed across OpenCode, Claude Code, Copilot CLI, and Cursor) | `cmd /c` wrapper, or use the full absolute path to `npx.cmd` from `where.exe npx` |
| `Set-ExecutionPolicy` "cannot be loaded because running scripts is disabled" | Execution policy is `Restricted` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (see Phase 1) |
| Playwright MCP: "browser not found" / launch failure | Chromium binary wasn't downloaded, or was downloaded to a path OneDrive later moved/locked | `npx -y playwright install chromium` — rerun it; if it still fails, move `kio_final` out of OneDrive sync or exclude the Playwright cache dir (`%USERPROFILE%\AppData\Local\ms-playwright`) from OneDrive |
| Context7: 401/auth error | Key not set, wrong scope, or shell wasn't restarted after `SetEnvironmentVariable` | Restart PowerShell + OpenCode fully; verify with `[System.Environment]::GetEnvironmentVariable("CONTEXT7_API_KEY","User")` |
| OpenCode doesn't detect a server at all (missing from `opencode mcp list`) | JSON syntax error (trailing comma, mismatched brace) — JSON is strict, unlike JSONC | Validate with `Get-Content $OcGlobalConfig -Raw \| ConvertFrom-Json`; if you want inline comments, rename to `opencode.jsonc` and confirm OpenCode is pointed at it |
| Filesystem MCP: "permission denied" reading a file that's clearly readable | Path is outside the allowed root passed in `command`, or OneDrive has the file locked mid-sync | Check the root arg matches `$KioRoot` exactly; pause OneDrive sync |
| Git MCP: not detected / `uvx: command not found` | `uv` wasn't installed, or PATH wasn't refreshed | Rerun the `uv` installer from Phase 1, open a **new** PowerShell window (PATH changes don't apply to already-open shells) |
| Memory MCP: doesn't persist across sessions | Expected if you're running with a fresh profile/container each time, or if `enabled` got flipped by a project-level override | Confirm memory's storage location isn't being wiped by a cleanup script; check `enabled: true` in global config specifically |
| Sequential Thinking: "unavailable" / tool not called | Not a connectivity issue — the model has to *choose* to invoke it; some prompts don't trigger it | Ask explicitly: "use sequential thinking to..." |
| Windows path issues (`\` vs `/`) in JSON | JSON requires escaped backslashes: `C:\\Users\\...`, not `C:\Users\...` | Always double-escape backslashes in path strings inside `.json` files, or use forward slashes (`C:/Users/...`) which Node accepts fine on Windows |
| OneDrive-specific: install/config changes don't seem to "stick" | OneDrive syncing an older cached copy over your edit | Right-click `kio_final` → "Always keep on this device"; check the OneDrive sync icon shows fully synced (green check) before assuming a file change failed |
| Corporate/network firewall or proxy blocking npm registry | `npx` hangs or times out fetching a package | Set npm's proxy: `npm config set proxy http://<proxy>:<port>` and `npm config set https-proxy http://<proxy>:<port>`; same firewall issue affects `uv`/`uvx` — check `uv` proxy env vars (`HTTPS_PROXY`) if it also hangs |

---

## Phase 8 — Security Hardening

**Configuration boundary (mechanical, not habit-based):**

- All six MCP definitions live in **global** config (`%USERPROFILE%\.config\opencode\opencode.json`) only. Project config (`<KioRoot>\opencode.json`) carries no `mcp` block, ever.
- `filesystem`'s allowed root is scoped to `$KioRoot` specifically — never `C:\Users\<USER>\` or a drive root. This is least-privilege: the server literally cannot read/write outside that directory, regardless of what the model is tricked into asking for.
- `git`'s `--repository` flag is similarly scoped to the KIO repo, not a general git-anywhere tool.

**Preventing rogue MCP execution from cloned repos** (this is the specific risk you and I already discussed for `external/`):

1. Never run `opencode` from inside a freshly cloned repo before inspecting it:
   ```powershell
   Get-ChildItem -Path <cloned-repo-path> -Recurse -Include opencode.json,opencode.jsonc,mcp.json -ErrorAction SilentlyContinue
   ```
   If this returns anything, open and read it before running `opencode` in that directory.
2. Because your global `mcp` block already claims the names `filesystem`, `git`, `memory`, `sequential-thinking`, `context7`, `playwright`, a malicious project-level config **cannot silently redefine those** — OpenCode's project config can only add new server names or, per its own docs, override specific keys of an existing name, so treat step 1's grep as mandatory, not a backstop.
3. Keep `enabled: false` as your default reflex for anything unfamiliar you find in a cloned repo's config — don't flip it to `true` without reading exactly what `command` it runs.

**Windows Defender exclusions**: none required or recommended for this stack. Do **not** exclude `npx`'s npm cache directory or `uvx`'s tool cache from Defender scanning — that cache is exactly where a malicious package would land, and it's a low-cost scan target. The one legitimate performance exclusion, if you find `npm install`/`npx` unusually slow, is excluding your project's build output directories (not source, not caches) — not relevant to this six-server stack.

**Rollback procedure**: see `backup-mcps.ps1` / `restore-mcps.ps1` in Phase 9 — always back up the global config before hand-editing it.

---

## Phase 10 — Final Validation Checklist

Run `verify-mcps.ps1` (Phase 9 scripts) for the automated version. Manual checklist:

- [ ] `node -v`, `npm -v`, `npx -v` all print versions
- [ ] `git --version` prints
- [ ] `uv --version`, `uvx --version` print
- [ ] `Get-ExecutionPolicy -List` shows `RemoteSigned` or less restrictive for `CurrentUser`
- [ ] `opencode --version` prints
- [ ] `opencode mcp list` shows all six servers as enabled
- [ ] `/mcp` inside an OpenCode session shows all six connected
- [ ] Filesystem test prompt returns a real KIO directory listing
- [ ] Git test prompt returns real branch/commit data
- [ ] Memory test prompt persists a fact across two sessions
- [ ] Sequential Thinking test prompt shows a visible reasoning trace
- [ ] Context7 test prompt returns current, non-generic docs
- [ ] Playwright test prompt successfully launches a browser and returns a page title
- [ ] `CONTEXT7_API_KEY` confirmed set at User scope and picked up (no 401)
- [ ] Global config (`%USERPROFILE%\.config\opencode\opencode.json`) contains the `mcp` block; project config does not
- [ ] `external/`-clone security check (Phase 8, step 1) understood and will be run before opening any newly cloned repo in OpenCode
- [ ] Backup of global config exists in `%USERPROFILE%\.kio-mcp-backups\`

If every box is checked: production ready for this six-server stack. Nothing here blocks or unblocks Gate C-09 — that's still the actual bottleneck.
