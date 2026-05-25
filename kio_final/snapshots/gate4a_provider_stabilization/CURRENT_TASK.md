# CURRENT TASK: Gate 4A Entrypoint — Provider Lifecycle Harden

Target:   mini_kio/llm/provider_manager.py
Contract: Harden provider registration, health tracking, and failover
          selection logic. No runtime changes. No conversational changes.

## Scope (exact)

- ProviderManager.register_provider() — duplicate registration handling,
  provider_name validation, health metric initialization
- ProviderManager.record_failure() — state transition edge cases
- ProviderManager.get_health_status() — deterministic query
- ProviderManager._select_provider() — failover logic hardening

## NOT in Scope

- llm_gateway.py (already normalized in Gate 3)
- provider_base.py (contract review only if needed)
- Any core/ runtime file
- Any context/ file
- Any conversational changes
- Real provider integration

## Entry Criteria

- [ ] Branch: gate4_foundance
- [ ] Working tree clean
- [ ] 89/89 Gate 3 tests passing
- [ ] No pending changes in core/ or runtime/

## Exit Criteria

- [ ] All 89 Gate 3 tests still pass
- [ ] No new lint or type errors
- [ ] Provider health transitions are deterministic
- [ ] Circuit breaker state machine handles: registration, failure,
      cooldown, recovery, re-registration
- [ ] Failover selection logic has edge-case coverage
- [ ] gitnexus_detect_changes() confirms scope
