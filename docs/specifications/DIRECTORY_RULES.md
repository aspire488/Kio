# Directory Rules

## Import Rules

- Upper layers may import only from lower‑level packages.
- No module in `aura/` may import from `runtime/` or `execution/`.
- `adapters/` may import from `providers/` but not vice‑versa.

## Allowed Dependencies

- `runtime/` → `providers/`, `execution/`, `communication/`.
- `execution/` → `runtime/`, `aura/`.
- `voice/` → `runtime/`.
- `avatar/` → `runtime/`.

## Forbidden Dependencies

- No circular imports.
- No direct imports from `external/` repositories.
- `governance/` must not import from `adapters/`.

## Layering Rules

1. **External** (adapters) → **Provider** → **Core Runtime** → **Execution** → **AURA**.
2. Dependencies flow only inward; higher layers must not depend on lower‑level implementation details.

## Naming Conventions

- Packages: snake_case.
- Modules: snake_case.
- Classes: PascalCase.
- Functions/variables: snake_case.

## Ownership Rules

- Each top‑level directory is owned by the team listed in its README.
- Ownership determines responsibility for reviewing changes.

---

*ponytail: omitted formal policy matrix – add when governance requires formal compliance.*