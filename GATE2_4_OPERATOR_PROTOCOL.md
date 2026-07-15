# KIO Operator Protocol v1.1

## 1. Operator Contract Structure
Every operator must implement the `KIOTool` protocol:
- `name`: Unique string identifier.
- `side_effect_class`: `NONE | READ | WRITE | DESTRUCTIVE`.
- `ram_budget_mb`: Declared maximum RAM usage for admission control.
- `execute(args, context)`: Async execution returning `ToolResult`.

## 2. Response Schema
```json
{
  "success": "boolean",
  "output": "object | string",
  "error": "string | null",
  "telemetry": {
    "elapsed_ms": "integer",
    "ram_peak_mb": "float"
  }
}
```

## 3. Side-Effect Classification
- **DESTRUCTIVE**: Requires explicit user confirmation via Core Brain.
- **WRITE**: Logged to append-only audit trail.
- **READ/NONE**: Automated execution allowed.

## 4. Lifecycle Hooks
- `on_load()`: ResourceGuard admission check.
- `on_unload()`: GC collect and state cleanup.
