"""Health aggregation for loaded adapters.

Each adapter may implement a ``health`` method returning a ``bool`` or a dict
with ``status`` (bool) and optional ``details`` (str). The aggregator normalises
these into :class:`AdapterHealth` objects and reports an overall status.
"""

from typing import List, Tuple

from .types import AdapterHealth

class HealthAggregator:
    """Collect health information from adapters."""

    def aggregate(self, adapters: List[object]) -> Tuple[bool, List[AdapterHealth]]:
        """Return ``(overall_status, reports)``.

        ``overall_status`` is ``True`` only if all adapters report healthy.
        """
        reports: List[AdapterHealth] = []
        overall = True
        for adapter in adapters:
            adapter_id = getattr(adapter, "__adapter_id__", getattr(adapter, "__class__", type(adapter)).__name__)
            health_fn = getattr(adapter, "health", None)
            if not callable(health_fn):
                # Treat missing health as healthy
                reports.append(AdapterHealth(id=adapter_id, status=True))
                continue
            try:
                result = health_fn()
            except Exception:
                reports.append(AdapterHealth(id=adapter_id, status=False, details="exception"))
                overall = False
                continue
            if isinstance(result, dict):
                status = bool(result.get("status", False))
                details = result.get("details")
            else:
                status = bool(result)
                details = None
            reports.append(AdapterHealth(id=adapter_id, status=status, details=details))
            if not status:
                overall = False
        return overall, reports