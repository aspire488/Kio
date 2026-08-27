# HARDCODE_REMEDIATION_PLAN — Prioritized Action Plan

## Executive Summary

- **Total Hardcodings Found:** 90+
- **Critical:** 16
- **High:** 47
- **Medium:** 22
- **Low:** 5
- **Legitimate:** 5+

## Priority 1: CRITICAL (Immediate Action Required)

### 1.1 Security: Credentials in .env
- **File:** `.env`
- **Risk:** Live credentials committed to git
- **Action:** Move to `.env.gitignore`, inject via secrets manager
- **Effort:** 1 hour
- **Impact:** Security vulnerability

### 1.2 LLM Provider Chain
- **File:** `llm_router.py`
- **Risk:** Provider priority hardcoded, cannot change without code
- **Action:** Externalize to config file with priority field
- **Effort:** 2 hours
- **Impact:** Operational flexibility

### 1.3 System Prompt
- **File:** `llm/gateway.py` (_ASYSTEM_PROMPT)
- **Risk:** Kio identity hardcoded, cannot modify personality
- **Action:** Externalize to prompt template files
- **Effort:** 2 hours
- **Impact:** Personality customization

### 1.4 Canonical Knowledge
- **File:** `llm/constants.py` (_CANONICAL_KNOWLEDGE)
- **Risk:** Knowledge base hardcoded, cannot update
- **Action:** Externalize to knowledge base config
- **Effort:** 2 hours
- **Impact:** Knowledge management

### 1.5 Intent Classification Phrases
- **File:** `pipeline/__init__.py`
- **Risk:** 100+ phrases hardcoded, cannot add new intents
- **Action:** Externalize to intent config YAML
- **Effort:** 4 hours
- **Impact:** Intent extensibility

### 1.6 Media Response Phrases
- **File:** `media_manager.py`
- **Risk:** All user-visible responses hardcoded
- **Action:** Externalize to template system
- **Effort:** 3 hours
- **Impact:** Response customization

## Priority 2: HIGH (Next Sprint)

### 2.1 Command Routing
- **Files:** `command_router.py`, `pipeline/__init__.py`
- **Risk:** All routing rules hardcoded
- **Action:** Extract to declarative routing config
- **Effort:** 6 hours
- **Impact:** Routing flexibility

### 2.2 State Machine
- **File:** `pipeline/__init__.py`
- **Risk:** State transitions hardcoded
- **Action:** Extract to state machine config
- **Effort:** 4 hours
- **Impact:** State management

### 2.3 Browser Connector
- **Files:** `browser_connector/`
- **Risk:** Port, extension IDs, paths hardcoded
- **Action:** Externalize to browser config
- **Effort:** 3 hours
- **Impact:** Browser flexibility

### 2.4 Media Providers
- **Files:** `media/providers/`
- **Risk:** Commands, URLs, selectors hardcoded
- **Action:** Externalize to provider config
- **Effort:** 4 hours
- **Impact:** Provider extensibility

### 2.5 MCP Servers
- **Files:** `core/mcp/`
- **Risk:** Server names, mappings hardcoded
- **Action:** Externalize to MCP config
- **Effort:** 3 hours
- **Impact:** Tool flexibility

### 2.6 Configuration Values
- **Files:** `config.py`, `llm/constants.py`
- **Risk:** All config values hardcoded
- **Action:** Single config system with overrides
- **Effort:** 4 hours
- **Impact:** Configuration management

### 2.7 Personality System
- **Files:** `companion/`
- **Risk:** Identity, responses, behavior hardcoded
- **Action:** Externalize to personality config
- **Effort:** 4 hours
- **Impact:** Personality customization

## Priority 3: MEDIUM (Following Sprints)

### 3.1 Response Templates
- **Files:** `runtime_response_formatter.py`, `media_manager.py`
- **Risk:** Response text hardcoded
- **Action:** Template system with slots
- **Effort:** 4 hours
- **Impact:** Response flexibility

### 3.2 Mood Mapping
- **Files:** `pipeline/__init__.py`, `media_recommender.py`
- **Risk:** Mood→genre, time→mood mappings hardcoded
- **Action:** Externalize to mood config
- **Effort:** 3 hours
- **Impact:** Mood system flexibility

### 3.3 Memory Categories
- **Files:** `memory/`
- **Risk:** Category names, thresholds hardcoded
- **Action:** Externalize to memory config
- **Effort:** 2 hours
- **Impact:** Memory flexibility

### 3.4 Intelligence Routing
- **Files:** `intelligence_router.py`
- **Risk:** Routing rules hardcoded
- **Action:** Externalize to routing config
- **Effort:** 3 hours
- **Impact:** Intelligence flexibility

### 3.5 Adapter Logic
- **Files:** `adapters/`
- **Risk:** Priorities, prompts, fallbacks hardcoded
- **Action:** Externalize to adapter config
- **Effort:** 3 hours
- **Impact:** Adapter flexibility

### 3.6 Error Handling
- **Files:** Various
- **Risk:** Error messages hardcoded
- **Action:** Error template system
- **Effort:** 2 hours
- **Impact:** Error customization

## Priority 4: LOW (Backlog)

### 4.1 Legacy Code Removal
- **Files:** `legacy/`, deprecated providers
- **Risk:** Dead code still executable
- **Action:** Remove dead code
- **Effort:** 4 hours
- **Impact:** Code hygiene

### 4.2 Test Hardcoding
- **Files:** `tests/`
- **Risk:** Test-only values
- **Action:** Keep as-is (legitimate)
- **Effort:** 0 hours
- **Impact:** None

### 4.3 Script Hardcoding
- **Files:** `scripts/`
- **Risk:** Script-specific values
- **Action:** Keep as-is (legitimate)
- **Effort:** 0 hours
- **Impact:** None

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
1. Security: Fix .env exposure
2. Config System: Build external config loader
3. Template System: Build response template engine
4. LLM Config: Externalize provider chain and prompts

### Phase 2: Core (Week 2)
1. Intent Config: Externalize phrase sets
2. Routing Config: Externalize command routing
3. State Config: Externalize state machine
4. Browser Config: Externalize browser settings

### Phase 3: Media (Week 3)
1. Media Config: Externalize provider settings
2. Response Templates: Externalize media responses
3. Mood Config: Externalize mood mappings
4. Session Config: Externalize session settings

### Phase 4: Polish (Week 4)
1. Personality Config: Externalize companion behavior
2. Error Templates: Externalize error messages
3. Legacy Cleanup: Remove dead code
4. Documentation: Update all docs

## Success Metrics

| Metric | Current | Target |
|---|---|---|
| Hardcoded values | 90+ | <10 |
| Config files | 0 | 5-10 |
| Template files | 0 | 10-15 |
| Code changes for behavior | Required | Config-only |
| New intent addition | Code change | Config change |
| New provider addition | Code change | Config change |
| Personality modification | Code change | Config change |

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Breaking existing behavior | Comprehensive testing before each phase |
| Performance impact | Benchmark before/after each phase |
| Configuration complexity | Clear documentation and examples |
| Migration effort | Automated migration scripts |
| Team adoption | Training and documentation |
