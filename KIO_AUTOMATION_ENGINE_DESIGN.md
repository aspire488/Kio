# KIO Automation Engine Design

**Date:** 2026-09-13
**Status:** DESIGN — Pending approval before implementation
**Prerequisite:** KIO_AUTOMATION_SEMANTIC_AUDIT.md approved

---

## Architecture Overview

The automation engine is a **lightweight orchestrator** that:
1. Loads canonical YAML templates from `automation/library/`
2. Resolves capabilities to KIO's existing providers + new missing ones
3. Executes workflows step-by-step with verification
4. Handles triggers (schedule, file watch, webhook, email, event)
5. Manages state (memory KV store) for deduplication and context

### Design Principles
- **No n8n dependency.** Templates are the source of truth.
- **Lazy loading.** Only load templates the user triggers.
- **Capability-first.** Each step declares a capability; the engine maps to providers.
- **Verification mandatory.** Every consequential step has a verification gate.
- **Stateful execution.** Memory KV store prevents duplicate side effects.
- **Zero-second runtime constraint.** Engine must start and execute within resource limits.

---

## Component Architecture

```
┌─────────────────────────────────────────────────┐
│                  AutomationEngine                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Template │  │ Step     │  │ Verification │  │
│  │ Loader   │→ │ Executor │→ │ Gate         │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│       ↓              ↓              ↓            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Capability│  │ Memory   │  │ Monitoring   │  │
│  │ Registry │  │ KV Store │  │ TriggerMgr   │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
         ↓              ↓              ↓
┌─────────────────────────────────────────────────┐
│              KIO Provider Layer                  │
│  LLM │ Browser │ Terminal │ Filesystem │ MCP    │
└─────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Template Loader

```python
# mini_kio/automation/template_loader.py
class TemplateLoader:
    """Loads and validates YAML templates from automation/library/."""
    
    def load(self, template_id: str) -> AutomationTemplate:
        """Load a template by ID (e.g. 'ai.deep_research')."""
        
    def list_available(self) -> List[str]:
        """List all available template IDs."""
        
    def validate(self, template: AutomationTemplate) -> bool:
        """Validate against kio_template.schema.json."""
```

**Template Model:**
```python
@dataclass
class AutomationTemplate:
    id: str
    name: str
    description: str
    category: str
    version: str
    trigger: TriggerConfig
    inputs: List[InputConfig]
    config: List[ConfigField]
    capabilities_required: List[str]
    providers_required: List[str]
    mcp_servers_required: List[str]
    credentials_required: List[CredentialConfig]
    steps: List[StepConfig]
    outputs: List[OutputConfig]
    verification: List[VerificationConfig]
    failure_recovery: FailureRecoveryConfig
    security_classification: str
    user_confirmation_required: bool
    resource_expectations: ResourceExpectations
    provenance: ProvenanceConfig
```

### 2. Capability Registry

Maps capability names to KIO providers and new capabilities.

```python
# mini_kio/automation/capability_registry.py
class CapabilityRegistry:
    """Maps workflow capabilities to executable providers."""
    
    def __init__(self):
        self.capabilities = {
            # Existing KIO capabilities
            'ai_reasoning': AIReasoningCapability(),
            'browser': BrowserCapability(),
            'filesystem': FilesystemCapability(),
            'terminal': TerminalCapability(),
            'workflow': WorkflowCapability(),
            'knowledge': KnowledgeCapability(),
            
            # New capabilities (to be built)
            'memory': MemoryCapability(),        # Phase 1
            'communication': CommunicationCapability(),  # Phase 1
            'mcp_tool': MCPToolCapability(),      # Phase 1
            'github': GitHubCapability(),         # Phase 3
            'calendar': CalendarCapability(),     # Phase 3
            'media': MediaCapability(),           # Phase 4
            'email': EmailCapability(),           # Phase 5
            'http': HTTPCapability(),             # Phase 5
            'monitoring': MonitoringCapability(), # Phase 2
            'artifact': ArtifactCapability(),     # Phase 6
            'code_project': CodeProjectCapability(),  # Phase 6
        }
    
    def resolve(self, capability_name: str, action: str) -> Callable:
        """Resolve a capability+action to an executable function."""
```

### 3. Step Executor

```python
# mini_kio/automation/step_executor.py
class StepExecutor:
    """Executes individual workflow steps."""
    
    async def execute_step(
        self, 
        step: StepConfig, 
        context: ExecutionContext
    ) -> StepResult:
        """Execute a single step with error handling."""
        
    async def execute_with_retry(
        self,
        step: StepConfig,
        context: ExecutionContext,
        retry_config: RetryConfig
    ) -> StepResult:
        """Execute with retry and backoff."""
```

**Execution Context:**
```python
@dataclass
class ExecutionContext:
    template_id: str
    run_id: str
    inputs: Dict[str, Any]
    config: Dict[str, Any]
    step_results: Dict[str, StepResult]  # For depends_on resolution
    memory: MemoryKVStore
    verification_results: Dict[str, Any]
```

### 4. Verification Gate

```python
# mini_kio/automation/verification_gate.py
class VerificationGate:
    """Runs verification checks after each consequential step."""
    
    async def verify(
        self,
        verification: VerificationConfig,
        context: ExecutionContext,
        step_result: StepResult
    ) -> VerificationResult:
        """Run verification checks."""
```

**Verification Types:**
- `artifact`: Check file exists, is valid, has expected content
- `filesystem`: Check path exists, size, permissions
- `communication_delivery`: Check message ID returned
- `browser_state`: Check page loaded, selector matched
- `calendar_event`: Check event exists by ID
- `github_state`: Check issue/PR exists
- `http_response`: Check status code, response body
- `data_shape`: Check data conforms to schema

### 5. Memory KV Store (Phase 1)

```python
# mini_kio/automation/memory_store.py
class MemoryKVStore:
    """Persistent key-value store for workflow state."""
    
    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        
    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set a value with optional TTL (seconds)."""
        
    async def delete(self, key: str):
        """Delete a key."""
        
    async def list_keys(self, prefix: str) -> List[str]:
        """List keys matching a prefix."""
        
    async def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Message]:
        """Get conversation history for a user."""
        
    async def add_conversation_turn(self, user_id: str, message: str, reply: str):
        """Add a conversation turn."""
        
    async def get_snapshot(self, key: str) -> Optional[str]:
        """Get a change detection snapshot."""
        
    async def set_snapshot(self, key: str, content: str):
        """Store a change detection snapshot."""
```

**Schema:**
```sql
CREATE TABLE kv_store (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,  -- JSON-encoded
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE snapshots (
    key TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6. Monitoring Trigger Manager (Phase 2)

```python
# mini_kio/automation/trigger_manager.py
class TriggerManager:
    """Manages workflow triggers (schedule, file watch, webhook, email, event)."""
    
    def __init__(self, memory: MemoryKVStore):
        self.memory = memory
        self.schedulers = {}
        self.file_watchers = {}
        self.webhook_server = None
        
    async def register_schedule(self, template_id: str, cron: str):
        """Register a cron-based schedule trigger."""
        
    async def register_file_watch(self, template_id: str, watch_path: str):
        """Register a file watch trigger."""
        
    async def register_webhook(self, template_id: str, path: str, auth: str):
        """Register a webhook trigger."""
        
    async def register_email(self, template_id: str, filter_config: dict):
        """Register an email received trigger."""
        
    async def start(self):
        """Start all registered triggers."""
        
    async def stop(self):
        """Stop all triggers."""
```

### 7. Automation Engine (Orchestrator)

```python
# mini_kio/automation/engine.py
class AutomationEngine:
    """Main orchestrator for workflow execution."""
    
    def __init__(self, kio_core):
        self.template_loader = TemplateLoader()
        self.capability_registry = CapabilityRegistry()
        self.step_executor = StepExecutor(self.capability_registry)
        self.verification_gate = VerificationGate()
        self.memory = MemoryKVStore()
        self.trigger_manager = TriggerManager(self.memory)
        
    async def execute_workflow(
        self,
        template_id: str,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None
    ) -> WorkflowResult:
        """Execute a workflow from template ID."""
        
    async def list_workflows(self) -> List[WorkflowSummary]:
        """List all available workflows with their status."""
        
    async def get_workflow_status(self, run_id: str) -> WorkflowStatus:
        """Get the status of a running/completed workflow."""
        
    async def start_triggers(self):
        """Start all registered triggers."""
        
    async def stop_triggers(self):
        """Stop all triggers."""
```

---

## Integration with KIO Core

### Entry Points

```python
# In kio_bot.py or main CLI
from mini_kio.automation.engine import AutomationEngine

# Initialize
automation = AutomationEngine(kio_core)

# Execute a workflow
result = await automation.execute_workflow(
    "ai.deep_research",
    inputs={"topic": "quantum computing"},
    config={"depth": "deep"}
)

# Start all triggers
await automation.start_triggers()
```

### Route Integration

The existing pipeline dispatch (`mini_kio/core/pipeline/__init__.py`) gets a new route:

```python
# Route 26: Automation
elif user_text.startswith("/automate") or user_text.startswith("/workflow"):
    template_id = extract_template_id(user_text)
    result = await automation_engine.execute_workflow(template_id, inputs)
```

---

## File Structure

```
mini_kio/automation/
├── __init__.py
├── engine.py              # Main orchestrator
├── template_loader.py     # YAML template loading
├── capability_registry.py # Maps capabilities to providers
├── step_executor.py       # Executes individual steps
├── verification_gate.py   # Runs verification checks
├── memory_store.py        # Persistent KV store (Phase 1)
├── trigger_manager.py     # Trigger infrastructure (Phase 2)
├── models.py              # Data models (Template, Step, etc.)
└── providers/
    ├── __init__.py
    ├── memory.py          # Memory capability
    ├── communication.py   # Communication capability
    ├── github.py          # GitHub capability
    ├── calendar.py        # Calendar capability
    ├── media.py           # Media capability
    ├── email.py           # Email capability
    ├── http.py            # HTTP capability
    └── monitoring.py      # Monitoring capability
```

---

## Implementation Phases

### Phase 1: Core Engine + Memory (39/63 workflows)
**Duration:** 3-4 days
**Deliverables:**
- `template_loader.py` — Load and validate YAML templates
- `capability_registry.py` — Map capabilities to providers
- `step_executor.py` — Execute steps with retry
- `verification_gate.py` — Run verification checks
- `memory_store.py` — Persistent KV store
- `engine.py` — Main orchestrator
- `models.py` — Data models
- Communication capability (Telegram)
- MCP tool capability

**Workflows unblocked:** 46/63 (73%)

### Phase 2: Trigger Infrastructure (24/63 workflows)
**Duration:** 3-4 days
**Deliverables:**
- `trigger_manager.py` — Trigger orchestration
- Cron scheduler (APScheduler)
- File watcher (watchdog)
- Webhook receiver (FastAPI)
- Email poller (imaplib)
- Event bus

**Workflows unblocked:** 58/63 (92%)

### Phase 3: External Providers (10/63 workflows)
**Duration:** 2-3 days
**Deliverables:**
- Calendar provider (Google Calendar OAuth)
- GitHub write capabilities (issues, PRs, releases)
- HTTP client (requests/httpx)

**Workflows unblocked:** 63/63 (100%)

### Phase 4: Media + Render (6/63 workflows)
**Duration:** 2-3 days
**Deliverables:**
- Media providers (Whisper, TTS, image gen)
- Render library integration (python-docx, weasyprint, python-pptx)

**All workflows fully executable.**

---

## Resource Constraints

- **Runtime:** Zero-second startup, execute within memory limits
- **Memory:** 650MB peak (ResourceGuard enforced)
- **No eval()/exec()** — All execution through safe provider interfaces
- **CredentialVault only** — No plaintext secrets
- **Verification mandatory** — Every consequential step verified
- **Lazy loading** — Only load templates the user triggers

---

## Open Questions

1. **State persistence:** SQLite vs JSON files for memory KV store?
2. **Cron library:** APScheduler vs custom cron parser?
3. **Webhook server:** FastAPI vs aiohttp vs integrated into existing KIO server?
4. **Email IMAP:** Pure Python (imaplib) vs third-party (imapclient)?
5. **Media providers:** Local Whisper vs OpenAI API? Local TTS vs cloud?

**Recommendation:** Start with simplest working solution, optimize later.
- SQLite for memory (already have sqlite MCP server)
- APScheduler for cron (mature, lightweight)
- FastAPI for webhook (already used in many Python projects)
- imaplib for email (stdlib, no dependency)
- OpenAI API for media (fastest to implement, can add local later)
