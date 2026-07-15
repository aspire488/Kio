"""Adapter loading utilities.

Handles dynamic import of adapter modules and instantiation of a standard
``Adapter`` class defined therein. Validation of the loaded instance is
performed by the registry.
"""

import importlib
from pathlib import Path
from typing import Any

from .exceptions import AdapterLoadError
from .types import AdapterInfo

class AdapterLoader:
    """Load and instantiate adapters given their ``AdapterInfo``."""

    def __init__(self, adapters_dir: Path = Path(__file__).parent):
        self.adapters_dir = adapters_dir

    def load(self, info: AdapterInfo) -> Any:
        """Import the module and instantiate ``Adapter``.

        The module must define a class named ``Adapter`` (or a callable ``adapter``).
        """
        try:
            module_path = self.adapters_dir / f"{info.module}.py"
            spec = importlib.util.spec_from_file_location(info.module, module_path)
            if not spec or not spec.loader:
                raise ImportError(f"Cannot find spec for {info.module}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[assignment]
        except Exception as exc:
            raise AdapterLoadError(f"Failed to import adapter '{info.id}': {exc}") from exc

        # Prefer a class named Adapter, else a callable named adapter
        adapter_cls = getattr(module, "Adapter", None)
        if adapter_cls is None:
            adapter_callable = getattr(module, "adapter", None)
            if callable(adapter_callable):
                return adapter_callable()
            raise AdapterLoadError(f"Adapter '{info.id}' does not define an Adapter class or callable.")
        try:
            return adapter_cls()
        except Exception as exc:
            raise AdapterLoadError(f"Failed to instantiate Adapter for '{info.id}': {exc}") from exc