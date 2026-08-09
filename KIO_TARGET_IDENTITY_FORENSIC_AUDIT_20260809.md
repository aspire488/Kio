# KIO Execution-System Forensic Audit — Target Identity, Verification & Response Truthfulness

Date: 2026-08-09 · Scope: whole action lifecycle · Read-only (no code changes in this document)

---

## 1. Executive summary

The live bug `Open ChatGPT` → `Close it` → *whole Chrome session killed* is not a
Chrome bug and not a response-text bug. It is the visible symptom of a systemic
defect: **KIO collapses distinct target kinds (web-app tab, browser process,
application) into a single string `target`, and the string is corrupted
(`chrome::open_url::https://chat.openai.com::chatgpt`) as it travels through
resolution → execution → verification → context → response.**

Every step of that corruption is proven below with file/line evidence.

---

## 2. Actual runtime call graph (as-built)

```
Telegram update (kio_bot.py)
  └─ route/route_request (command_router.py)
      └─ dispatch_channel_input (runtime.py)
          ├─ InputNormalizer + context_manager.get_session_context
          └─ handle_command (command_router.py)
              └─ Pipeline.run (pipeline/__init__.py)
                  ├─ _NormalizationService.run      (emoji/alias/politeness + resolved_text pronouns)
                  ├─ _IntentClassifier.classify     (deterministic rule cascade)
                  ├─ _CapabilityResolver.resolve    (intent -> capability name + params)
                  ├─ _ExecutionCoordinator.execute  (dispatch by capability)
                  │    ├─ desktop  -> execution_boundary.execute_action
                  │    ├─ browser  -> command_router connector helpers / execute_action
                  │    ├─ media    -> MediaManager
                  │    ├─ coordinator -> parse_command + command_router._execute_multi_step
                  │    └─ conversation/knowledge/memory/system/file
                  └─ _ResponseComposer.compose     (ctx.update + remember_runtime_context)
              └─ format_result (runtime_response_formatter.py)   ← final user text
              └─ format_channel_reply (runtime.py)
```

---

## 3. The `Open ChatGPT` path (line-by-line evidence)

| # | Stage | File:line | What happens |
|---|-------|-----------|--------------|
| 1 | classifier | `pipeline/__init__.py` `_detect_open` | `get_browser_routing("chatgpt")` |
| 2 | routing | `routing_utils.py:180-201` `get_browser_routing` | `canonicalize("chatgpt")` → `browser_session_registry._TARGET_URLS["chatgpt"]="https://chat.openai.com"` → **`target = "chrome::open_url::https://chat.openai.com::chatgpt"`** (line 215) |
| 3 | resolver | `pipeline/__init__.py` `_CapabilityResolver.resolve` | `("browser", {"action":"execute_capability","target":"chrome::open_url::..."})` — **metadata `canonical_target`/`browser` is dropped** |
| 4 | execution | `pipeline/__init__.py` `_exec_browser` → `execute_action("execute_capability", ...)` | goes through `execution_boundary.execute_action` → `app_operator.execute_capability` |
| 5 | operator | `app_operator.py:1804+` `execute_capability` | splits `::` → connector `open_tab(url)` → ACK → **`verification_mode: "noop"`**, `capability_name:"Chatgpt"`, `browser:"chrome"`, message `"Opened ChatGPT in Chrome."` |
| 6 | context | `context_manager.py` `update()` (≈line 574) | stores `result["target"]` **verbatim** = `chrome::open_url::https://chat.openai.com::chatgpt` into `active_entity`/`last_target` |
| 7 | context | `pipeline/__init__.py` `_ResponseComposer.compose` (end) | `remember_runtime_context("execution", {"target": result.get("target")...})` — same raw string |
| 8 | response | `runtime_response_formatter.py` `format_capability` | message already natural → `_is_natural` true → returned unchanged ("Opened ChatGPT in Chrome.") |

### Root cause A (open): **target identity is destroyed at resolution.**
The pipeline turns a *web-app request* into a *serialized routing string*
(`browser::capability::url::name`) and treats that string as the *target*. The
structured identity (browser=chrome, url, friendly_name=chatgpt) exists only in
local variables inside `execute_capability` and is lost once the result is
normalized — the result `target` is the raw serialized string.

---

## 4. The `Close it` path (line-by-line evidence)

| # | Stage | File:line | What happens |
|---|-------|-----------|--------------|
| 1 | pronoun | `context_manager.py` `resolved_text` G5 (≈line 560) | `re.sub(r"\b(it|that|this)\b", self.active_entity, "close it")` → **"close chrome::open_url::https://chat.openai.com::chatgpt"** |
| 2 | classifier | `pipeline/__init__.py` `_detect_close` | target is not a bare browser name → `RoutingDecision(BROWSER_FOCUS, "close_tab", raw_serialized_string)` |
| 3 | resolver | `_CapabilityResolver.resolve` | `("browser", {"action":"close_tab","target": raw_serialized_string})` |
| 4 | execution | `pipeline/__init__.py` `_exec_browser` close_tab | `conn.close_tab(raw_serialized_string)` fails (no tab matches that text) → **falls through to `execute_action("close_app", raw_serialized_string)`** |
| 5 | collapse | `app_operator.py:596` `close_app` | **`if "::" in key: key = key.split("::")[0]`** → key = **"chrome"** |
| 6 | escalation | `app_operator.py` process-discovery fallback | `_find_matching_process_pid("chrome", info)` → discovers newest chrome root → `close_app("chrome", pid=...)` → **terminates the entire Chrome session** |
| 7 | response | `runtime_response_formatter.py` `format_close_app` | `target.strip().capitalize()` → **"Closed Chrome::open_url::https://chat.openai.com::chatgpt, but some background processes are still running."** |

### Root cause B (close): **scope escalation + target collapse.**
Two independent defects combine:
1. `close_tab` escalates to `close_app` when the tab isn't found (tab-scope → process-scope).
2. `close_app` truncates capability strings to the *browser process name* and then kills it.

### Root cause C (response): **raw internal serialization leaks to the user.**
The user-facing close formatter capitalizes the raw `target` string. Nothing
between `execute_capability` and `format_close_app` ever converts the internal
`browser::open_url::url::name` serialization back to a friendly name.

---

## 5. Systematic audit of every stage

### 5.1 Target model
**No canonical target representation exists.** The pipeline threads a single
`str target` from classification to response. Target kinds (app/browser/tab/
webapp/media/file) are encoded *ad hoc*:
- capability serializations `browser::cap::url::name` (3 producers: `command_parser.py:260/264`,
  `routing_utils.py:215`, `pipeline/__init__.py:364`)
- URL strings
- registry keys
- friendly names

**Consequence:** any consumer that receives a `target` must guess its kind.
`close_app` guesses wrong (`::` → browser process). `_extract_url_name` guesses
(heuristic). Context referents store the raw serialization.

### 5.2 Reference/pronoun model
`context_manager` `active_entity`/`last_target` are raw target strings; pronoun
splicing (`it/that/this`) blindly substitutes them into a new command. **No type
information, no canonical identity, no validity window.** `get_last_successful_interaction`
(runtime buffer) stores the raw `target` too.

### 5.3 Action model
Actions are loose strings (`open`, `close`, `play`, `focus`, `close_tab`,
`execute_capability`). There is no per-action declaration of *target granularity*
or *success invariant*. `_ACTION_MAP` (execution_boundary.py) maps `close→close_app`,
`focus→focus`(browser), etc.

### 5.4 Execution model
`execution_boundary.execute_action` is the single side-effect gate with safety
policy + RAM check + result normalization + probe. **Good architecture — but the
verification probes are almost all "noop"**:
- `register_verification_probe("open_app", process_liveness_probe)` ✓
- `register_verification_probe("close_app", exit_code_probe)` ✓
- everything else → `_default_probe` → `noop_probe` (pass-through on operator success)
- `execute_capability` explicitly requests `verification_mode: "noop"`

### 5.5 Verification model
`VerificationCode` enum exists (protocol.py) and `state_verification.py` provides
VerifiedConnector for the media path. **But app/browser path does not use it.**
Open = "the connector ACKed" (no tab identity check). Close = "one PID is gone".

### 5.6 Result/outcome model
Rich but disconnected: `execution_boundary` computes `outcome_class`,
`verification_status`, `failure_class`, `probe_used` — yet:
- `_ResponseComposer` ignores them (uses raw message/target)
- `format_result` uses only `action/target/success/details.message`
- multi-step `_summarize_steps` ignores per-step verification entirely

### 5.7 Response-generation model
`runtime_response_formatter.format_result` → per-action formatters. **Leakage is
possible whenever `target` is a serialized capability string**, because
`format_open_app`/`format_close_app` capitalize the raw target. `format_capability`
and `_extract_url_name` handle `::` correctly; `format_open_app`/`format_close_app`
do not.

### 5.8 Async model
`kio_bot.py` uses `concurrent_updates(4)` + `asyncio.to_thread` for media ops.
Long media ops no longer block other messages (verified live: Hi during media →
1.7s). **Remaining risk:** `_execute_multi_step` runs steps sequentially on the
dispatcher thread (a multi-step browser task can still stall chat; acceptable
for now, noted in remaining issues).

### 5.9 Multi-action model
`_execute_multi_step` (command_router.py) + `parse_command`. Defects:
- **`_summarize_steps` reports "done - opened X and Y" without per-step
  verification** (it reads `result["success"]`, which for `execute_capability`
  is the noop ACK).
- Steps that fail cause an **early return** (`Step N failed`) that aborts the
  remaining independent actions.
- Blocked vs failed vs success is not reflected truthfully in the summary.

### 5.10 Browser/application model
`capability_registry` (Gate 5.1) exists and tracks `canonical_target/browser/url/
browser_pid/active` — **the correct store for web-app sessions**. `routing_utils.
resolve_capability_for_close` exists. **But `close_app` bypasses it** (the `::`
collapse happens before any capability lookup). `close_browser_capability` has a
SAFETY GATE (no isolated profile → blocked) — good, but unreachable from the bug path.

---

## 6. Bug classes (root causes, ranked)

| ID | Class | Severity | Evidence | Owning layer |
|----|-------|----------|----------|--------------|
| BC-1 | Target collapse (`::`→browser process) | **CRITICAL** | `app_operator.py:596` | close/process |
| BC-2 | Tab→app scope escalation | **CRITICAL** | `pipeline/__init__.py` `_exec_browser` close_tab fallback | browser execution |
| BC-3 | Raw serialized targets stored as conversational referents | HIGH | `context_manager.update`, composer `remember_runtime_context` | context |
| BC-4 | Unverified open (noop) | HIGH | `execute_capability` `verification_mode:"noop"`; probe registry | execution/verification |
| BC-5 | Response leakage of internal serialization | HIGH | `format_close_app`/`format_open_app` capitalize raw target | response |
| BC-6 | Multi-action false-success summary + early abort | HIGH | `_summarize_steps`, `_execute_multi_step` | coordinator |
| BC-7 | Duplicate target-URL sources (3 competing maps) | MEDIUM | `command_parser` dict, `browser_session_registry._TARGET_URLS`, `app_operator.WEB_URLS/WEB_DOMAIN_ALIASES` | resolution |
| BC-8 | Verification not capability-specific | MEDIUM | probe registry only has open/close | verification |
| BC-9 | close_tab fallback reaches close_app (even when connector absent) | MEDIUM | same as BC-2 | browser execution |
| BC-10 | `not_tracked` refusal ("I didn't open it") for web-app closes | MEDIUM | `close_app` no-ownership branch | close |

---

## 7. Existing mechanisms to reuse (NOT duplicate)

1. `capability_registry` (Gate 5.1) — web-app session store with identity. **Owns close.**
2. `routing_utils.resolve_capability_for_close` / `close_browser_capability` / `deactivate_capability` — capability-close path (with isolated-profile safety gate).
3. `runtime_response_formatter._extract_url_name` — capability-string → friendly name (extend to a general `safe_target_name`).
4. `state_verification.VerifiedConnector` + `VerificationCode` — generic verification pipeline (media already uses it).
5. `execution_boundary` probes + outcome taxonomy — extend registration, don't fork.
6. `window_activation` — native-app focus (Capability A).
7. `media_registry` — current media state (Capability C).

---

## 8. Minimal system-level fix plan

1. **New `target_ref.py`**: canonical parse of capability strings → `{kind, name, browser, url, pid}` + `safe_target_name()` (display-only, never leaks URL/`::`).
2. **`close_app`**: remove `::` collapse; capability/web targets resolve via capability registry → tab/session close with safety gate; never blind browser kill. Web-app names without a session → truthful "not running/found" rather than process refusal.
3. **`_exec_browser.close_tab`**: never escalate to `close_app`; truthful failure when tab not found.
4. **Context/composer**: store `safe_target_name()` as referent (never raw serialization).
5. **Formatters**: `format_open_app`/`format_close_app` use `safe_target_name()`.
6. **Multi-step**: per-step verified outcomes; no early abort; truthful partial summary ("Opened ChatGPT, but I couldn't open Telegram.").
7. **Verify**: register a `tab_identity` probe for web opens (bounded) instead of `noop`.

---

## 9. Targeted test plan

- target_ref parse/safe-name unit tests
- close_app capability target → capability-close path (no chrome.exe kill), webapp name → truthful not-running
- close_tab no-escalation (unit: connector missing → truthful failure, no execute_action close_app)
- context referent sanitization
- formatter safe-name for raw serialized targets
- multi-step summary truthfulness (partial/full success, no "done -" false success)
- classifier: what's open / focus / now_playing intents
- media now_playing state

## 10. Live verification matrix

1. `Open ChatGPT` → verify tab; 2. `Close it` → ChatGPT **tab** closes, Chrome stays; 3. `What's open?`; 4. `Switch to Telegram`/`Focus`; 5. `Play X` → `Pause it` → `What's playing?` → `Resume it`; 6. `Open ChatGPT and Telegram` → truthful per-step; 7. `Hi` during a long action → responsive.

---

## 11. Regression risks

- `execute_capability` callers expecting `target` to round-trip (multi-step close) — mitigated by resolving through capability registry instead of string surgery.
- Tests asserting old message formats — update to safe names.
- `close_app` "not tracked" refusal tests — now route web apps truthfully; registry apps unchanged.
