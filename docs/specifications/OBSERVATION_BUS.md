# Observation Bus Specification

The **ObservationBus** is the single runtime mechanism for propagating `Observation` objects.

## Public API

| Method | Description |
|--------|-------------|
| `register(subscriber: Subscriber)` / `subscribe` | Add a subscriber. Subscribers are ordered by `priority()` (higher first). |
| `unregister(subscriber: Subscriber)` / `unsubscribe` | Remove a subscriber. |
| `publish(observation: Observation)` | Record the observation in bounded history and deliver it to all subscribers that `supports` it. Delivery is performed asynchronously so one slow subscriber never blocks others. |
| `publish_many(observations: Iterable[Observation])` | Convenience wrapper to publish a sequence. |
| `history() -> List[Observation]` | Return a copy of the FIFO history (capacity configurable at construction). |
| `clear()` | Empty history and reset statistics. |
| `statistics() -> dict` | Aggregate counts: total, per‑provider, per‑subsystem, per‑severity. |

## Thread‑Safety Guarantees

* Registration / unregistration are protected by a lock.
* History is a thread‑safe bounded FIFO (`collections.deque`).
* Publishing never blocks on subscriber processing – each subscriber runs in a `ThreadPoolExecutor` worker.
* Exceptions raised by a subscriber are caught and logged; they do not affect other subscribers.

## Configuration

```python
bus = ObservationBus(history_capacity=5000, max_workers=8)
```

* `history_capacity` – maximum number of observations retained (FIFO eviction).
* `max_workers` – size of the thread pool used for delivery.

The bus has no external dependencies and does not import any **AURA**, **providers**, or **adapters**.
