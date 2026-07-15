# Gate 2.4: Operator Result Schema (Canonical Format)

## 1. Canonical Result Structure
Every operator execution must return a dictionary conforming to this schema. The schema provides deterministic execution contracts, runtime telemetry, and lifecycle metadata without embedding verification or confidence semantics in the operator itself.

```json
{
  "success": "bool",
  "data": "dict",
  "error": {
    "code": "string | null",
    "message": "string | null",
    "stack": "string | null"
  },
  "telemetry": {
    "duration_ms": "float",
    "ram_delta_mb": "float",
    "peak_ram_mb": "float"
  },
  "metadata": {
    "tool_name": "string",
    "tool_version": "string",
    "side_effect": "NONE | READ | WRITE | DESTRUCTIVE",
    "pid": "int | null",
    "lifecycle": "standard | uwp | singleton",
    "execution_id": "string"
  }
}
```

## 2. Field Definitions

### 2.1 Success Semantics
- `success: true`: The operator completed its execution path and returned a valid result.
- `success: false`: The operator failed, timed out, was aborted by ResourceGuard, or returned a terminal error.

### 2.2 Error
- `code`: A normalized error code or `null`.
- `message`: Human-readable error text or `null`.
- `stack`: Stack information for diagnostics or `null`.

### 2.3 Telemetry
- `duration_ms`: Execution elapsed time in milliseconds.
- `ram_delta_mb`: Change in resident memory from start to end.
- `peak_ram_mb`: Highest resident memory observed during execution.

### 2.4 Metadata
- `tool_name`: The operator/tool identity.
- `tool_version`: The deployed version of the operator.
- `side_effect`: Declared side-effect classification for runtime policy.
- `pid`: Primary process ID if applicable.
- `lifecycle`: Execution lifecycle category for cleanup semantics.
- `execution_id`: Unique identifier for correlation with runtime audit logs.

## 3. Validation Compatibility
- Operators do not return verification decisions or confidence values.
- The runtime layer uses `success`, telemetry, and metadata to perform deterministic execution validation and lifecycle enforcement.
- This schema is intentionally lightweight and deterministic to preserve KIO Architecture v1.1 discipline.
