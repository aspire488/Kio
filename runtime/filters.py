from __future__ import annotations

from typing import Callable, Iterable, List

from .observation import Observation, ObservationSeverity


class BaseFilter:
    """Callable filter that returns True if observation passes."""

    def __call__(self, observation: Observation) -> bool:
        raise NotImplementedError


class SeverityFilter(BaseFilter):
    def __init__(self, severity: ObservationSeverity):
        self._severity = severity

    def __call__(self, observation: Observation) -> bool:
        return observation.severity == self._severity


class ProviderFilter(BaseFilter):
    def __init__(self, provider: str):
        self._provider = provider

    def __call__(self, observation: Observation) -> bool:
        return observation.provider == self._provider


class SubsystemFilter(BaseFilter):
    def __init__(self, subsystem: str):
        self._subsystem = subsystem

    def __call__(self, observation: Observation) -> bool:
        return observation.subsystem == self._subsystem


class ActionFilter(BaseFilter):
    def __init__(self, action: str):
        self._action = action

    def __call__(self, observation: Observation) -> bool:
        return observation.action == self._action


class CompositeFilter(BaseFilter):
    def __init__(self, filters: Iterable[BaseFilter]):
        self._filters: List[BaseFilter] = list(filters)

    def __call__(self, observation: Observation) -> bool:
        return all(f(observation) for f in self._filters)
