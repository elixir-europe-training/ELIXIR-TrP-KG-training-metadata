from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from collections import defaultdict
import re

from rdflib import Dataset

from .data_models import (
    CourseInstance as _CourseInstance,
    Organization as _Organization,
    TrainingResource,
    literal_to_datetime as _literal_to_datetime,
    literal_to_float as _literal_to_float,
    literal_to_int as _literal_to_int,
    literal_to_str as _literal_to_str,
    literals_to_strings as _literals_to_strings,
)
from .loader import extract_resources_from_graph, load_dataset
from .loader.dedupe import select_richest

# Re-export selected data model helpers for compatibility.
CourseInstance = _CourseInstance
Organization = _Organization
literal_to_datetime = _literal_to_datetime
literal_to_float = _literal_to_float
literal_to_int = _literal_to_int
literal_to_str = _literal_to_str
literals_to_strings = _literals_to_strings

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class KeywordIndex:
    _token_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "KeywordIndex":
        token_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            tokens = _collect_keyword_tokens(resource)
            for token in tokens:
                _append_unique(token_map[token], uri)
        immutable = {token: tuple(uris) for token, uris in token_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, query: str, limit: int | None = None) -> list[str]:
        tokens = _tokenize(query)
        seen_set: set[str] = set()
        seen_list: list[str] = []
        for token in tokens:
            for uri in self._token_to_resources.get(token, ()):
                if uri not in seen_set:
                    seen_set.add(uri)
                    seen_list.append(uri)
                    if limit is not None and len(seen_list) >= limit:
                        return seen_list
        return seen_list


@dataclass(frozen=True)
class ProviderIndex:
    _provider_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "ProviderIndex":
        provider_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            if resource.provider and resource.provider.name:
                key = resource.provider.name.strip().lower()
                _append_unique(provider_map[key], uri)
        immutable = {provider: tuple(uris) for provider, uris in provider_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, provider_name: str, limit: int | None = None) -> list[str]:
        key = provider_name.strip().lower()
        results = list(self._provider_to_resources.get(key, ()))
        if limit is not None:
            return results[:limit]
        return results


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
                _append_unique(country_map[country_key], uri)

                if instance.locality:
                    city_key = instance.locality.strip().lower()
                    _append_unique(country_city_map[(country_key, city_key)], uri)

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


@dataclass(frozen=True)
class CourseSchedule:
    resource_uri: str
    start: datetime
    end: datetime | None = None


@dataclass(frozen=True)
class DateIndex:
    _schedules: tuple[CourseSchedule, ...]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "DateIndex":
        schedules: list[CourseSchedule] = []
        for uri, resource in resources.items():
            for instance in resource.course_instances:
                if instance.start_date is None:
                    continue
                schedules.append(
                    CourseSchedule(
                        resource_uri=uri,
                        start=instance.start_date,
                        end=instance.end_date,
                    )
                )
        schedules.sort(key=lambda schedule: schedule.start)
        return cls(tuple(schedules))

    def lookup(
        self,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        limit: int | None = None,
    ) -> list[str]:
        start_dt = _normalize_datetime_input(start)
        end_dt = _normalize_datetime_input(end)

        results: list[str] = []
        for schedule in self._schedules:
            if start_dt:
                if schedule.end:
                    if schedule.end < start_dt:
                        continue
                elif schedule.start < start_dt:
                    continue
            if end_dt and schedule.start > end_dt:
                continue
            if schedule.resource_uri not in results:
                results.append(schedule.resource_uri)
                if limit is not None and len(results) >= limit:
                    break
        return results


@dataclass(frozen=True)
class TopicIndex:
    _topic_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "TopicIndex":
        topic_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            for topic in resource.topics:
                normalized_topic = topic.strip().lower()
                _append_unique(topic_map[normalized_topic], uri)
                if "/" in topic:
                    short_name = topic.rsplit("/", 1)[-1].lower()
                    _append_unique(topic_map[short_name], uri)
        immutable = {topic: tuple(uris) for topic, uris in topic_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, topic: str, limit: int | None = None) -> list[str]:
        key = topic.strip().lower()
        results = list(self._topic_to_resources.get(key, ()))
        if limit is not None:
            return results[:limit]
        return results


@dataclass(frozen=True)
class TrainingDataStore:
    dataset: Dataset
    resources_by_uri: Mapping[str, TrainingResource]
    per_source_counts: Mapping[str, int]
    load_timestamp: datetime
    source_graphs: Mapping[str, str]
    keyword_index: "KeywordIndex"
    provider_index: "ProviderIndex"
    location_index: "LocationIndex"
    date_index: "DateIndex"
    topic_index: "TopicIndex"
    stats: Mapping[str, Any]

    @property
    def resource_count(self) -> int:
        return len(self.resources_by_uri)


def load_training_data(source_paths: Mapping[str, Path]) -> TrainingDataStore:
    dataset, graphs_by_source, source_graphs = load_dataset(source_paths)
    resource_map: dict[str, TrainingResource] = {}
    per_source_counts: dict[str, int] = {}

    for source_key, graph in graphs_by_source.items():
        resources = extract_resources_from_graph(graph, source_key)
        per_source_counts[source_key] = len(resources)
        for resource in resources.values():
            select_richest(resource_map, resource)

    timestamp = datetime.now(timezone.utc)
    keyword_index, provider_index, location_index, date_index, topic_index = _build_indexes(resource_map)
    stats = _build_stats(resource_map, per_source_counts, timestamp)

    return TrainingDataStore(
        dataset=dataset,
        resources_by_uri=MappingProxyType(resource_map),
        per_source_counts=MappingProxyType(per_source_counts),
        load_timestamp=timestamp,
        source_graphs=MappingProxyType(source_graphs),
        keyword_index=keyword_index,
        provider_index=provider_index,
        location_index=location_index,
        date_index=date_index,
        topic_index=topic_index,
        stats=MappingProxyType(stats),
    )


def _build_indexes(
    resources: Mapping[str, TrainingResource],
) -> tuple[KeywordIndex, ProviderIndex, LocationIndex, DateIndex, TopicIndex]:
    keyword_index = KeywordIndex.from_resources(resources)
    provider_index = ProviderIndex.from_resources(resources)
    location_index = LocationIndex.from_resources(resources)
    date_index = DateIndex.from_resources(resources)
    topic_index = TopicIndex.from_resources(resources)
    return keyword_index, provider_index, location_index, date_index, topic_index


def _collect_keyword_tokens(resource: TrainingResource) -> set[str]:
    texts: list[str] = []
    for text in (
        resource.name,
        resource.description,
        resource.abstract,
        resource.headline,
        resource.interactivity_type,
        resource.language,
    ):
        if text:
            texts.append(text)

    texts.extend(resource.keywords)
    texts.extend(resource.learning_resource_types)
    texts.extend(resource.educational_levels)
    texts.extend(resource.prerequisites)
    texts.extend(resource.teaches)

    tokens: set[str] = set()
    for text in texts:
        for token in _tokenize(text):
            tokens.add(token)
    return tokens


def _build_stats(
    resources: Mapping[str, TrainingResource],
    per_source_counts: Mapping[str, int],
    timestamp: datetime,
) -> dict[str, Any]:
    type_distribution: defaultdict[str, int] = defaultdict(int)
    access_mode_distribution: defaultdict[str, int] = defaultdict(int)
    audience_role_distribution: defaultdict[str, int] = defaultdict(int)
    topic_example: dict[str, str] = {}

    for uri, resource in resources.items():
        for resource_type in resource.types:
            type_distribution[resource_type] += 1
        for access_mode in resource.access_modes:
            access_mode_distribution[access_mode] += 1
        for role in resource.audience_roles:
            audience_role_distribution[role] += 1
        if resource.topics:
            topic_example.setdefault(next(iter(resource.topics)), uri)

    stats: dict[str, Any] = {
        "loaded_at": timestamp.isoformat(),
        "total_resources": len(resources),
        "per_source": dict(per_source_counts),
        "type_distribution": dict(type_distribution),
        "access_modes": dict(access_mode_distribution),
        "audience_roles": dict(audience_role_distribution),
        "sample_topic_examples": topic_example,
    }

    return stats


def _tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    lower_text = text.lower()
    return list(TOKEN_PATTERN.findall(lower_text))


def _append_unique(bucket: list[str], value: str) -> None:
    if value not in bucket:
        bucket.append(value)


def _normalize_datetime_input(value: datetime | date | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    combined = datetime.combine(value, datetime.min.time()).replace(tzinfo=timezone.utc)
    return combined
