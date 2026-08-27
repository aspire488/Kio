# SYSTEM_EXECUTION_GRAPH.md
# KIO Complete Runtime Execution Map
# ============================
# Reconstructed from actual code inspection, not documentation.

## FULL EXECUTION FLOW

```
TELEGRAM USER
    │
    ▼
telegram.Update (python-telegram-bot)
    │
    ├── filters.TEXT & ~filters.COMMAND ──► handle_message()
    │   │
    │   ├── Input validation (ALLOWED_USER_IDS, empty check)
    │   ├── Per-session sequence tracking (threading.Lock)
    │   ├── Long-op pool classification (_LONG_KEYWORDS)
    │   │   (play/next/stop/pause/create/open/browse/search/news/weather)
    │   │
    │   ├── route(text, user_id, channel="telegram")
    │   │   │
    │   │   ├── dispatch_channel_input(text, channel, user_id)
    │   │   │   │
    │   │   │   ├── KioRuntime lifecycle guard
    │   │   │   │   (shutdown check, input length, pruning)
    │   │   │   │
    │   │   │   ├── InputNormalizer.strip_emoji()
    │   │   │   │
    │   │   │   └── Pipeline.run(text, session_id, channel, user_id)
    │   │   │       │
    │   │   │       ├── Stage 1: NORMALIZATION
    │   │   │       │   _NormalizationService.run(raw, ctx)
    │   │   │       │   ├── strip_emoji()
    │   │   │       │   ├── resolve_references() (context resolution)
    │   │   │       │   ├── _apply_aliases()
    │   │   │       │   ├── _normalize_connectors()
    │   │   │       │   ├── normalize_typos()
    │   │   │       │   ├── expand_casual_contractions()
    │   │   │       │   ├── strip "hey kio" prefix
    │   │   │       │   ├── strip politeness prefix
    │   │   │       │   └── strip correction prefixes
    │   │   │       │
    │   │   │       ├── Stage 2: CLASSIFICATION
    │   │   │       │   _IntentClassifier.classify(normalized, raw)
    │   │   │       │   │
    │   │   │       │   ├── Capability-question gate (identity first)
    │   │   │       │   ├── Polite prefix re-strip
    │   │   │       │   ├── KIO-self canonicalization
    │   │   │       │   ├── Pragmatics analysis (register/temporal)
    │   │   │       │   │
    │   │   │       │   ├── Layer 0: KIO-self routes (health/status/uptime)
    │   │   │       │   ├── Layer 1: Greeting strip → recursion
    │   │   │       │   │   "hello kio open chrome" → "open chrome"
    │   │   │       │   ├── Layer 2: Acknowledgements/Thanks
    │   │   │       │   ├── Layer 3: Meta-conversation control
    │   │   │       │   ├── Layer 4: Utility detection (time/date/weather/convert)
    │   │   │       │   ├── Layer 5: Document save-as / open-and-make / code workflow
    │   │   │       │   ├── Layer 6: Camera capture compounds
    │   │   │       │   ├── Layer 7: Multi-step detection
    │   │   │       │   ├── Layer 8: Now-playing state queries
    │   │   │       │   ├── Layer 9: Deterministic system classification
    │   │   │       │   ├── Layer 10: Media transport (pause/resume/stop/next)
    │   │   │       │   ├── Layer 11: Discovery utterances ("play something")
    │   │   │       │   ├── Layer 12: Memory (remember/forget)
    │   │   │       │   ├── Layer 13: Pragmatics social (yo/heyy/bet/facts)
    │   │   │       │   ├── Layer 14: Curiosity/interest ("what are you curious about")
    │   │   │       │   ├── Layer 15: Identity ("who are you")
    │   │   │       │   ├── Layer 16: Opinion ("what do you think")
    │   │   │       │   ├── Layer 17: Emotion ("I'm bored")
    │   │   │       │   ├── Layer 18: Context follow-up ("nah/next/go with 1")
    │   │   │       │   ├── Layer 19: Camera capability
    │   │   │       │   ├── Layer 20: Entity query (capitalized proper nouns)
    │   │   │       │   └── Layer 21: Default → CONVERSATION
    │   │   │       │
    │   │   │       ├── Stage 2b: POST-CLASSIFICATION OVERRIDES
    │   │   │       │   ├── _apply_discourse_context_override()
    │   │   │       │   │   (context outranks surface form)
    │   │   │       │   ├── _apply_verification_probe_route()
    │   │   │       │   │   ("is this true?" with pending claims)
    │   │   │       │   ├── _apply_graph_recall_override()
    │   │   │       │   │   (known graph participants → conversation)
    │   │   │       │   ├── _apply_profile_recall_answer()
    │   │   │       │   │   (personal-state questions → deterministic)
    │   │   │       │   ├── _register_user_assertion()
    │   │   │       │   │   (declarative statements → pending claims)
    │   │   │       │   └── _consume_stale_claims()
    │   │   │       │       (topic move → clear pending claims)
    │   │   │       │
    │   │   │       ├── Stage 2c: SEMANTIC INGESTION (demand-driven)
    │   │   │       │   Only for CONVERSATION/MEMORY/INFORMATION/ENTITY_QUERY/KNOWLEDGE
    │   │   │       │   ├── intelligence.ingest_turn()
    │   │   │       │   ├── seed_current_facts()
    │   │   │       │   └── planner_decision()
    │   │   │       │
    │   │   │       ├── Stage 3: CAPABILITY RESOLUTION
    │   │   │       │   _CapabilityResolver.resolve(decision)
    │   │   │       │   ├── CapabilityRegistry lookup
    │   │   │       │   ├── Template preservation for conversation
    │   │   │       │   ├── Connector availability check (youtube search)
    │   │   │       │   └── Static fallback mapping
    │   │   │       │
    │   │   │       ├── Stage 4: EXECUTION
    │   │   │       │   _ExecutionCoordinator.execute(capability, params, decision)
    │   │   │       │   │
    │   │   │       │   ├── "desktop" → _exec_desktop()
    │   │   │       │   │   └── execution_boundary.execute_action()
    │   │   │       │   │       (app launch/close, file ops)
    │   │   │       │   │
    │   │   │       │   ├── "media" → _exec_media()
    │   │   │       │   │   ├── play/play_discovery → MediaManager.play()
    │   │   │       │   │   │   └── MediaContextIntelligence → search → browser
    │   │   │       │   │   ├── transport (pause/resume/stop/next) → MediaManager methods
    │   │   │       │   │   ├── accept_offer → MediaManager.process_followup()
    │   │   │       │   │   └── information_query → MediaManager.process_information_query()
    │   │   │       │   │       └── _maybe_proactive_offer() (APPENDS to result)
    │   │   │       │   │
    │   │   │       │   ├── "browser" → _exec_browser()
    │   │   │       │   │   └── BrowserRuntime / Connector
    │   │   │       │   │
    │   │   │       │   ├── "conversation" → _exec_conversation()
    │   │   │       │   │   ├── identity → identity_dataset.get_identity_answer()
    │   │   │       │   │   ├── greeting/social → render_social_reply() + fallbacks
    │   │   │       │   │   ├── accept_offer → MediaManager.process_followup()
    │   │   │       │   │   ├── converse/elaborate → _chat_converse() (LLM)
    │   │   │       │   │   └── meta_control → handle_meta_signal()
    │   │   │       │   │
    │   │   │       │   ├── "knowledge" → _exec_knowledge()
    │   │   │       │   │   └── LLM + web retrieval (Exa/Tavily/DDG)
    │   │   │       │   │
    │   │   │       │   ├── "operational" → _exec_operational()
    │   │   │       │   │   └── system health/status/uptime
    │   │   │       │   │
    │   │   │       │   ├── "utility" → _exec_utility()
    │   │   │       │   │   └── utilities.utility_answer()
    │   │   │       │   │       (time/date/weather/convert)
    │   │   │       │   │
    │   │   │       │   ├── "memory" → _exec_memory()
    │   │   │       │   ├── "mcp" → _exec_conversation()
    │   │   │       │   ├── "file" → _exec_desktop()
    │   │   │       │   ├── "coordinator" → _exec_coordinator()
    │   │   │       │   └── "credential" → _exec_credential()
    │   │   │       │
    │   │   │       ├── Stage 5: RESPONSE COMPOSITION
    │   │   │       │   _ResponseComposer.compose(result, decision, ctx)
    │   │   │       │   ├── _strip_leaks() (implementation jargon)
    │   │   │       │   ├── ctx.update() + append_exchange()
    │   │   │       │   ├── observe_exchange() (pragmatics)
    │   │   │       │   └── remember_runtime_context()
    │   │   │       │
    │   │   │       └── Return dict {success, message, action, ...}
    │   │   │
    │   │   ├── format_channel_reply(result)
    │   │   │   └── Extracts message string from dict
    │   │   │
    │   │   ├── Stale-response detection (per-session sequence)
    │   │   │
    │   │   └── update.message.reply_text(reply) ──► TELEGRAM USER
    │   │
    │   └── emit_runtime_trace() (latency metrics)
    │
    ├── filters.COMMAND ──► handle_unknown_command()
    ├── /start ──► cmd_start()
    ├── /help ──► cmd_help()
    └── /health|/status|/uptime|... ──► cmd_operational()
        └── route(command, user_id) → same Pipeline path

## PROACTIVE MESSAGE PATH (SEPARATE)

```
poll_proactive() daemon loop
    │
    ├── SemanticGraph.attributed_statements() (active user goals)
    ├── Workflow engine state evaluation
    ├── Stale-goal detection (age threshold, no re-engagement)
    ├── One-notification-per-goal constraint
    │
    └── send_telegram_message() ──► TELEGRAM USER
        (independent of Pipeline — not a response to a user message)
```

## MULTI-RESPONSE ROOT CAUSES (see MULTI_RESPONSE_ROOT_CAUSE.md)

The Pipeline itself is SINGLE-RESPONSE by design.
Multiple visible responses come from:
1. `_maybe_proactive_offer()` appending to information_query results
2. `monitoring/proactive.py` daemon sending independent messages
3. Proactive companion items (companion/proactive.py)
4. Browser connector background processes
