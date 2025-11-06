from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..data_models import TrainingResource
from .utils import append_unique


@dataclass(frozen=True)
class TopicIndex:
    _topic_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "TopicIndex":
        topic_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            for topic in resource.topics:
                normalized_topic = topic.strip().lower()
                append_unique(topic_map[normalized_topic], uri)
                if "/" in topic:
                    short_name = topic.rsplit("/", 1)[-1].lower()
                    append_unique(topic_map[short_name], uri)
        immutable = {topic: tuple(uris) for topic, uris in topic_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, topic: str, limit: int | None = None) -> list[str]:
        key = topic.strip().lower()
        results = list(self._topic_to_resources.get(key, ()))
        if limit is not None:
            return results[:limit]
        return results
