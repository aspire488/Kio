# KIO v2 Legacy Archive
Documentation only.
No functionality changed.

## Legacy Removal Plan

### Phase 1
- Identify all direct imports of legacy modules.
- Add thin adapter layers in `modern_browser` package.
- Update CI to flag any new legacy imports.

### Phase 2
- Migrate internal callers to adapters.
- Decommission temporary compatibility layers.
- Run integration tests targeting migrated paths.

### Phase 3
- Replace adapters with direct modern implementations.
- Remove legacy modules from import graph.
- Perform load‑testing on migrated components.

### Final Removal
- Delete legacy source files.
- Update documentation to reflect removal.
- Retire any feature flags related to legacy mode.

### Compatibility Shims
- Maintain shim modules in `legacy/compat_layers/` until Phase 2 is complete.
- Shims forward calls to new implementations.

### Rollback Strategy
- If regression detected, revert adapter imports to legacy versions.
- Keep version‑controlled branch with legacy code unchanged for quick rollback.
