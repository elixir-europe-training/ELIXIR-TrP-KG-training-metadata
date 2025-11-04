from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from rdflib import Dataset, Graph, Namespace
from rdflib.namespace import RDF
from rdflib.term import BNode, Literal, Node, URIRef
import re

from collections import defaultdict

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
    keyword_index, provider_index, location_index, date_index, topic_index = _build_indexes(resource_map)

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
