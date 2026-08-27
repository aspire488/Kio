# PROACTIVE_INTERFERENCE_AUDIT.md
# Proactive System Interference with User Requests
# ================================================

## EXECUTIVE SUMMARY

KIO has **three independent proactive mechanisms** that can fire during or after user interactions.
Only one (monitoring/proactive.py) sends independent Telegram messages.
The other two are embedded within the response pipeline.

---

## PROACTIVE MECHANISM 1: Monitoring Proactive Daemon

**File:** `mini_kio/monitoring/proactive.py`
**Trigger:** Daemon loop (independent of user messages)
**Output:** Independent Telegram message via `send_telegram_message()`

### Behavior
- Evaluates active user goals from SemanticGraph
- Evaluates workflow engine state (failed/completed/pending)
- Sends notifications when goals are stale (>24h) and user hasn't re-engaged
- One notification per goal, ever
- Rate-limited by MIN_AGE_S (24 hours)

### Interference Risk
- **HIGH**: Can send a proactive message DURING an active conversation
- **Timing**: If daemon runs between user message and KIO response, user sees two messages
- **Mitigation**: Currently rate-limited, but no interaction-aware suppression

### Current Mitigation
- MIN_AGE_S = 24h (goals must be old)
- One notification per goal
- MAX_CANDIDATES = 2 per tick

### Recommended Fix
- Add active-conversation detection: suppress proactive messages when a user message was received in the last N seconds
- Or: queue proactive messages and deliver them only during idle periods

---

## PROACTIVE MECHANISM 2: Companion Proactive Evaluation

**File:** `mini_kio/companion/proactive.py`
**Trigger:** Called during response context (not daemon)
**Output:** Optional proactive message string (returned, not independently sent)

### Behavior
- Evaluates companion model beliefs for relevant open items
- Returns a proactive message if relevance_score >= 0.3 and confidence >= 0.4
- Rate-limited by _proactive_cooldown_messages (3 messages minimum gap)

### Interference Risk
- **LOW**: Returns a string, doesn't independently send
- **Usage**: Currently not clearly wired into the response path
- **Risk**: If wired into response generation, could append to responses

### Current Mitigation
- Rate limiting (cooldown)
- Confidence/relevance thresholds
- Returns None when no relevant items

### Recommended Fix
- Ensure this mechanism is used ONLY for contextual initiative, never overrides explicit user requests
- Add explicit priority: EXPLICIT USER REQUEST > PROACTIVE SUGGESTION

---

## PROACTIVE MECHANISM 3: Media Proactive Offer

**File:** `mini_kio/core/pipeline/__init__.py:7365-7464`
**Trigger:** After information_query execution in _exec_media
**Output:** Appends offer line to result["message"]

### Behavior
- Runs `MediaDiscovery.detect_opportunity()` after topic answers
- When an opportunity is detected, appends a one-line media offer to the response
- User sees the answer PLUS the media offer in one message

### Interference Risk
- **MEDIUM**: Modifies the response but doesn't send independently
- **User perception**: User asked a question, got an answer + media suggestion
- **Intention**: Useful when the topic is genuinely media-relevant

### Current Mitigations
- Never fires after verification/claim answers
- Never fires on pure information queries
- Per-session cooldown (5 minutes for same topic)
- Only fires when topic has genuine media opportunity

### Recommended Fix
- Already well-gated — no changes needed unless it fires inappropriately
- Monitor live behavior to confirm restraint rules work

---

## PROACTIVE PRIORITY MODEL (RECOMMENDED)

```
1. EXPLICIT USER REQUEST
   "play X" → MUST play X
   "open Chrome" → MUST open Chrome
   "what time is it" → MUST return time
   Priority: HIGHEST — never overridden

2. DETERMINISTIC UTILITY/ACTION
   Time/date/weather answers
   App launch/close
   System status
   Priority: HIGH — deterministic, reliable

3. CONVERSATIONAL RESPONSE
   LLM-generated conversation
   Identity answers
   Social replies
   Priority: MEDIUM — contextual

4. PROACTIVE SUGGESTION
   Media offer after topic answer
   Stale goal notification
   Companion initiative
   Priority: LOW — never overrides 1-3
```

### Implementation Rule
Proactive behavior must NEVER:
- Fire during active message processing (within 30s of user message)
- Override or modify an explicit user request's response
- Send an independent message that appears to be a response to user input
- Inject content that contradicts the user's stated intent

---

## PROACTIVE MESSAGES TIMING ANALYSIS

| Mechanism | When it fires | How user perceives it |
|-----------|--------------|----------------------|
| Monitoring daemon | Independent timer | Separate message (appears as second response) |
| Companion evaluation | During response context | Could appear as appended content |
| Media offer | After information_query | Appended to response (one message) |

### The "Dual Response" Problem
The monitoring daemon is the PRIMARY cause of perceived dual responses.
When the daemon fires during an active conversation, the user sees:
1. KIO's response to their message
2. A proactive notification about a stale goal

These are NOT two responses to the same message — they are a response + a background notification.
But the user perceives them as "KIO sent two replies."

### Fix
Suppress monitoring daemon messages when user interaction was recent.
