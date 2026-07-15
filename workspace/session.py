from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class WorkspaceSession(Protocol):
    """Protocol defining a session lifecycle for a workspace.

    Implementations manage a logical grouping of work within a workspace.
    All methods are abstract and must be provided by concrete classes.
    """

    def create(self, *args: Any, **kwargs: Any) -> None:
        """Create a new session.

        Parameters are implementation‑specific and may include configuration
        details required to initialise the session.
        """
        ...

    def open(self) -> None:
        """Open the session for interaction.

        Raises
        ------
        RuntimeError
            If the session cannot be opened (e.g., already open or closed).
        """
        ...

    def close(self) -> None:
        """Close the session, releasing any allocated resources.

        After closing, the session should not be used unless ``create``
        is called again.
        """
        ...

    def list(self) -> list[Any]:
        """Return a list of items (e.g., tasks, resources) associated with the session.
        """
        ...

    def destroy(self) -> None:
        """Destroy the session permanently.

        This is a stronger operation than ``close``; it removes all persistent
        state associated with the session.
        """
        ...

    def current(self) -> Any:
        """Return the current active element of the session, if any.
        """
        ...
