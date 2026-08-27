# LEGACY_HARDCODING — Every Legacy/Obsolete Behavior

## Legacy Code Paths

### 1. Legacy Compatibility Layer

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| legacy/ | Backward compatibility wrappers | Obsolete | Remove if no consumers |
| legacy/ | Deprecated API endpoints | Obsolete | Remove |
| legacy/ | Old format converters | Obsolete | Remove |

### 2. Deprecated Browser Automation

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| browser/ | Old Selenium-based automation | Superseded by Playwright | Remove |
| browser/ | Legacy Chrome DevTools Protocol | Superseded by extension-based | Review |
| browser/ | Deprecated browser profiles | Superseded by session management | Remove |

### 3. Old Media Providers

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| media/providers/ | Deprecated VLC integration | Superseded by browser-based | Remove |
| media/providers/ | Old MPV player support | Superseded by browser-based | Remove |
| media/providers/ | Legacy Airplay support | Never completed | Remove |

### 4. Legacy Memory System

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| memory/ | Old file-based memory | Superseded by DB-based | Remove |
| memory/ | Legacy JSON serialization | Superseded by proper models | Remove |
| memory/ | Deprecated memory categories | Superseded by dynamic categories | Remove |

### 5. Old LLM Integration

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| llm/ | Deprecated OpenAI v1 API | Superseded by v2 | Remove |
| llm/ | Old HuggingFace integration | Superseded by dedicated providers | Remove |
| llm/ | Legacy prompt templates | Superseded by current templates | Remove |

### 6. Deprecated MCP Servers

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| core/mcp/ | Old server definitions | Superseded by current servers | Remove |
| core/mcp/ | Deprecated tool mappings | Superseded by current mappings | Remove |
| core/mcp/ | Legacy connection handling | Superseded by current handling | Remove |

### 7. Old Adapter Implementations

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| adapters/ | Deprecated adapter interfaces | Superseded by current interfaces | Remove |
| adapters/ | Old priority logic | Superseded by current logic | Remove |
| adapters/ | Legacy fallback chains | Superseded by current chains | Remove |

## Test-Only Hardcoding

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| tests/ | Mock API responses | Legitimate in tests | Keep |
| tests/ | Test fixture data | Legitimate in tests | Keep |
| tests/ | Mock provider configs | Legitimate in tests | Keep |
| tests/ | Test environment variables | Legitimate in tests | Keep |

## Script-Specific Hardcoding

| File | Behavior | Status | Recommendation |
|---|---|---|---|
| scripts/ | Deployment paths | Legitimate in scripts | Keep |
| scripts/ | Build configuration | Legitimate in scripts | Keep |
| scripts/ | Environment setup | Legitimate in scripts | Keep |

## Dead Code Detection

| Location | Dead Code | Recommendation |
|---|---|---|
| pipeline/__init__.py | Unused intent types | Remove |
| pipeline/__init__.py | Unreachable code branches | Remove |
| media_manager.py | Unused media formats | Remove |
| browser/ | Deprecated browser features | Remove |
| llm/ | Unused provider methods | Remove |
| memory/ | Deprecated memory operations | Remove |

## Legacy Configuration

| Setting | Legacy Value | Current Value | File |
|---|---|---|---|
| WebSocket port | 8765 | 9877 | browser_connector/ |
| API version | v1 | v2 | internal_api/ |
| Memory format | JSON | SQLite | memory/ |
| Browser engine | Selenium | Playwright | browser/ |
| LLM provider | OpenAI only | Multi-provider | llm/ |

## Backward Compatibility Concerns

| Feature | Concern | Risk | Recommendation |
|---|---|---|---|
| API endpoints | External consumers may depend | HIGH | Version before removing |
| Media formats | Users may have playlists | MEDIUM | Provide migration |
| Memory data | Users may have saved memories | HIGH | Provide export/import |
| Configuration | Users may have custom configs | MEDIUM | Provide migration guide |
