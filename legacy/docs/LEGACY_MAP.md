# KIO v2 Legacy Archive
Documentation only.
No functionality changed.

## Legacy Subsystems

### BrowserRuntime
- **Current location:** `kio_final/browser_runtime.py`
- **Purpose:** Provides core browser execution environment.
- **Replacement (future):** `modern_browser.runtime`
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserConnector`, `BrowserOperator`
- **Replacement owner:** Platform team

### Browser Connector
- **Current location:** `kio_final/browser_connector.py`
- **Purpose:** Connects KIO to external browser instances.
- **Replacement (future):** `modern_browser.connector`
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserRuntime`
- **Replacement owner:** Platform team

### Browser Operator
- **Current location:** `kio_final/browser_operator.py`
- **Purpose:** Orchestrates browser actions.
- **Replacement (future):** `modern_browser.operator`
- **Migration phase:** Phase 2
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserRuntime`, `BrowserConnector`
- **Replacement owner:** Platform team

### Browser Workspace
- **Current location:** `kio_final/browser_workspace.py`
- **Purpose:** Manages workspace state for browsers.
- **Replacement (future):** `modern_browser.workspace`
- **Migration phase:** Phase 2
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserRuntime`
- **Replacement owner:** Platform team

### Browser Session
- **Current location:** `kio_final/browser_session.py`
- **Purpose:** Tracks user sessions within browsers.
- **Replacement (future):** `modern_browser.session`
- **Migration phase:** Phase 2
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserWorkspace`
- **Replacement owner:** Platform team

### Browser Compatibility
- **Current location:** `kio_final/browser_compatibility.py`
- **Purpose:** Compatibility shim for older browsers.
- **Replacement (future):** `modern_browser.compat`
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserRuntime`
- **Replacement owner:** Platform team

### Old Browser Routing
- **Current location:** `kio_final/old_browser_routing.py`
- **Purpose:** Routes requests to legacy browsers.
- **Replacement (future):** `modern_browser.router`
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** `BrowserConnector`
- **Replacement owner:** Platform team

### Legacy browser utilities
- **Current location:** `kio_final/legacy_utils/`
- **Purpose:** Helper utilities for legacy browser code.
- **Replacement (future):** `modern_browser.utils`
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** Various legacy modules
- **Replacement owner:** Platform team

### Temporary compatibility layers
- **Current location:** `kio_final/compat_layers/`
- **Purpose:** Short‑term shims to keep old code running.
- **Replacement (future):** Direct integration into new modules.
- **Migration phase:** Phase 1
- **Removal phase:** After Phase 3
- **Dependencies:** Multiple legacy subsystems
- **Replacement owner:** Platform team