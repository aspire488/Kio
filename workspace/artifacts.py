from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable, Iterable


@dataclass
class Artifact:
    """Simple data holder for a workspace artifact.

    Attributes
    ----------
    id: str
        Unique identifier for the artifact.
    name: str
        Human‑readable name.
    type: str
        Type or category of the artifact.
    metadata: Dict[str, Any]
        Additional arbitrary data.
    """

    id: str
    name: str
    type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ArtifactStore(Protocol):
    """Protocol for persisting and retrieving :class:`Artifact` objects.

    Concrete implementations decide the storage backend (in‑memory, DB, etc.).
    """

    def save(self, artifact: Artifact) -> None:
        """Persist ``artifact``.
        """
        ...

    def load(self, artifact_id: str) -> Artifact:
        """Load and return the artifact with ``artifact_id``.
        """
        ...

    def delete(self, artifact_id: str) -> None:
        """Delete the artifact identified by ``artifact_id``.
        """
        ...

    def exists(self, artifact_id: str) -> bool:
        """Return ``True`` if an artifact with ``artifact_id`` exists.
        """
        ...

    def list(self) -> Iterable[Artifact]:
        """Iterate over all stored artifacts.
        """
        ...
