from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..data_models import TrainingResource
from .utils import append_unique, tokenize


@dataclass(frozen=True)
class KeywordIndex:
    _token_to_resources: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "KeywordIndex":
        token_map: dict[str, list[str]] = defaultdict(list)
        for uri, resource in resources.items():
            tokens = _collect_keyword_tokens(resource)
            for token in tokens:
                append_unique(token_map[token], uri)
        immutable = {token: tuple(uris) for token, uris in token_map.items()}
        return cls(MappingProxyType(immutable))

    def lookup(self, query: str, limit: int | None = None) -> list[str]:
        tokens = tokenize(query)
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
        for token in tokenize(text):
            tokens.add(token)
    return tokens
