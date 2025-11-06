from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from collections import defaultdict

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
from .indexes import (
    CourseSchedule,
    DateIndex,
    KeywordIndex,
    LocationIndex,
    ProviderIndex,
    TopicIndex,
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


@dataclass(frozen=True)
class TrainingDataStore:
    dataset: Dataset
    resources_by_uri: Mapping[str, TrainingResource]
    per_source_counts: Mapping[str, int]
    load_timestamp: datetime
    source_graphs: Mapping[str, str]
    keyword_index: KeywordIndex
    provider_index: ProviderIndex
    location_index: LocationIndex
    date_index: DateIndex
    topic_index: TopicIndex
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
