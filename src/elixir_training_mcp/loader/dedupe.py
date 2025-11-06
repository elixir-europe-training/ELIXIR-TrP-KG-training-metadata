from __future__ import annotations

from typing import MutableMapping

from rdflib import Graph
from rdflib.term import BNode, Node, URIRef

from ..data_models import TrainingResource
from .utils import first_value_as_str, schema_predicates


def resolve_resource_identifier(graph: Graph, subject: Node) -> str | None:
    """Return a canonical identifier for a resource subject."""
    url = first_value_as_str(graph, subject, *schema_predicates("url"))
    if url:
        return url
    if isinstance(subject, URIRef):
        return str(subject)
    if isinstance(subject, BNode):
        return str(subject)
    return None


def resource_quality(resource: TrainingResource) -> int:
    """Score resources so richer metadata wins during deduplication."""
    scalar_fields = [
        "name",
        "description",
        "abstract",
        "headline",
        "url",
        "provider",
        "language",
        "interactivity_type",
        "license_url",
        "accessibility_summary",
        "is_accessible_for_free",
        "is_family_friendly",
        "creative_work_status",
        "version",
        "date_published",
        "date_modified",
    ]
    collection_fields = [
        "keywords",
        "topics",
        "identifiers",
        "authors",
        "contributors",
        "prerequisites",
        "teaches",
        "learning_resource_types",
        "educational_levels",
        "access_modes",
        "access_mode_sufficient",
        "accessibility_controls",
        "accessibility_features",
        "audience_roles",
        "course_instances",
    ]

    score = 0
    for field in scalar_fields:
        value = getattr(resource, field)
        if value:
            score += 1

    for field in collection_fields:
        value = getattr(resource, field)
        if value and len(value) > 0:
            score += 1

    return score


def is_richer_resource(candidate: TrainingResource, current: TrainingResource) -> bool:
    """Return True when the candidate resource contains richer metadata."""
    return resource_quality(candidate) > resource_quality(current)


def select_richest(
    resources: MutableMapping[str, TrainingResource],
    resource: TrainingResource,
) -> None:
    """
    Place the richer representation in a resource map.

    Mutates ``resources`` in place, mirroring the original behaviour in
    ``data_store``.
    """
    existing = resources.get(resource.uri)
    if existing is None or is_richer_resource(resource, existing):
        resources[resource.uri] = resource
