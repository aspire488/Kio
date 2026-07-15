"""Generic provider manifest loader.

Scans the ``providers`` directory for subfolders containing a ``provider.yaml``
file and returns a dictionary mapping provider id to manifest contents.
The loader does not assume any specific provider implementation – it only
parses the static yaml data.
"""

from __future__ import annotations

import os
import yaml  # type: ignore
from pathlib import Path
from typing import Dict, Any

def load_provider_manifests(base_dir: Path | None = None) -> Dict[str, Dict[str, Any]]:
    """Load all ``provider.yaml`` files under ``providers``.

    Returns a mapping of provider ``id`` to the parsed manifest dictionary.
    """
    base = base_dir or Path(__file__).parent
    manifests: Dict[str, Dict[str, Any]] = {}
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        yaml_path = entry / "provider.yaml"
        if yaml_path.is_file():
            try:
                with yaml_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                pid = data.get("id") or entry.name
                manifests[pid] = data
            except Exception:
                # Skip invalid manifests – they will be reported elsewhere.
                continue
    return manifests

__all__ = ["load_provider_manifests"]
