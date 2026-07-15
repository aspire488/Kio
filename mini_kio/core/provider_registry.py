"""ProviderRegistry — singleton mapping capability names to provider instances."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth

logger = logging.getLogger(__name__)


class ProviderRegistry:
    _instance: ProviderRegistry | None = None
    _providers: dict[str, ExecutionProvider] = {}
    _provider_ids: dict[str, ExecutionProvider] = {}

    def __new__(cls) -> ProviderRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._providers = {}
            cls._provider_ids = {}
        return cls._instance

    def register(self, provider: ExecutionProvider) -> None:
        pid = provider.id()
        self._provider_ids[pid] = provider
        for cap in provider.capabilities():
            existing = self._providers.get(cap.name)
            if existing is not None and existing is not provider:
                continue
            self._providers[cap.name] = provider

    def get_provider(self, capability: str) -> ExecutionProvider | None:
        provider = self._providers.get(capability)
        if provider is not None and provider.health() == ProviderHealth.OFFLINE:
            return None
        return provider

    def get_provider_by_id(self, provider_id: str) -> ExecutionProvider | None:
        return self._provider_ids.get(provider_id)

    def all_capabilities(self) -> list[str]:
        return list(self._providers.keys())

    def all_providers(self) -> list[ExecutionProvider]:
        seen: set[int] = set()
        result: list[ExecutionProvider] = []
        for p in self._providers.values():
            pid = id(p)
            if pid not in seen:
                seen.add(pid)
                result.append(p)
        return result

    def healthy_providers(self) -> list[ExecutionProvider]:
        return [p for p in self.all_providers() if p.health() == ProviderHealth.HEALTHY]

    def has_capability(self, capability: str) -> bool:
        return self.get_provider(capability) is not None

    def reset(self) -> None:
        self._providers.clear()
        self._provider_ids.clear()


def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry()


def reset_provider_registry() -> None:
    ProviderRegistry._instance = None
    ProviderRegistry._providers = {}
    ProviderRegistry._provider_ids = {}
