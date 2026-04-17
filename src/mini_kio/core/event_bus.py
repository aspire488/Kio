import logging
from typing import Callable, Any, Dict, List

logger = logging.getLogger(__name__)

_subscribers: Dict[str, List[Callable[[Any], None]]] = {}

def subscribe(event: str, handler: Callable[[Any], None]) -> None:
    if event not in _subscribers:
        _subscribers[event] = []
    _subscribers[event].append(handler)
    logger.debug(f"Subscribed to event {event}.")

def publish(event: str, payload: Any = None) -> None:
    handlers = _subscribers.get(event, [])
    logger.debug(f"Publishing event {event} to {len(handlers)} handlers.")
    for handler in handlers:
        try:
            handler(payload)
        except Exception as e:
            logger.error(f"Error in event handler for {event}: {e}")
