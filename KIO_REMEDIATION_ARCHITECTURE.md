# KIO_REMEDIATION_ARCHITECTURE.md
# Target Architecture for KIO
# ============================

## CURRENT ARCHITECTURE (VERIFIED FROM CODE)

```
USER INPUT
    ↓
TELEGRAM TRANSPORT (kio_bot.py)
    ↓
NORMALIZATION (InputNormalizer + _NormalizationService)
    ↓
CLASSIFICATION (_IntentClassifier — 21-layer deterministic classifier)
    ↓
POST-CLASSIFICATION OVERRIDES
    ├── Discourse context override
    ├── Verification probe routing
    ├── Graph recall override
    ├── Profile recall answer (early return)
    ├── User assertion registration
    └── Stale claim consumption
    ↓
CAPABILITY RESOLUTION (_CapabilityResolver → CapabilityRegistry)
    ↓
EXECUTION (_ExecutionCoordinator → capability-specific executor)
    ↓
RESPONSE COMPOSITION (_ResponseComposer)
    ↓
TELEGRAM OUTPUT
```

### Strengths (KEEP)
- Single routing authority (Pipeline)
- Deterministic fast paths (greetings, utility, identity)
- Progressive fallback chains (pragmatics → LLM → deterministic)
- Context-aware overrides (discourse, graph, profile)
- Single canonical phrase store (phrases.py)
- Single canonical identity source (identity_dataset.py)
- Single canonical utility owner (utilities.py)
- Single canonical media owner (MediaManager)

### Weaknesses (FIX)
1. Proactive offer embedding (_maybe_proactive_offer in _exec_media)
2. Two independent proactive systems (monitoring + companion)
3. Dead code (_reply_greeting method)
4. Static topic keyword banks (200+ keywords)
5. Static activity → music mappings
6. Hardcoded proactive session list

---

## TARGET ARCHITECTURE

```
USER INPUT
    ↓
TRANSPORT (interface-independent)
    ↓
SEMANTIC UNDERSTANDING
    ├── Input normalization (existing)
    ├── Pragmatics analysis (existing)
    ├── Intent classification (existing — deterministic fast paths)
    ├── Context resolution (existing — discourse, graph, profile)
    └── Entity extraction (existing)
    ↓
CANONICAL INTENT / ACTION MODEL
    (existing RoutingDecision — single canonical intent type)
    ↓
POLICY (existing — safety, priorities, terminal semantics)
    ↓
CAPABILITY DISCOVERY (existing — CapabilityRegistry)
    ↓
DYNAMIC ROUTING (existing — _CapabilityResolver)
    ↓
EXECUTION (existing — _ExecutionCoordinator)
    ↓
VERIFICATION (existing — playback verification, execution boundary)
    ↓
RESPONSE GENERATION (existing — _ResponseComposer)
    ↓
OUTPUT (interface-specific rendering)
```

### Changes from Current
1. **Proactive layer extracted** from _exec_media → dedicated ProactiveOfferManager
2. **Proactive systems consolidated** → single proactive priority model
3. **Dead code removed** → _reply_greeting deleted
4. **Topic classification** → semantic (when LLM available) with keyword fallback
5. **Activity → music** → contextual intent resolution

### What Does NOT Change
- Pipeline as single routing authority
- Deterministic fast paths for common commands
- MediaManager as canonical media owner
- Browser-based YouTube playback
- CapabilityRegistry for capability discovery
- _ResponseComposer for response formatting
- Pragmatics as canonical register analyzer

---

## TERMINAL SEMANTICS (RECOMMENDED)

```
HANDLED     → Response sent, no further action needed
TERMINAL    → Processing complete, no follow-up expected
DEFERRED    → Action started, result pending (media playback)
ACTION_REQUIRED → User input needed (confirmation, choice)
FALLBACK    → Primary path failed, using alternative
ERROR       → Processing failed, error response sent
```

### Where Terminal Semantics Apply
- After _exec_conversation: HANDLED
- After _exec_utility: HANDLED
- After _exec_media play: DEFERRED (playback in progress)
- After _exec_media transport: HANDLED
- After _exec_desktop: HANDLED
- After _exec_browser: DEFERRED (browser action in progress)
- After offer recommendation: ACTION_REQUIRED (user choice needed)

---

## CANONICAL OWNER MAP (FINAL)

| Concept | Canonical Owner | Duplicates |
|---------|----------------|------------|
| Greeting | phrases.py + pragmatics | 0 |
| Acknowledgement | phrases.py + pragmatics | 0 |
| Thanks | phrases.py + pragmatics | 0 |
| Identity | identity_dataset.py | 0 |
| Utility | utilities.py | 0 |
| Media transport | phrases.py + _classify_media_transport | 0 |
| Media follow-up | MediaManager.process_followup() | 0 |
| Media session state | MediaManager | 0 |
| Media context intelligence | MediaContextIntelligence | 0 |
| Proactive (stale goals) | monitoring/proactive.py | 1 (companion) |
| Proactive (media offer) | _maybe_proactive_offer (→ to extract) | 0 (after extraction) |
| Conversation state | ContextManager | 0 |
| Execution boundary | execution_boundary.py | 0 |
| Browser operations | BrowserRuntime + Connector | 0 |
| Desktop operations | execution_boundary.py + app_operator | 0 |
| Knowledge retrieval | KnowledgeRouter | 0 |
| Pragmatics | pragmatics.py | 0 |
| Response formatting | _ResponseComposer | 0 |

**Final duplicate count:** 1 (proactive systems — to be consolidated)
