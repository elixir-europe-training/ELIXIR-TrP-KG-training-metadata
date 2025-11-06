from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..data_models import TrainingResource
from .utils import append_unique


@dataclass(frozen=True)
class ProviderIndex:
    _provider_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "ProviderIndex":
        provider_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            if resource.provider and resource.provider.name:
                key = resource.provider.name.strip().lower()
                append_unique(provider_map[key], uri)
        immutable = {provider: tuple(uris) for provider, uris in provider_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, provider_name: str, limit: int | None = None) -> list[str]:
        key = provider_name.strip().lower()
        results = list(self._provider_to_resources.get(key, ()))
        if limit is not None:
            return results[:limit]
        return results
