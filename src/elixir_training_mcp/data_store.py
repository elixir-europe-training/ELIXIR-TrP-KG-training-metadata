from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from rdflib import Dataset, Graph, Namespace
from rdflib.namespace import RDF
from rdflib.term import BNode, Literal, Node, URIRef

from .data_models import (
    CourseInstance,
    Organization,
    TrainingResource,
    literal_to_datetime,
    literal_to_float,
    literal_to_int,
    literal_to_str,
    literals_to_strings,
)

SCHEMA = Namespace("http://schema.org/")
DCT = Namespace("http://purl.org/dc/terms/")

RESOURCE_TYPES = (
    SCHEMA.Course,
    SCHEMA.LearningResource,
    SCHEMA.Event,
)


@dataclass(frozen=True)
class TrainingDataStore:
    dataset: Dataset
    resources_by_uri: Mapping[str, TrainingResource]
    per_source_counts: Mapping[str, int]
    load_timestamp: datetime
    source_graphs: Mapping[str, str]

    @property
    def resource_count(self) -> int:
        return len(self.resources_by_uri)


def load_training_data(source_paths: Mapping[str, Path]) -> TrainingDataStore:
    dataset = Dataset()
    resource_map: dict[str, TrainingResource] = {}
    per_source_counts: dict[str, int] = {}
    source_graphs: dict[str, str] = {}

    for source_key, file_path in source_paths.items():
        if not file_path.exists():
            raise FileNotFoundError(f"TTL file not found for source '{source_key}': {file_path}")

        graph_uri = URIRef(f"urn:graph:{source_key}")
        graph = dataset.graph(graph_uri)
        graph.parse(str(file_path), format="ttl")
        source_graphs[source_key] = str(graph_uri)

        resources = _extract_resources_from_graph(graph, source_key)
        per_source_counts[source_key] = len(resources)

        for uri, resource in resources.items():
            resource_map[uri] = resource

    timestamp = datetime.now(timezone.utc)

    return TrainingDataStore(
        dataset=dataset,
        resources_by_uri=MappingProxyType(resource_map),
        per_source_counts=MappingProxyType(per_source_counts),
        load_timestamp=timestamp,
        source_graphs=MappingProxyType(source_graphs),
    )


def _extract_resources_from_graph(graph: Graph, source_key: str) -> dict[str, TrainingResource]:
    resources: dict[str, TrainingResource] = {}
    candidate_subjects: set[URIRef] = set()

    for rdf_type in RESOURCE_TYPES:
        for subject in graph.subjects(RDF.type, rdf_type):
            if isinstance(subject, URIRef):
                candidate_subjects.add(subject)

    for subject in candidate_subjects:
        resource = _build_training_resource(graph, subject, source_key)
        resources[resource.uri] = resource

    return resources


def _build_training_resource(graph: Graph, subject: URIRef, source_key: str) -> TrainingResource:
    types = frozenset(str(obj) for obj in graph.objects(subject, RDF.type))
    name = literal_to_str(_first_literal(graph, subject, SCHEMA.name))
    description = literal_to_str(_first_literal(graph, subject, SCHEMA.description))
    abstract = literal_to_str(_first_literal(graph, subject, SCHEMA.abstract))
    headline = literal_to_str(_first_literal(graph, subject, SCHEMA.headline))
    url = _first_value_as_str(graph, subject, SCHEMA.url)
    provider = _extract_primary_organization(graph, subject, SCHEMA.provider)
    keywords = _collect_keywords(graph, subject)
    topics = _collect_topics(graph, subject)
    identifiers = _collect_identifiers(graph, subject)
    authors = _collect_node_strs(graph, subject, SCHEMA.author)
    contributors = _collect_node_strs(graph, subject, SCHEMA.contributor)
    prerequisites = literals_to_strings(graph.objects(subject, SCHEMA.coursePrerequisites))
    teaches = literals_to_strings(graph.objects(subject, SCHEMA.teaches))
    learning_resource_types = _collect_literal_strings(graph, subject, SCHEMA.learningResourceType)
    educational_levels = _collect_literal_strings(graph, subject, SCHEMA.educationalLevel)
    language = literal_to_str(_first_literal(graph, subject, SCHEMA.inLanguage))
    interactivity_type = literal_to_str(_first_literal(graph, subject, SCHEMA.interactivityType))
    license_url = _first_value_as_str(graph, subject, SCHEMA.license)

    published_dt, published_raw = literal_to_datetime(_first_literal(graph, subject, SCHEMA.datePublished))
    modified_dt, modified_raw = literal_to_datetime(_first_literal(graph, subject, SCHEMA.dateModified))

    course_instances = _collect_course_instances(graph, subject)

    return TrainingResource(
        uri=str(subject),
        source=source_key,
        types=types,
        name=name,
        description=description,
        abstract=abstract,
        headline=headline,
        url=url,
        provider=provider,
        keywords=keywords,
        topics=topics,
        identifiers=identifiers,
        authors=authors,
        contributors=contributors,
        prerequisites=prerequisites,
        teaches=teaches,
        learning_resource_types=learning_resource_types,
        educational_levels=educational_levels,
        language=language,
        interactivity_type=interactivity_type,
        license_url=license_url,
        date_published=published_dt,
        date_published_raw=published_raw,
        date_modified=modified_dt,
        date_modified_raw=modified_raw,
        course_instances=course_instances,
    )


def _collect_course_instances(graph: Graph, subject: URIRef) -> tuple[CourseInstance, ...]:
    instances: list[CourseInstance] = []
    for instance_node in graph.objects(subject, SCHEMA.hasCourseInstance):
        instance = _parse_course_instance(graph, instance_node)
        if instance:
            instances.append(instance)
    return tuple(instances)


def _parse_course_instance(graph: Graph, node: Node) -> CourseInstance | None:
    start_dt, start_raw = literal_to_datetime(_first_literal(graph, node, SCHEMA.startDate))
    end_dt, end_raw = literal_to_datetime(_first_literal(graph, node, SCHEMA.endDate))
    mode = literal_to_str(_first_literal(graph, node, SCHEMA.courseMode))
    capacity = literal_to_int(_first_literal(graph, node, SCHEMA.maximumAttendeeCapacity))

    country = locality = postal_code = street_address = None
    latitude = longitude = None

    location_node = _first_node(graph, node, SCHEMA.location)
    if location_node is not None:
        latitude = literal_to_float(_first_literal(graph, location_node, SCHEMA.latitude))
        longitude = literal_to_float(_first_literal(graph, location_node, SCHEMA.longitude))
        address_node = _first_node(graph, location_node, SCHEMA.address)
        if address_node is not None:
            country = literal_to_str(_first_literal(graph, address_node, SCHEMA.addressCountry))
            locality = literal_to_str(_first_literal(graph, address_node, SCHEMA.addressLocality))
            postal_code = literal_to_str(_first_literal(graph, address_node, SCHEMA.postalCode))
            street_address = literal_to_str(_first_literal(graph, address_node, SCHEMA.streetAddress))

    funders = _collect_organizations(graph, node, SCHEMA.funder)
    organizers = _collect_organizations(graph, node, SCHEMA.organizer)

    if not any([start_dt, start_raw, end_dt, end_raw, mode, capacity, country, locality]):
        return None

    return CourseInstance(
        start_date=start_dt,
        start_raw=start_raw,
        end_date=end_dt,
        end_raw=end_raw,
        mode=mode,
        capacity=capacity,
        country=country,
        locality=locality,
        postal_code=postal_code,
        street_address=street_address,
        latitude=latitude,
        longitude=longitude,
        funders=funders,
        organizers=organizers,
    )


def _collect_keywords(graph: Graph, subject: URIRef) -> frozenset[str]:
    keywords: set[str] = set()
    for value in graph.objects(subject, SCHEMA.keywords):
        text = _node_to_str(value)
        if not text:
            continue
        parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
        keywords.update(parts)
    return frozenset(keywords)


def _collect_topics(graph: Graph, subject: URIRef) -> frozenset[str]:
    topics: set[str] = set()
    for value in graph.objects(subject, SCHEMA.about):
        string_value = _node_to_str(value)
        if string_value:
            topics.add(string_value)
    for value in graph.objects(subject, DCT.subject):
        string_value = _node_to_str(value)
        if string_value:
            topics.add(string_value)
    return frozenset(topics)


def _collect_identifiers(graph: Graph, subject: URIRef) -> frozenset[str]:
    identifiers: set[str] = set()
    for value in graph.objects(subject, SCHEMA.identifier):
        string_value = _node_to_str(value)
        if string_value:
            identifiers.add(string_value)
    return frozenset(identifiers)


def _collect_literal_strings(graph: Graph, subject: URIRef, predicate: URIRef) -> frozenset[str]:
    values: set[str] = set()
    for literal in graph.objects(subject, predicate):
        string_value = literal_to_str(literal) if isinstance(literal, Literal) else _node_to_str(literal)
        if string_value:
            values.add(string_value)
    return frozenset(values)


def _collect_node_strs(graph: Graph, subject: URIRef, predicate: URIRef) -> tuple[str, ...]:
    values: list[str] = []
    for node in graph.objects(subject, predicate):
        string_value = _node_to_str(node)
        if string_value:
            values.append(string_value)
    return tuple(values)


def _collect_organizations(graph: Graph, subject: Node, predicate: URIRef) -> tuple[Organization, ...]:
    organizations: list[Organization] = []
    for node in graph.objects(subject, predicate):
        organization = _parse_organization(graph, node)
        if organization is not None:
            organizations.append(organization)
    return tuple(organizations)


def _extract_primary_organization(graph: Graph, subject: URIRef, predicate: URIRef) -> Organization | None:
    for node in graph.objects(subject, predicate):
        organization = _parse_organization(graph, node)
        if organization is not None:
            return organization
    return None


def _parse_organization(graph: Graph, node: Node) -> Organization | None:
    name_literal = _first_literal(graph, node, SCHEMA.name) or _first_literal(graph, node, SCHEMA.legalName)
    name = literal_to_str(name_literal)
    url = _first_value_as_str(graph, node, SCHEMA.url)

    if not name and isinstance(node, URIRef):
        name = str(node)
        if url is None:
            url = str(node)

    if not name:
        return None

    return Organization(name=name, url=url)


def _first_literal(graph: Graph, subject: Node, predicate: URIRef) -> Literal | None:
    for obj in graph.objects(subject, predicate):
        if isinstance(obj, Literal):
            return obj
    return None


def _first_node(graph: Graph, subject: Node, predicate: URIRef) -> Node | None:
    for obj in graph.objects(subject, predicate):
        return obj
    return None


def _first_value_as_str(graph: Graph, subject: Node, predicate: URIRef) -> str | None:
    for obj in graph.objects(subject, predicate):
        return _node_to_str(obj)
    return None


def _node_to_str(node: Node) -> str | None:
    if isinstance(node, Literal):
        return literal_to_str(node)
    if isinstance(node, (URIRef, BNode)):
        return str(node)
    return None
