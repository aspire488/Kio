"""Workspace protocol for internal API.

Defines abstract file system operations required by KIO components.
"""

from __future__ import annotations
from typing import Protocol, Iterable


class Workspace(Protocol):
    """Abstract file system interactions used by adapters."""

    def read_file(self, path: str) -> str: ...
    """Read the entire contents of a file at *path* and return as a string."""

    def write_file(self, path: str, content: str) -> None: ...
    """Write *content* to a file at *path*, overwriting if it exists."""

    def list_dir(self, path: str) -> Iterable[str]: ...
    """List entries in a directory, returning filenames relative to *path*."""
