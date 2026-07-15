"""Adapter discovery utilities.

Scans the ``adapters`` package for python modules that represent adapters.
Each adapter module must define:
- ``__adapter_id__`` (str) – unique identifier
- ``__version__`` (str) – version string
- ``CAPABILITIES`` (list[str]) – optional capability list
- optionally a ``health`` function for health aggregation
"""

import importlib.util
import os
from pathlib import Path
from typing import List

from .types import AdapterInfo, AdapterState

class AdapterDiscovery:
    """Discover adapter modules in the ``adapters`` directory."""

    def __init__(self, base_path: Path = Path(__file__).parent):
        self.base_path = base_path

    def scan(self) -> List[AdapterInfo]:
        infos: List[AdapterInfo] = []
        for entry in self.base_path.iterdir():
            if entry.is_file() and entry.suffix == ".py" and entry.name not in {"__init__.py", "exceptions.py", "types.py", "loader.py", "health.py", "registry.py", "discovery.py"}:
                module_name = entry.stem
                spec = importlib.util.spec_from_file_location(module_name, entry)
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)  # type: ignore[assignment]
                except Exception:
                    # Skip modules that cannot be imported – they'll raise on load.
                    continue
                adapter_id = getattr(module, "__adapter_id__", module_name)
                version = getattr(module, "__version__", "0.0.0")
                capabilities = getattr(module, "CAPABILITIES", [])
                info = AdapterInfo(
                    id=adapter_id,
                    version=version,
                    capabilities=capabilities,
                    state=AdapterState.REGISTERED,
                    module=module_name,
                )
                infos.append(info)
        return infos