"""Provider system protocol for internal API.

Abstracts external services such as LLMs, storage, or other providers.
"""

from __future__ import annotations
from typing import Protocol, Any, Mapping


class Provider(Protocol):
    """Base protocol for a service provider.

    Implementations expose a ``call`` method that takes arbitrary input and
    returns a provider‑specific response.
    """

    def call(self, request: Any, *, context: Mapping[str, Any] | None = None) -> Any: ...
