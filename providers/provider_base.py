from __future__ import annotations

from typing import Protocol, Mapping, Any, runtime_checkable

from .provider_metadata import ProviderMetadata
from .provider_result import ProviderResult

# Minimal placeholder for a health report – concrete implementations may
# define a richer TypedDict or dataclass elsewhere.
HealthReport = Mapping[str, Any]


@runtime_checkable
class Provider(Protocol):
    """Interface that all KIO v2 providers must implement.

    No runtime behavior is defined here; implementations provide concrete
    logic. The methods return the abstract types defined in the surrounding
    ``providers`` package.
    """

    def initialize(self) -> ProviderMetadata:
        """Prepare the provider and return its metadata.

        Implementations should perform any required startup work and return a
        ``ProviderMetadata`` instance reflecting the ready state.
        """
        ...

    def shutdown(self) -> ProviderMetadata:
        """Shut down the provider and return updated metadata.

        After shutdown the provider should be in ``ProviderState.STOPPED``.
        """
        ...

    def health(self) -> HealthReport:
        """Return a health report describing the current status of the provider.

        The exact structure is left to the implementation – a simple mapping with
        keys such as ``"state"`` and ``"details"`` is typical.
        """
        ...

    def capabilities(self) -> Mapping[str, Any]:
        """Describe the capabilities the provider offers.

        A mapping from capability name to a description or specification.
        """
        ...

    def metadata(self) -> ProviderMetadata:
        """Retrieve the current static metadata for the provider.
        """
        ...

    def execute(self, action: str, parameters: Mapping[str, Any] | None = None) -> ProviderResult:
        """Execute a named ``action`` with optional ``parameters``.

        Returns a ``ProviderResult`` capturing status, data, timing and any
        error information.
        """
        ...
