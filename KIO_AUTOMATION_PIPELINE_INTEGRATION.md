# KIO Automation Pipeline Integration

## Summary

The KIO AutomationEngine is now wired into the existing KIO pipeline dispatch. Users can invoke any of the 63 canonical YAML automation workflows through the same input path used for all other KIO commands.

## Integration Architecture

```
User input (Telegram/Terminal)
    │
    ▼
Pipeline.run(text)
    │
    ├─── _NormalizationService.run()
    │
    ├─── _IntentClassifier.classify()
    │    └── NEW: _detect_automation() recognizes "run/execute/start/launch X workflow"
    │
    ├─── _CapabilityResolver.resolve()
    │    └── NEW: AUTOMATION → ("automation", {target, metadata})
    │
    ├─── _ExecutionCoordinator.execute()
    │    └── NEW: _exec_automation() → create_automation_engine().execute(template_id)
    │
    └─── _ResponseComposer.compose()
```

## What Changed

### `mini_kio/core/pipeline/types.py`
- Added `AUTOMATION = "automation"` to `IntentType` enum (27th value)

### `mini_kio/core/pipeline/__init__.py`
Three additions, zero modifications to existing code:

1. **`_IntentClassifier._detect_automation()`** (after `_detect_utility`, before `_check_identity`)
   - Regex patterns: `run X`, `execute X`, `start X`, `launch X`, `automation X`, `workflow X`
   - Compound phrases: `run the daily briefing`, `execute the workflow`
   - Returns `RoutingDecision(IntentType.AUTOMATION, "run_workflow", candidate, ...)`
   - Does NOT steal: greetings, utilities, media, search, system commands

2. **`_CapabilityResolver` mapping**
   - `IntentType.AUTOMATION → ("automation", {"action", "target", "metadata"})`

3. **`_ExecutionCoordinator._exec_automation()`**
   - Resolves template candidate → template ID via fuzzy matching
   - Creates `AutomationEngine` via `create_automation_engine()`
   - Runs `engine.execute(template_id)` with `asyncio.run()`
   - Formats results with step counts, blocked/failed details
   - Returns user-friendly message with workflow status

4. **`_ExecutionCoordinator._resolve_template_id()` / `_fuzzy_match_templates()`**
   - Static helper methods for template name resolution
   - Exact match → normalized match (spaces/dashes to underscores) → prefix match → substring match
   - Fuzzy match returns human-readable suggestions

### `mini_kio/automation/template_store.py`
- Added fallback path to `Downloads/kio_final/automation/library/` for development

## Trigger Patterns

| Pattern | Example | Template Candidate |
|---------|---------|-------------------|
| `run <name>` | "run the morning routine" | "morning routine" |
| `execute <name>` | "execute data json transform" | "data json transform" |
| `start <name>` | "start the daily briefing" | "daily briefing" |
| `launch <name>` | "launch the pr review prep" | "pr review prep" |
| `automation <name>` | "automation workflow name" | "workflow name" |
| `run the <name> briefing` | "run the daily briefing" | "daily" |

## Template Resolution

1. **Exact ID match**: "data.json_transform" → `data.json_transform`
2. **Normalized match**: "data json transform" → `data.json_transform`
3. **Partial prefix**: "browser structured extract" → `browser.structured_extract`
4. **Substring**: "json" → `data.json_transform`
5. **Fuzzy suggestions**: "browser" → list of matching template names

## What Did NOT Change

- No new top-level dispatcher
- No new NLU system
- No new security system
- No new credential vault
- No new event bus
- No new workflow engine
- Existing 26 IntentTypes unchanged (plus new AUTOMATION)
- Existing pipeline flow: Normalize → Classify → Resolve → Execute → Compose
- All existing intents continue to work (verified by regression tests)

## Test Coverage

- **69 integration tests** across 18 categories (all passing)
- **6 engine unit tests** (all passing)
- **Regression**: greeting, media, desktop, utility, knowledge, system, search all unaffected

## Live Validation: data.json_transform

Pipeline correctly:
1. Classified "run data json transform" → AUTOMATION intent
2. Resolved template ID → `data.json_transform`
3. Invoked AutomationEngine
4. Executed step through execution boundary
5. Returned formatted result (step failed with domain error — expected without input data)
