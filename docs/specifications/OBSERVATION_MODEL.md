# Observation Model

The **Observation** is an immutable data record describing a single runtime event.

```python
@dataclass(frozen=True, slots=True)
class Observation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    subsystem: str = ""
    provider: str = ""
    action: str = ""
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    success: bool = True
    duration_ms: Optional[int] = None
    severity: ObservationSeverity = ObservationSeverity.INFO
    metadata: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Any]] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    type: ObservationType = ObservationType.CUSTOM
```

## Enums

* **ObservationSeverity** – DEBUG, INFO, WARNING, ERROR, CRITICAL
* **ObservationType** – EXECUTION, WORKFLOW, PROVIDER, BROWSER, VOICE, AVATAR, COMMUNICATION, SYSTEM, CUSTOM

All fields are optional except those with default factories, making the model easy to construct in production code.
