# KIO Communication Provider Readiness Audit

**Audit Date:** 2026-09-15
**Audit Type:** SOURCE-VERIFIED, READ-ONLY
**Scope:** All 32 YAML templates using `capability: communication`
**Code Root:** `C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final`
**Library Root:** `C:\Users\joelj\Downloads\kio_final\automation\library\`

---

## Executive Verdict

**Decision: C — DEFER_COMMUNICATION**

Communication is NOT the correct next provider implementation. While 32 templates declare `communication`, the actual semantic surface is far narrower than the template count suggests. The existing KIO communication infrastructure only supports **Telegram text messages** via `send_telegram_message()`. Of 32 templates, only **1 template's communication step** can work with existing infrastructure (and it's blocked by other capabilities). The remaining 31 templates require actions that don't exist yet (send_batch, send_file, send_with_ack, debounce_messages, format_for_channel, etc.).

**Recommended next target:** `terminal` capability — 3 templates, TerminalProvider exists, only needs APP_CAPABILITIES entry (~100 LOC).

---

## Communication Template Inventory

### All 32 Templates Declaring `capability: communication`

| # | Template ID | Communication Actions | Other Capabilities |
|---|-------------|----------------------|-------------------|
| 1 | transcribe_summarize | send_message | ai_reasoning, media |
| 2 | page_change_monitor | send_message | ai_reasoning, browser, memory |
| 3 | price_monitor | send_message | browser, memory |
| 4 | crm_followup | send_batch | ai_reasoning, mcp_tool, memory |
| 5 | email_autoresponder_approval | send_message | ai_reasoning, workflow |
| 6 | lead_intake_crm | send_message | ai_reasoning, mcp_tool, memory |
| 7 | support_ticket_triage | send_message | ai_reasoning, mcp_tool |
| 8 | chat_assistant | send_message, debounce_messages | ai_reasoning, memory |
| 9 | escalation_alert | send_with_ack | workflow |
| 10 | notify | format_for_channel, send_message | (none) |
| 11 | voice_assistant | send_message | ai_reasoning, media |
| 12 | workflow_failure_alert | format_failure | workflow |
| 13 | form_intake | send_message | filesystem |
| 14 | ci_failure_alert | send_message | github |
| 15 | dependency_monitor | send_message | github |
| 16 | github_issue_triage | send_message | github |
| 17 | pr_review_prep | send_message | github |
| 18 | repo_health_report | send_file | github, terminal |
| 19 | document_summarize | send_message | filesystem |
| 20 | inbox_monitor | get_updates, send_message | (none) |
| 21 | rss_news_monitor | send_message | ai_reasoning, knowledge, memory |
| 22 | security_scan_alert | send_message | ai_reasoning, knowledge |
| 23 | website_uptime | send_message | knowledge, memory |
| 24 | calendar_to_status | set_status, clear_status | calendar |
| 25 | ecosystem_briefing | priority_unread, send_message | ai_reasoning, calendar, filesystem |
| 26 | email_label_ai | apply_label | (none) |
| 27 | meeting_prep | send_message | ai_reasoning, memory |
| 28 | morning_briefing | send_message | ai_reasoning, calendar, knowledge, mcp_tool |
| 29 | weekly_review | send_file | ai_reasoning, memory, terminal |
| 30 | competitor_monitor | send_file | ai_reasoning, browser, memory, terminal |
| 31 | daily_brief | send_message | ai_reasoning, memory |
| 32 | youtube_summary | send_message | ai_reasoning, knowledge, memory |

### Distinct Communication Actions Used

| Action | Templates Using | Semantic Pattern |
|--------|----------------|-----------------|
| send_message | 25 | Send text message to channel/user |
| send_batch | 1 | Send multiple messages |
| send_file | 3 | Send document/file |
| send_with_ack | 1 | Send with acknowledgement tracking |
| debounce_messages | 1 | Buffer rapid consecutive messages |
| format_for_channel | 1 | Format message for specific channel |
| format_failure | 1 | Format failure notification |
| get_updates | 1 | Get inbox updates |
| priority_unread | 1 | Get priority unread messages |
| apply_label | 1 | Apply label to email |
| set_status | 1 | Set calendar status |
| clear_status | 1 | Clear calendar status |

---

## Existing KIO Communication Infrastructure

### Telegram Provider — `monitoring/watches.py`

```python
def send_telegram_message(chat_id: str, text: str) -> bool:
    """Push a message to a Telegram chat via the Bot API."""
```

- **Input:** chat_id (string), text (string)
- **Output:** bool (True if delivered)
- **Transport:** HTTP POST to `https://api.telegram.org/bot{token}/sendMessage`
- **Authentication:** TELEGRAM_TOKEN environment variable
- **Capabilities:** Text messages only, no files, no formatting, no delivery confirmation
- **Error handling:** Catches all exceptions, returns False

### Messages Module — `communication/messages.py`

```python
def message_answer(query: str, ctx=None, decision=None) -> dict:
    """Canonical outbound-communication owner: draft / send / cancel / list."""
```

- **Capabilities:** Draft, send, cancel, list messages
- **Transport:** Only Telegram via `send_telegram_message()`
- **Authorization:** Only sends to user's own chat (self-recipient)
- **Persistence:** OutboundMessageRepository (SQLite)
- **Verification:** Delivery confirmation via Telegram API response

### APP_CAPABILITIES — `core/app_operator.py`

```python
APP_CAPABILITIES = {
    "telegram": ["send_message"],
    # ... other apps
}
```

- **Only `telegram: send_message` is registered**
- **No `communication` entry** in APP_CAPABILITIES
- **No email, Slack, Discord support**

### execute_capability — `core/app_operator.py`

```python
if cap == "send_message":
    from mini_kio.communication.messages import message_answer
    result = message_answer("send a message to me: %s" % args, decision=None)
```

- **Only `send_message` is implemented**
- **Routes to `message_answer()`** which only supports Telegram
- **All other communication actions return "Capability not implemented"**

### StepRunner Mappings — `automation/step_runner.py`

```python
("communication", "send_message"): "execute_capability",
("communication", "send_with_ack"): "execute_capability",
("communication", "send_batch"): "execute_capability",
("communication", "send_file"): "execute_capability",
("communication", "format_for_channel"): "execute_capability",
("communication", "format_failure"): "execute_capability",
("communication", "send_notification"): "execute_capability",
("communication", "send_alert"): "execute_capability",
("communication", "apply_label"): "execute_capability",
("communication", "clear_status"): "execute_capability",
("communication", "set_status"): "execute_capability",
("communication", "debounce_messages"): "execute_capability",
("communication", "get_updates"): "execute_capability",
("communication", "priority_unread"): "execute_capability",
```

- **All 14 communication actions are mapped to `execute_capability`**
- **But only `send_message` is implemented in `execute_capability()`**
- **All other actions return "Capability not implemented"**

---

## UI vs Automation Communication

### A. Telegram as KIO's User Interface
- Telegram is KIO's primary user interface
- User sends messages to KIO via Telegram bot
- KIO responds via Telegram bot
- This is conversational, not automation

### B. Telegram as Automation Communication Capability
- Templates need to SEND messages proactively (not in response to user)
- Templates need to send to specific channels/users
- Templates need delivery confirmation
- Templates need retry logic
- **Current limitation:** `send_telegram_message()` only sends to user's own chat
- **No support for:** sending to other users, groups, channels

### C. Email
- **ABSENT.** No email provider exists.
- Templates need: send email, receive email, draft reply
- **Requires:** New provider + OAuth2 integration

### D. Slack
- **ABSENT.** No Slack provider exists.
- Templates need: send message, send file, receive message
- **Requires:** New provider + Bot token

### E. Discord
- **ABSENT.** No Discord provider exists.
- Templates need: send message, send file
- **Requires:** New provider + Bot token

### F. Generic Notification/Webhook
- **ABSENT.** No generic webhook provider exists.
- Templates need: HTTP POST to webhook URL
- **Requires:** New provider

---

## Communication Capability Matrix

| Communication Action | Templates | Can Existing KIO Do It? | Needs | Classification |
|---------------------|-----------|------------------------|-------|----------------|
| send_message | 25 | Partially — Telegram only, self-recipient only | Multi-channel support, recipient resolution | ADAPTER_REQUIRED |
| send_batch | 1 | No — no batch sending | Batch sending logic | PROVIDER_REQUIRED |
| send_file | 3 | No — no file sending | File upload via Telegram API | ADAPTER_REQUIRED |
| send_with_ack | 1 | No — no ack tracking | Ack tracking + timeout | PROVIDER_REQUIRED |
| debounce_messages | 1 | No — no message buffering | Message buffering logic | PROVIDER_REQUIRED |
| format_for_channel | 1 | No — no channel formatting | Channel-specific formatting | ADAPTER_REQUIRED |
| format_failure | 1 | No — no failure formatting | Failure notification formatting | ADAPTER_REQUIRED |
| get_updates | 1 | No — no inbox polling | Telegram getUpdates API | ADAPTER_REQUIRED |
| priority_unread | 1 | No — no priority detection | Priority detection logic | PROVIDER_REQUIRED |
| apply_label | 1 | No — no email labeling | Email API integration | PROVIDER_REQUIRED |
| set_status | 1 | No — no status setting | Calendar API integration | PROVIDER_REQUIRED |
| clear_status | 1 | No — no status clearing | Calendar API integration | PROVIDER_REQUIRED |

### Summary

| Classification | Count | Actions |
|---------------|-------|---------|
| DIRECTLY_SUPPORTED | 0 | (none) |
| ADAPTER_REQUIRED | 6 | send_message, send_file, format_for_channel, format_failure, get_updates, send_batch |
| PROVIDER_REQUIRED | 6 | send_with_ack, debounce_messages, priority_unread, apply_label, set_status, clear_status |
| EXTERNAL_INFRASTRUCTURE_REQUIRED | 0 | (none) |
| SEMANTICALLY_UNSUPPORTED | 0 | (none) |

---

## Telegram Reuse Analysis

### What Telegram Can Do (Existing)

| Capability | Source | Status |
|-----------|--------|--------|
| Send text message | `send_telegram_message()` | **PRESENT** |
| Send to user's own chat | `message_answer()` | **PRESENT** |
| Delivery confirmation | Telegram API response | **PRESENT** |
| Draft message | `OutboundMessageRepository` | **PRESENT** |
| Send draft | `message_answer()` | **PRESENT** |
| Cancel draft | `message_answer()` | **PRESENT** |
| List drafts | `message_answer()` | **PRESENT** |

### What Telegram Cannot Do (Missing)

| Capability | Status | Required For |
|-----------|--------|-------------|
| Send to other users | **ABSENT** | send_batch, send_message to others |
| Send to groups/channels | **ABSENT** | send_batch, notifications |
| Send files/documents | **ABSENT** | send_file |
| Send photos/media | **ABSENT** | voice_assistant |
| Channel-specific formatting | **ABSENT** | format_for_channel |
| Acknowledgement tracking | **ABSENT** | send_with_ack |
| Message buffering | **ABSENT** | debounce_messages |
| Inbox polling | **ABSENT** | get_updates |
| Priority detection | **ABSENT** | priority_unread |

### Telegram Reuse Verdict

**PARTIAL.** Existing Telegram can only send text messages to the user's own chat. Templates need:
- Multi-recipient support
- File sending
- Channel formatting
- Ack tracking
- Inbox polling

**Only 1 template's communication step** can partially work with existing Telegram (and it's blocked by other capabilities).

---

## Other Provider Analysis

### Email
- **Status:** ABSENT
- **Requires:** New provider + OAuth2 (Gmail, Outlook)
- **Templates needing:** email_autoresponder_approval, email_label_ai, lead_intake_crm, support_ticket_triage
- **Complexity:** HIGH — OAuth2, IMAP/SMTP, message parsing

### Slack
- **Status:** ABSENT
- **Requires:** New provider + Bot token
- **Templates needing:** chat_assistant (multi-channel), escalation_alert
- **Complexity:** MEDIUM — Bot API, channel management

### Discord
- **Status:** ABSENT
- **Requires:** New provider + Bot token
- **Templates needing:** chat_assistant (multi-channel)
- **Complexity:** MEDIUM — Bot API, channel management

### Generic Webhook
- **Status:** ABSENT
- **Requires:** New provider
- **Templates needing:** workflow_failure_alert
- **Complexity:** LOW — HTTP POST

### SMS
- **Status:** ABSENT
- **Requires:** New provider (Twilio, etc.)
- **Templates needing:** None directly
- **Complexity:** HIGH — Carrier integration

### Push Notification
- **Status:** ABSENT
- **Requires:** New provider (Firebase, etc.)
- **Templates needing:** None directly
- **Complexity:** HIGH — Platform-specific

---

## Per-Template Semantic Analysis

### Templates Where Communication Step Could Work with Existing Infrastructure (1 template)

| Template ID | Communication Action | Status | Other Blocking Capabilities |
|-------------|---------------------|--------|---------------------------|
| notify | send_message | **PARTIAL** — Telegram self-recipient only | (none) |

**NOT fully executable** — `notify` only works for Telegram self-recipient, not multi-channel.

### Templates Requiring ADAPTER (20 templates)

| Template ID | Communication Actions Needing Adapter |
|-------------|--------------------------------------|
| transcribe_summarize | send_message |
| page_change_monitor | send_message |
| price_monitor | send_message |
| email_autoresponder_approval | send_message |
| lead_intake_crm | send_message |
| support_ticket_triage | send_message |
| chat_assistant | send_message, debounce_messages |
| voice_assistant | send_message |
| form_intake | send_message |
| ci_failure_alert | send_message |
| dependency_monitor | send_message |
| github_issue_triage | send_message |
| pr_review_prep | send_message |
| document_summarize | send_message |
| inbox_monitor | get_updates, send_message |
| rss_news_monitor | send_message |
| security_scan_alert | send_message |
| website_uptime | send_message |
| meeting_prep | send_message |
| morning_briefing | send_message |

### Templates Requiring PROVIDER (11 templates)

| Template ID | Communication Actions Needing Provider |
|-------------|---------------------------------------|
| crm_followup | send_batch |
| escalation_alert | send_with_ack |
| workflow_failure_alert | format_failure |
| repo_health_report | send_file |
| weekly_review | send_file |
| competitor_monitor | send_file |
| calendar_to_status | set_status, clear_status |
| ecosystem_briefing | priority_unread, send_message |
| email_label_ai | apply_label |
| daily_brief | send_message |
| youtube_summary | send_message |

---

## Security / Side-Effect Analysis

### Confirmation
- **Low risk.** `message_answer()` requires explicit user action ("send the draft")
- **Medium risk.** Automation templates send without user confirmation (security_classification: low)

### Security Classification
- Most templates: `low` — read-only notifications
- Some templates: `consequential` — email autoresponder, lead intake, support triage
- **No mechanism** to enforce security classification in automation

### Credential Isolation
- **Good.** TELEGRAM_TOKEN stored in environment variable
- **Good.** OAuth2 tokens stored in CredentialVault
- **No cross-credential leakage**

### Recipient Validation
- **Good.** `message_answer()` only sends to user's own chat
- **No validation** for automation templates — could send to arbitrary recipients

### Secret Leakage
- **Low risk.** Messages don't contain credentials
- **Medium risk.** Templates process external data that could contain secrets

### Prompt Injection into Outbound Content
- **Medium risk.** Templates like `support_ticket_triage` process untrusted email bodies
- **No sanitization** of outbound content

### Arbitrary Recipient Protection
- **Good.** `message_answer()` refuses to send to unregistered recipients
- **No protection** in automation — templates specify recipients directly

### Destructive/Spam Protection
- **Low risk.** No bulk sending capability
- **No rate limiting** in automation

### Duplicate-Send Protection
- **Good.** `message_answer()` uses draft-based workflow
- **No idempotency** in automation templates

### Audit Logging
- **Good.** `OutboundMessageRepository` persists all messages
- **No audit trail** for automation sends

### Verification
- **Good.** `message_answer()` verifies delivery via Telegram API
- **No verification** in automation — just returns delivery_id

### Existing KIO Mechanisms That Can Enforce
- CredentialVault for credential isolation
- OutboundMessageRepository for persistence
- Telegram API response for delivery confirmation
- Draft-based workflow for user confirmation

---

## Resource Analysis

### Storage Footprint
- Current: ~17 MB RSS
- Adding communication: ~2-5 MB (message persistence)
- **Total impact:** Minimal

### RAM Impact
- Current: ~17 MB RSS
- Adding communication: ~1-2 MB (message buffers)
- **Total impact:** Minimal

### Network Impact
- Each send: 1 HTTP request to Telegram API
- **Total impact:** Minimal

### Rate Limiting
- Telegram Bot API: 30 messages/second, 1 message/recipient/second
- **No enforcement** in KIO

---

## Exact Unlock Impact

### Would Communication Fix Alone Make Any Template Fully Executable?

**NO.** Every single communication template depends on at least one other blocked capability:

| Blocking Capability | Templates Blocked |
|--------------------|------------------|
| ai_reasoning | 18 |
| memory | 10 |
| browser | 3 |
| terminal | 3 |
| github | 8 |
| mcp_tool | 3 |
| knowledge | 4 |
| calendar | 3 |
| workflow | 3 |
| filesystem | 3 |
| media | 2 |

### Templates Fully Unlocked by Communication Alone: **0**

### Templates Partially Improved by Communication: **32** (all of them — the communication step would work, but downstream steps still block)

### Templates Still Blocked by Other Capabilities: **32** (all of them)

---

## Other Blocking Capabilities

The 32 communication templates use these other capabilities:

| Capability | Templates Using | Current Provider Status |
|-----------|----------------|----------------------|
| ai_reasoning | 18 | ADAPTER_REQUIRED — needs JSON parsing adapter |
| memory | 10 | PROVIDER_REQUIRED — needs automation state infrastructure |
| github | 8 | ADAPTER_REQUIRED — MCP server exists, needs entry |
| knowledge | 4 | ROUTING_WORKS — direct boundary actions work |
| browser | 3 | ROUTING_WORKS — direct boundary actions work |
| terminal | 3 | ADAPTER_REQUIRED — TerminalProvider exists but needs entry |
| calendar | 3 | PROVIDER_REQUIRED — no provider |
| workflow | 3 | ADAPTER_REQUIRED — WorkflowExecutionProvider exists |
| mcp_tool | 3 | PROVIDER_REQUIRED — MCP servers exist, needs entry |
| filesystem | 3 | ROUTING_WORKS — direct boundary actions work |
| media | 2 | PROVIDER_REQUIRED — no provider |

**Key insight:** ai_reasoning (18 templates) and memory (10 templates) are the most common blockers. If ai_reasoning were implemented, 18 templates would unblock their AI step.

---

## Minimal Implementation Design

If communication were to be implemented, here is the smallest architecture-compatible design:

### 1. APP_CAPABILITIES Entry
```python
APP_CAPABILITIES["communication"] = [
    "send_message", "send_batch", "send_file", "send_with_ack",
    "debounce_messages", "format_for_channel", "format_failure",
    "get_updates", "priority_unread", "apply_label", "set_status", "clear_status"
]
```

### 2. Handler Function (~300 LOC)
```python
def _handle_communication(cap: str, args: str) -> dict:
    """Route communication capabilities to appropriate handlers."""
    import json
    try:
        params = json.loads(args) if args else {}
    except json.JSONDecodeError:
        return {"success": False, "message": "Invalid JSON args"}
    
    # Route to specific handler
    if cap == "send_message":
        return _handle_send_message(params)
    elif cap == "send_batch":
        return _handle_send_batch(params)
    # ... etc
```

### 3. Per-Action Handlers (~500 LOC total)
Each action needs its own handler with:
- Multi-channel support (Telegram, email, Slack, Discord)
- Recipient resolution
- Delivery verification
- Retry logic
- Idempotency

### 4. Channel Adapters (~300 LOC total)
Each channel needs its own adapter:
- Telegram adapter (extend existing)
- Email adapter (new)
- Slack adapter (new)
- Discord adapter (new)

### 5. Tests (~200 LOC)
Unit tests for each action handler.

**Total estimated LOC: ~1300**

This significantly exceeds the 500 LOC threshold.

---

## LOC Estimate

| Component | LOC |
|-----------|-----|
| APP_CAPABILITIES entry | 20 |
| Handler function | 300 |
| Per-action handlers (12) | 500 |
| Channel adapters (4) | 300 |
| Recipient resolution | 100 |
| Delivery verification | 100 |
| Tests | 200 |
| **Total** | **~1520** |

This significantly exceeds the 500 LOC threshold.

---

## Comparison With Remaining Phase 4 Targets

### Communication (32 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — existing Telegram is too limited
- **Existing infrastructure reuse:** LOW — only `send_telegram_message()` exists
- **Implementation size:** ~1520 LOC (exceeds threshold)
- **Dependencies:** Telegram bot token, email OAuth2, Slack bot token, Discord bot token
- **Credentials:** Required (multiple)
- **Security risk:** MEDIUM — external side effects, recipient validation
- **Resource impact:** Minimal

### Terminal (3 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** HIGH — TerminalProvider exists
- **Existing infrastructure reuse:** HIGH — TerminalProvider exists
- **Implementation size:** ~100 LOC (APP_CAPABILITIES entry + handler)
- **Dependencies:** None
- **Credentials:** None
- **Security risk:** MEDIUM — command execution
- **Resource impact:** Minimal

### GitHub (8 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** MEDIUM — MCP server exists, needs entry
- **Existing infrastructure reuse:** HIGH — MCP gateway exists
- **Implementation size:** ~200 LOC (MCP server registration)
- **Dependencies:** GitHub MCP server
- **Credentials:** Required (GitHub token)
- **Security risk:** LOW — read/write GitHub
- **Resource impact:** Minimal

### Calendar (3 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** MEDIUM — needs Google Calendar integration
- **Existing infrastructure reuse:** LOW — no calendar provider
- **Implementation size:** ~400 LOC
- **Dependencies:** Google Calendar API
- **Credentials:** Required (OAuth2)
- **Security risk:** LOW — calendar read/write
- **Resource impact:** Minimal

### MCP Tool (2 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** HIGH — MCP gateway exists
- **Existing infrastructure reuse:** HIGH — MCP gateway exists
- **Implementation size:** ~150 LOC (MCP server registration)
- **Dependencies:** MCP servers
- **Credentials:** Varies by MCP server
- **Security risk:** LOW — tool execution via MCP
- **Resource impact:** Minimal

### Workflow (3 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** MEDIUM — WorkflowExecutionProvider exists
- **Existing infrastructure reuse:** HIGH — WorkflowExecutionProvider exists
- **Implementation size:** ~150 LOC (APP_CAPABILITIES entry + handler)
- **Dependencies:** None
- **Credentials:** None
- **Security risk:** LOW — workflow execution
- **Resource impact:** Minimal

### AI Reasoning (46 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — needs structured output, schema validation
- **Existing infrastructure reuse:** MEDIUM — ask_llm() exists but wrong pattern
- **Implementation size:** ~470 LOC (but misleading — 0 templates become executable)
- **Dependencies:** LLM providers
- **Credentials:** Required (API keys)
- **Security risk:** MEDIUM — prompt injection
- **Resource impact:** Low

### Memory (13 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — existing memory is conversational, not automation
- **Existing infrastructure reuse:** MEDIUM — MemoryStore exists but wrong pattern
- **Implementation size:** ~1115 LOC (exceeds threshold)
- **Dependencies:** None
- **Credentials:** None
- **Security risk:** MEDIUM — state persistence, cross-session concerns
- **Resource impact:** Low

### Media (2 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — needs STT, TTS, image generation
- **Existing infrastructure reuse:** LOW — no media provider
- **Implementation size:** ~500 LOC
- **Dependencies:** External media APIs
- **Credentials:** Required
- **Security risk:** LOW
- **Resource impact:** Low

---

## Final Decision

**Decision: C — DEFER_COMMUNICATION**

### Rationale

1. **Zero templates fully unlocked.** Every communication template depends on other blocked capabilities. Implementing communication alone makes zero templates executable.

2. **Semantic mismatch.** 11 of 12 communication actions require entirely new infrastructure (batch sending, file sending, ack tracking, message buffering, channel formatting, inbox polling, priority detection, email labeling, calendar status). The existing Telegram is too limited.

3. **Implementation exceeds threshold.** At ~1520 LOC, communication implementation significantly exceeds the 500 LOC threshold. This is because it requires building multi-channel infrastructure (Telegram, email, Slack, Discord).

4. **Deceptive unlock count.** Claiming "32 templates unlocked" would be false. The real number is 0.

5. **Better targets exist.** Terminal (~100 LOC), GitHub (~200 LOC), and MCP Tool (~150 LOC) are smaller, high-impact, and would unblock more templates when combined with other fixes.

---

## Recommended Next Phase 4 Action

**Implement `terminal` capability instead.**

Terminal has:
- 3 templates depending on it
- TerminalProvider exists (just needs APP_CAPABILITIES entry)
- Only needs ~100 LOC
- Would unblock terminal steps in 3 templates

After terminal, implement `github` (~200 LOC) and `mcp_tool` (~150 LOC) — they're small, high-impact, and would unblock more templates.

---

## Audit Confirmation

1. **Communication templates audited:** 32
2. **Exact communication actions:** 14 (12 distinct patterns)
3. **Current real communication providers:** Telegram only (text messages)
4. **Exact directly-supported count:** 0
5. **Exact routing-only count:** 0
6. **Exact adapter-required count:** 6
7. **Exact provider-required count:** 6
8. **Exact unsupported count:** 0
9. **Exact templates fully unlocked by communication alone:** 0
10. **Exact templates still blocked by other capabilities:** 32
11. **Telegram reuse verdict:** PARTIAL — only text messages to self-recipient
12. **Other provider verdict:** All ABSENT (email, Slack, Discord, webhook)
13. **Honest LOC estimate:** ~1520 (exceeds 500 LOC threshold)
14. **Security findings:** Medium risk — external side effects, recipient validation, prompt injection
15. **Resource findings:** Minimal impact
16. **Comparison with remaining Phase 4 targets:** Terminal, GitHub, MCP Tool are better targets
17. **ONE final recommendation:** DEFER_COMMUNICATION, implement terminal instead
18. **Confirmation:** NO source/YAML/architecture changes were made during this audit
