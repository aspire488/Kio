"""Central Adapter Registry.

Provides discovery, registration, lazy loading, health aggregation and
metadata queries. Designed to be a singleton – ``AdapterRegistry.instance()``
returns the global registry.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Any

from .exceptions import (
    AdapterError,
    AdapterLoadError,
    AdapterRegistrationError,
    AdapterValidationError,
)
from .types import AdapterInfo, AdapterState, AdapterHealth
from .discovery import AdapterDiscovery
from .loader import AdapterLoader
from .health import HealthAggregator

class AdapterRegistry:
    _instance: Optional["AdapterRegistry"] = None
    _lock = threading.Lock()

    def __init__(self, adapters_dir: Path = Path(__file__).parent):
        self.adapters_dir = adapters_dir
        self._infos: Dict[str, AdapterInfo] = {}
        self._instances: Dict[str, Any] = {}
        self._discovery = AdapterDiscovery(self.adapters_dir)
        self._loader = AdapterLoader(self.adapters_dir)
        self._health_aggregator = HealthAggregator()

    @classmethod
    def instance(cls) -> "AdapterRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ---------- Discovery & Registration ----------
    def discover(self) -> List[AdapterInfo]:
        """Discover adapters on disk and register their metadata.

        Returns a list of discovered :class:`AdapterInfo` objects.
        """
        infos = self._discovery.scan()
        for info in infos:
            self.register(info)
        return infos

    def register(self, info: AdapterInfo) -> None:
        if info.id in self._infos:
            raise AdapterRegistrationError(f"Adapter id '{info.id}' already registered")
        self._infos[info.id] = info

    def unregister(self, adapter_id: str) -> None:
        self.shutdown(adapter_id)
        self._infos.pop(adapter_id, None)
        self._instances.pop(adapter_id, None)

    # ---------- Loading ----------
    def load(self, adapter_id: str) -> Any:
        if adapter_id in self._instances:
            return self._instances[adapter_id]
        info = self._infos.get(adapter_id)
        if not info:
            raise AdapterLoadError(f"Adapter '{adapter_id}' not known")
        instance = self._loader.load(info)
        self._instances[adapter_id] = instance
        # update state
        self._infos[adapter_id] = AdapterInfo(
            id=info.id,
            version=info.version,
            capabilities=info.capabilities,
            state=AdapterState.LOADED,
            module=info.module,
        )
        return instance

    def reload(self, adapter_id: str) -> Any:
        self.shutdown(adapter_id)
        # remove cached instance
        self._instances.pop(adapter_id, None)
        return self.load(adapter_id)

    # ---------- Shutdown ----------
    def shutdown(self, adapter_id: str) -> None:
        instance = self._instances.get(adapter_id)
        if not instance:
            return
        shutdown_fn = getattr(instance, "shutdown", None)
        if callable(shutdown_fn):
            try:
                shutdown_fn()
            except Exception as exc:
                raise AdapterError(f"Shutdown failed for '{adapter_id}': {exc}")
        # mark state
        info = self._infos.get(adapter_id)
        if info:
            self._infos[adapter_id] = AdapterInfo(
                id=info.id,
                version=info.version,
                capabilities=info.capabilities,
                state=AdapterState.SHUTDOWN,
                module=info.module,
            )
        self._instances.pop(adapter_id, None)

    def shutdown_all(self) -> None:
        for aid in list(self._instances.keys()):
            self.shutdown(aid)

    # ---------- Query API ----------
    def get(self, adapter_id: str) -> Optional[Any]:
        return self._instances.get(adapter_id)

    def list(self) -> List[str]:
        return list(self._infos.keys())

    def capabilities(self) -> List[str]:
        caps = []
        for info in self._infos.values():
            caps.extend(info.capabilities)
        return list(set(caps))

    def versions(self) -> Dict[str, str]:
        return {aid: info.version for aid, info in self._infos.items()}

    def health(self) -> Dict[str, Any]:
        overall, reports = self._health_aggregator.aggregate(list(self._instances.values()))
        return {"overall": overall, "reports": reports}

    def validate(self) -> None:
        """Validate that each registered adapter meets minimal interface.

        Currently checks that a loaded adapter (if any) has a ``health`` callable.
        """
        for aid, info in self._infos.items():
            instance = self._instances.get(aid)
            if instance is None:
                continue  # Not loaded yet – cannot validate fully
            if not callable(getattr(instance, "health", None)):
                raise AdapterValidationError(f"Adapter '{aid}' missing required 'health' method")