from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType

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

SCHEMA_HTTP = Namespace("http://schema.org/")
SCHEMA_HTTPS = Namespace("https://schema.org/")
SCHEMA_NAMESPACES: tuple[Namespace, ...] = (SCHEMA_HTTP, SCHEMA_HTTPS)
DCT = Namespace("http://purl.org/dc/terms/")

RESOURCE_TYPES = tuple(
    namespace[name]
    for namespace in SCHEMA_NAMESPACES
    for name in ("Course", "LearningResource", "Event")
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
    stats: Mapping[str, Any]

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


def _extract_resources_from_graph(graph: Graph, source_key: str) -> dict[str, TrainingResource]:
    resources: dict[str, TrainingResource] = {}
    seen_subjects: set[Node] = set()

    for rdf_type in RESOURCE_TYPES:
        for subject in graph.subjects(RDF.type, rdf_type):
            if subject in seen_subjects:
                continue
            seen_subjects.add(subject)

            resource_id = _resolve_resource_identifier(graph, subject)
            if resource_id is None:
                continue

            resource = _build_training_resource(graph, subject, source_key, resource_id)
            existing = resources.get(resource.uri)
            if existing is None or _is_richer_resource(resource, existing):
                resources[resource.uri] = resource

    return resources


def _resolve_resource_identifier(graph: Graph, subject: Node) -> str | None:
    url = _first_value_as_str(graph, subject, *_schema_predicates("url"))
    if url:
        return url
    if isinstance(subject, URIRef):
        return str(subject)
    if isinstance(subject, BNode):
        return str(subject)
    return None


def _is_richer_resource(candidate: TrainingResource, current: TrainingResource) -> bool:
    return _resource_quality(candidate) > _resource_quality(current)


def _resource_quality(resource: TrainingResource) -> int:
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


def _build_training_resource(graph: Graph, subject: Node, source_key: str, resource_uri: str) -> TrainingResource:
    types = frozenset(str(obj) for obj in graph.objects(subject, RDF.type))
    name = literal_to_str(_first_literal(graph, subject, *_schema_predicates("name")))
    description = literal_to_str(_first_literal(graph, subject, *_schema_predicates("description")))
    abstract = literal_to_str(_first_literal(graph, subject, *_schema_predicates("abstract")))
    headline = literal_to_str(_first_literal(graph, subject, *_schema_predicates("headline")))
    url = _first_value_as_str(graph, subject, *_schema_predicates("url"))
    provider = _extract_primary_organization(graph, subject, *_schema_predicates("provider"))
    keywords = _collect_keywords(graph, subject)
    topics = _collect_topics(graph, subject)
    identifiers = _collect_identifiers(graph, subject)
    authors = _collect_person_identifiers(graph, subject, *_schema_predicates("author"))
    contributors = _collect_person_identifiers(graph, subject, *_schema_predicates("contributor"))
    prerequisites = literals_to_strings(_schema_objects(graph, subject, "coursePrerequisites"))
    teaches = literals_to_strings(_schema_objects(graph, subject, "teaches"))
    learning_resource_types = _collect_literal_strings(graph, subject, *_schema_predicates("learningResourceType"))
    educational_levels = _collect_literal_strings(graph, subject, *_schema_predicates("educationalLevel"))
    language = _extract_language_label(graph, subject)
    interactivity_type = literal_to_str(_first_literal(graph, subject, *_schema_predicates("interactivityType")))
    access_modes = _collect_literal_strings(graph, subject, *_schema_predicates("accessMode"))
    access_mode_sufficient = _collect_literal_strings(graph, subject, *_schema_predicates("accessModeSufficient"))
    accessibility_controls = _collect_literal_strings(graph, subject, *_schema_predicates("accessibilityControl"))
    accessibility_features = _collect_literal_strings(graph, subject, *_schema_predicates("accessibilityFeature"))
    accessibility_summary = literal_to_str(_first_literal(graph, subject, *_schema_predicates("accessibilitySummary")))
    audience_roles = _collect_audience_roles(graph, subject)
    license_url = _first_value_as_str(graph, subject, *_schema_predicates("license"))
    is_accessible_for_free = _literal_to_bool(_first_literal(graph, subject, *_schema_predicates("isAccessibleForFree")))
    is_family_friendly = _literal_to_bool(_first_literal(graph, subject, *_schema_predicates("isFamilyFriendly")))
    creative_work_status = literal_to_str(_first_literal(graph, subject, *_schema_predicates("creativeWorkStatus")))
    version = literal_to_str(_first_literal(graph, subject, *_schema_predicates("version")))

    published_dt, published_raw = literal_to_datetime(
        _first_literal(graph, subject, *_schema_predicates("datePublished"))
    )
    modified_dt, modified_raw = literal_to_datetime(
        _first_literal(graph, subject, *_schema_predicates("dateModified"))
    )

    course_instances = _collect_course_instances(graph, subject)

    return TrainingResource(
        uri=resource_uri,
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
        access_modes=access_modes,
        access_mode_sufficient=access_mode_sufficient,
        accessibility_controls=accessibility_controls,
        accessibility_features=accessibility_features,
        accessibility_summary=accessibility_summary,
        audience_roles=audience_roles,
        license_url=license_url,
        is_accessible_for_free=is_accessible_for_free,
        is_family_friendly=is_family_friendly,
        creative_work_status=creative_work_status,
        version=version,
        date_published=published_dt,
        date_published_raw=published_raw,
        date_modified=modified_dt,
        date_modified_raw=modified_raw,
        course_instances=course_instances,
    )


def _collect_course_instances(graph: Graph, subject: URIRef) -> tuple[CourseInstance, ...]:
    instances: list[CourseInstance] = []
    for instance_node in _schema_objects(graph, subject, "hasCourseInstance"):
        instance = _parse_course_instance(graph, instance_node)
        if instance:
            instances.append(instance)
    return tuple(instances)


def _parse_course_instance(graph: Graph, node: Node) -> CourseInstance | None:
    start_dt, start_raw = literal_to_datetime(_first_literal(graph, node, *_schema_predicates("startDate")))
    end_dt, end_raw = literal_to_datetime(_first_literal(graph, node, *_schema_predicates("endDate")))
    mode = literal_to_str(_first_literal(graph, node, *_schema_predicates("courseMode")))
    capacity = literal_to_int(_first_literal(graph, node, *_schema_predicates("maximumAttendeeCapacity")))

    country = locality = postal_code = street_address = None
    latitude = longitude = None

    location_node = _first_node(graph, node, *_schema_predicates("location"))
    if location_node is not None:
        latitude = literal_to_float(_first_literal(graph, location_node, *_schema_predicates("latitude")))
        longitude = literal_to_float(_first_literal(graph, location_node, *_schema_predicates("longitude")))
        address_node = _first_node(graph, location_node, *_schema_predicates("address"))
        if address_node is not None:
            country = literal_to_str(_first_literal(graph, address_node, *_schema_predicates("addressCountry")))
            locality = literal_to_str(_first_literal(graph, address_node, *_schema_predicates("addressLocality")))
            postal_code = literal_to_str(_first_literal(graph, address_node, *_schema_predicates("postalCode")))
            street_address = literal_to_str(_first_literal(graph, address_node, *_schema_predicates("streetAddress")))

    funders = _collect_organizations(graph, node, *_schema_predicates("funder"))
    organizers = _collect_organizations(graph, node, *_schema_predicates("organizer"))

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
    for value in _schema_objects(graph, subject, "keywords"):
        text = _node_to_str(value)
        if not text:
            continue
        parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
        keywords.update(parts)
    return frozenset(keywords)


def _collect_topics(graph: Graph, subject: URIRef) -> frozenset[str]:
    topics: set[str] = set()
    for value in _schema_objects(graph, subject, "about"):
        for string_value in _topic_strings_from_node(graph, value):
            if string_value:
                topics.add(string_value)
    for value in graph.objects(subject, DCT.subject):
        string_value = _node_to_str(value)
        if string_value:
            topics.add(string_value)
    return frozenset(topics)


def _collect_identifiers(graph: Graph, subject: URIRef) -> frozenset[str]:
    identifiers: set[str] = set()
    for value in _schema_objects(graph, subject, "identifier"):
        string_value = _node_to_str(value)
        if string_value:
            identifiers.add(string_value)
    return frozenset(identifiers)


def _collect_literal_strings(graph: Graph, subject: URIRef, *predicates: URIRef) -> frozenset[str]:
    values: set[str] = set()
    for predicate in predicates:
        for literal in graph.objects(subject, predicate):
            string_value = literal_to_str(literal) if isinstance(literal, Literal) else _node_to_str(literal)
            if string_value:
                values.add(string_value)
    return frozenset(values)


def _collect_organizations(graph: Graph, subject: Node, *predicates: URIRef) -> tuple[Organization, ...]:
    organizations: list[Organization] = []
    for predicate in predicates:
        for node in graph.objects(subject, predicate):
            organization = _parse_organization(graph, node)
            if organization is not None:
                organizations.append(organization)
    return tuple(organizations)


def _extract_primary_organization(graph: Graph, subject: URIRef, *predicates: URIRef) -> Organization | None:
    for predicate in predicates:
        for node in graph.objects(subject, predicate):
            organization = _parse_organization(graph, node)
            if organization is not None:
                return organization
    return None


def _parse_organization(graph: Graph, node: Node) -> Organization | None:
    name_literal = _first_literal(
        graph,
        node,
        *_schema_predicates("name"),
        *_schema_predicates("legalName"),
    )
    name = literal_to_str(name_literal)
    url = _first_value_as_str(graph, node, *_schema_predicates("url"))

    if not name and isinstance(node, URIRef):
        name = str(node)
        if url is None:
            url = str(node)

    if not name:
        return None

    return Organization(name=name, url=url)


def _first_literal(graph: Graph, subject: Node, *predicates: URIRef) -> Literal | None:
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            if isinstance(obj, Literal):
                return obj
    return None


def _first_node(graph: Graph, subject: Node, *predicates: URIRef) -> Node | None:
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            return obj
    return None


def _first_value_as_str(graph: Graph, subject: Node, *predicates: URIRef) -> str | None:
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            return _node_to_str(obj)
    return None


def _node_to_str(node: Node) -> str | None:
    if isinstance(node, Literal):
        return literal_to_str(node)
    if isinstance(node, (URIRef, BNode)):
        return str(node)
    return None


def _schema_predicates(*local_names: str) -> tuple[URIRef, ...]:
    predicates: list[URIRef] = []
    for name in local_names:
        for namespace in SCHEMA_NAMESPACES:
            predicates.append(namespace[name])
    return tuple(predicates)


def _schema_objects(graph: Graph, subject: Node, local_name: str) -> Iterable[Node]:
    for predicate in _schema_predicates(local_name):
        yield from graph.objects(subject, predicate)


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


def _collect_person_identifiers(graph: Graph, subject: Node, *predicates: URIRef) -> tuple[str, ...]:
    results: list[str] = []
    seen: set[str] = set()
    for predicate in predicates:
        for node in graph.objects(subject, predicate):
            for identifier in _extract_person_identifiers(graph, node):
                if identifier and identifier not in seen:
                    seen.add(identifier)
                    results.append(identifier)
    return tuple(results)


def _extract_person_identifiers(graph: Graph, node: Node) -> Iterable[str]:
    if isinstance(node, Literal):
        value = literal_to_str(node)
        return [value] if value else []
    if isinstance(node, URIRef):
        return [str(node)]
    if isinstance(node, BNode):
        values: list[str] = []
        for predicate in ("identifier", "mainEntityOfPage", "url"):
            for value in _schema_objects(graph, node, predicate):
                string_value = _node_to_str(value)
                if string_value:
                    values.append(string_value)
        name = literal_to_str(_first_literal(graph, node, *_schema_predicates("name")))
        if name:
            values.append(name)
        return values or [str(node)]
    return []


def _extract_language_label(graph: Graph, subject: Node) -> str | None:
    language_node = _first_node(graph, subject, *_schema_predicates("inLanguage"))
    if language_node is None:
        return None
    if isinstance(language_node, Literal):
        return literal_to_str(language_node)
    if isinstance(language_node, URIRef):
        return str(language_node)
    if isinstance(language_node, BNode):
        alt = literal_to_str(_first_literal(graph, language_node, *_schema_predicates("alternateName")))
        if alt:
            return alt
        name = literal_to_str(_first_literal(graph, language_node, *_schema_predicates("name")))
        if name:
            return name
        return str(language_node)
    return None


def _topic_strings_from_node(graph: Graph, node: Node) -> Iterable[str]:
    if isinstance(node, Literal):
        value = literal_to_str(node)
        return [value] if value else []
    if isinstance(node, URIRef):
        return [str(node)]
    if isinstance(node, BNode):
        values: list[str] = []
        name = literal_to_str(_first_literal(graph, node, *_schema_predicates("name")))
        if name:
            values.append(name)
        for value in _schema_objects(graph, node, "url"):
            string_value = _node_to_str(value)
            if string_value:
                values.append(string_value)
        return values or [str(node)]
    return []


def _collect_audience_roles(graph: Graph, subject: Node) -> frozenset[str]:
    roles: set[str] = set()
    for audience_node in _schema_objects(graph, subject, "audience"):
        if isinstance(audience_node, Literal):
            value = literal_to_str(audience_node)
            if value:
                roles.add(value)
            continue
        if isinstance(audience_node, URIRef):
            roles.add(str(audience_node))
            continue
        if isinstance(audience_node, BNode):
            for role_literal in _schema_objects(graph, audience_node, "educationalRole"):
                value = _node_to_str(role_literal)
                if value:
                    roles.add(value)
            name = literal_to_str(_first_literal(graph, audience_node, *_schema_predicates("name")))
            if name:
                roles.add(name)
    return frozenset(roles)


def _literal_to_bool(value: Literal | None) -> bool | None:
    if value is None:
        return None
    text = literal_to_str(value)
    if text is None:
        return None
    lowered = text.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None
