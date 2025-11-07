from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..data_models import TrainingResource
from .utils import append_unique


@dataclass(frozen=True)
class LocationIndex:
    _country_map: Mapping[str, tuple[str, ...]]
    _country_city_map: Mapping[tuple[str, str], tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "LocationIndex":
        country_map: dict[str, list[str]] = defaultdict(list)
        country_city_map: dict[tuple[str, str], list[str]] = defaultdict(list)

        for uri, resource in resources.items():
            for instance in resource.course_instances:
                if not instance.country:
                    continue
                country_key = instance.country.strip().lower()
                append_unique(country_map[country_key], uri)

                if instance.locality:
                    city_key = instance.locality.strip().lower()
                    append_unique(country_city_map[(country_key, city_key)], uri)

        immutable_country = {key: tuple(uris) for key, uris in country_map.items()}
        immutable_city = {key: tuple(uris) for key, uris in country_city_map.items()}
        return cls(
            MappingProxyType(immutable_country),
            MappingProxyType(immutable_city),
        )

    def lookup(self, country: str, city: str | None = None, limit: int | None = None) -> list[str]:
        country_key = country.strip().lower()
        if city:
            city_key = city.strip().lower()
            results = list(self._country_city_map.get((country_key, city_key), ()))
        else:
            results = list(self._country_map.get(country_key, ()))
        if limit is not None:
            return results[:limit]
        return results
