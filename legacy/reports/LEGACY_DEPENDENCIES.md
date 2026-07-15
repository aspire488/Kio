# KIO v2 Legacy Archive
Documentation only.
No functionality changed.

## Call Graph
- `BrowserRuntime` called by `BrowserOperator`, `BrowserWorkspace`, `BrowserSession`.
- `BrowserConnector` called by `BrowserRuntime` and `Old Browser Routing`.
- `BrowserOperator` orchestrates calls to `BrowserRuntime` and `BrowserConnector`.

## Import Graph
- `kio_final/browser_runtime.py` imports `browser_connector`, `browser_compatibility`.
- `kio_final/browser_operator.py` imports `browser_runtime`, `browser_workspace`.
- `kio_final/browser_workspace.py` imports `browser_runtime`.
- `kio_final/browser_session.py` imports `browser_workspace`.
- `kio_final/old_browser_routing.py` imports `browser_connector`.
- Utilities in `legacy_utils/` import various legacy modules.

## Runtime Dependencies
- System libraries: `subprocess`, `json`.
- Third‑party: none specific to legacy browser code.

## Modules referencing BrowserRuntime
- `browser_operator.py`
- `browser_workspace.py`
- `browser_session.py`

## Modules referencing BrowserConnector
- `browser_runtime.py`
- `old_browser_routing.py`

## Modules referencing BrowserOperator
- `browser_workspace.py`
- `browser_session.py`

## Potential Migration Blockers
- Tight coupling between `BrowserRuntime` and legacy plugins.
- Direct file system path handling in `legacy_utils`.
- Lack of unit tests for some legacy paths.
