# KIO v2 Legacy Archive
Documentation only.
No functionality changed.

## Production Status
- **BrowserRuntime:** Stable, in production.
- **Browser Connector:** Stable, in production.
- **Browser Operator:** Stable, in production.
- **Browser Workspace:** Stable, in production.
- **Browser Session:** Stable, in production.
- **Browser Compatibility:** Stable, in production.
- **Old Browser Routing:** Stable, in production.
- **Legacy browser utilities:** Stable, in production.
- **Temporary compatibility layers:** Stable, in production.

## Migration Priority
- High: Core runtime components (BrowserRuntime, Connector).
- Medium: Operators, Workspace, Session.
- Low: Utilities and temporary shims.

## Risk Level
- Core components: Medium risk due to wide usage.
- Supporting utilities: Low risk.

## Replacement Strategy
1. Introduce modern_browser equivalents.
2. Add thin adapters.
3. Phase out legacy imports.

## Current Consumers
- All modules under `kio_final/*` that interact with browsers.
- External plugins using `BrowserRuntime` and related APIs.