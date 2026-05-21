# KIO Gate 2.4: Architectural Constraints

## Runtime Constraints
- **RAM Limit**: Process RSS must never exceed 190MB (Hard Limit) and should remain < 170MB during multi-operator stress.
- **Single Process**: All operations must remain within the single Python/asyncio process. No multi-processing (v1.1 §4).
- **Non-Blocking**: No `time.sleep()` in any operator. Use `asyncio.sleep()` or threaded offloading for blocking I/O.
- **Lazy Loading**: Operators must only be fully initialised on demand to preserve idle RAM (v1.1 §3).

## Security Constraints
- **No Shell=True**: Absolute ban on `shell=True` in `subprocess` calls using user-derived input.
- **Confirmation Gate**: DESTRUCTIVE class operations (system shutdown/restart) must be mapped but remain blocked without explicit logic for user confirmation.
- **Path Sanitization**: Filesystem operations must be constrained to safe, absolute paths.
