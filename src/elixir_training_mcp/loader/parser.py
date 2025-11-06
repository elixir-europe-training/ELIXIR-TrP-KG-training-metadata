from __future__ import annotations

from typing import Iterable

from rdflib import Graph
from rdflib.namespace import RDF
from rdflib.term import BNode, Literal, Node, URIRef

from ..data_models import (
    CourseInstance,
    Organization,
    TrainingResource,
    literal_to_datetime,
    literal_to_float,
    literal_to_int,
    literal_to_str,
    literals_to_strings,
)
from .dedupe import resolve_resource_identifier, select_richest
from .utils import (
    DCT,
    collect_literal_strings,
    first_literal,
    first_node,
    first_value_as_str,
    literal_to_bool,
    node_to_str,
    schema_objects,
    schema_predicates,
    SCHEMA_NAMESPACES,
)

# Resource types supported by the loader; mirrors the original implementation.
RESOURCE_TYPES = tuple(
    namespace[name]
    for namespace in SCHEMA_NAMESPACES
    for name in ("Course", "LearningResource", "Event")
)


def extract_resources_from_graph(graph: Graph, source_key: str) -> dict[str, TrainingResource]:
    """
    Parse a named graph into training resources keyed by their canonical URI.
    """
    resources: dict[str, TrainingResource] = {}
    seen_subjects: set[Node] = set()

    for rdf_type in RESOURCE_TYPES:
        for subject in graph.subjects(RDF.type, rdf_type):
            if subject in seen_subjects:
                continue
            seen_subjects.add(subject)

            resource_id = resolve_resource_identifier(graph, subject)
            if resource_id is None:
                continue

            resource = _build_training_resource(graph, subject, source_key, resource_id)
            select_richest(resources, resource)

    return resources


def _build_training_resource(graph: Graph, subject: Node, source_key: str, resource_uri: str) -> TrainingResource:
    types = frozenset(str(obj) for obj in graph.objects(subject, RDF.type))
    name = literal_to_str(first_literal(graph, subject, *schema_predicates("name")))
    description = literal_to_str(first_literal(graph, subject, *schema_predicates("description")))
    abstract = literal_to_str(first_literal(graph, subject, *schema_predicates("abstract")))
    headline = literal_to_str(first_literal(graph, subject, *schema_predicates("headline")))
    url = first_value_as_str(graph, subject, *schema_predicates("url"))
    provider = _extract_primary_organization(graph, subject, *schema_predicates("provider"))
    keywords = _collect_keywords(graph, subject)
    topics = _collect_topics(graph, subject)
    identifiers = _collect_identifiers(graph, subject)
    authors = _collect_person_identifiers(graph, subject, *schema_predicates("author"))
    contributors = _collect_person_identifiers(graph, subject, *schema_predicates("contributor"))
    prerequisites = literals_to_strings(schema_objects(graph, subject, "coursePrerequisites"))
    teaches = literals_to_strings(schema_objects(graph, subject, "teaches"))
    learning_resource_types = collect_literal_strings(graph, subject, *schema_predicates("learningResourceType"))
    educational_levels = collect_literal_strings(graph, subject, *schema_predicates("educationalLevel"))
    language = _extract_language_label(graph, subject)
    interactivity_type = literal_to_str(first_literal(graph, subject, *schema_predicates("interactivityType")))
    access_modes = collect_literal_strings(graph, subject, *schema_predicates("accessMode"))
    access_mode_sufficient = collect_literal_strings(graph, subject, *schema_predicates("accessModeSufficient"))
    accessibility_controls = collect_literal_strings(graph, subject, *schema_predicates("accessibilityControl"))
    accessibility_features = collect_literal_strings(graph, subject, *schema_predicates("accessibilityFeature"))
    accessibility_summary = literal_to_str(first_literal(graph, subject, *schema_predicates("accessibilitySummary")))
    audience_roles = _collect_audience_roles(graph, subject)
    license_url = first_value_as_str(graph, subject, *schema_predicates("license"))
    is_accessible_for_free = literal_to_bool(first_literal(graph, subject, *schema_predicates("isAccessibleForFree")))
    is_family_friendly = literal_to_bool(first_literal(graph, subject, *schema_predicates("isFamilyFriendly")))
    creative_work_status = literal_to_str(first_literal(graph, subject, *schema_predicates("creativeWorkStatus")))
    version = literal_to_str(first_literal(graph, subject, *schema_predicates("version")))

    published_dt, published_raw = literal_to_datetime(
        first_literal(graph, subject, *schema_predicates("datePublished"))
    )
    modified_dt, modified_raw = literal_to_datetime(
        first_literal(graph, subject, *schema_predicates("dateModified"))
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
    for instance_node in schema_objects(graph, subject, "hasCourseInstance"):
        instance = _parse_course_instance(graph, instance_node)
        if instance:
            instances.append(instance)
    return tuple(instances)


def _parse_course_instance(graph: Graph, node: Node) -> CourseInstance | None:
    start_dt, start_raw = literal_to_datetime(first_literal(graph, node, *schema_predicates("startDate")))
    end_dt, end_raw = literal_to_datetime(first_literal(graph, node, *schema_predicates("endDate")))
    mode = literal_to_str(first_literal(graph, node, *schema_predicates("courseMode")))
    capacity = literal_to_int(first_literal(graph, node, *schema_predicates("maximumAttendeeCapacity")))

    country = locality = postal_code = street_address = None
    latitude = longitude = None

    location_node = first_node(graph, node, *schema_predicates("location"))
    if location_node is not None:
        latitude = literal_to_float(first_literal(graph, location_node, *schema_predicates("latitude")))
        longitude = literal_to_float(first_literal(graph, location_node, *schema_predicates("longitude")))
        address_node = first_node(graph, location_node, *schema_predicates("address"))
        if address_node is not None:
            country = literal_to_str(first_literal(graph, address_node, *schema_predicates("addressCountry")))
            locality = literal_to_str(first_literal(graph, address_node, *schema_predicates("addressLocality")))
            postal_code = literal_to_str(first_literal(graph, address_node, *schema_predicates("postalCode")))
            street_address = literal_to_str(
                first_literal(graph, address_node, *schema_predicates("streetAddress"))
            )

    funders = _collect_organizations(graph, node, *schema_predicates("funder"))
    organizers = _collect_organizations(graph, node, *schema_predicates("organizer"))

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
    for value in schema_objects(graph, subject, "keywords"):
        text = node_to_str(value)
        if not text:
            continue
        parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
        keywords.update(parts)
    return frozenset(keywords)


def _collect_topics(graph: Graph, subject: URIRef) -> frozenset[str]:
    topics: set[str] = set()
    for value in schema_objects(graph, subject, "about"):
        for string_value in _topic_strings_from_node(graph, value):
            if string_value:
                topics.add(string_value)
    for value in graph.objects(subject, DCT.subject):
        string_value = node_to_str(value)
        if string_value:
            topics.add(string_value)
    return frozenset(topics)


def _collect_identifiers(graph: Graph, subject: URIRef) -> frozenset[str]:
    identifiers: set[str] = set()
    for value in schema_objects(graph, subject, "identifier"):
        string_value = node_to_str(value)
        if string_value:
            identifiers.add(string_value)
    return frozenset(identifiers)


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
            for value in schema_objects(graph, node, predicate):
                string_value = node_to_str(value)
                if string_value:
                    values.append(string_value)
        name = literal_to_str(first_literal(graph, node, *schema_predicates("name")))
        if name:
            values.append(name)
        return values or [str(node)]
    return []


def _extract_primary_organization(graph: Graph, subject: URIRef, *predicates: URIRef) -> Organization | None:
    for predicate in predicates:
        for node in graph.objects(subject, predicate):
            organization = _parse_organization(graph, node)
            if organization is not None:
                return organization
    return None


def _collect_organizations(graph: Graph, subject: Node, *predicates: URIRef) -> tuple[Organization, ...]:
    organizations: list[Organization] = []
    for predicate in predicates:
        for node in graph.objects(subject, predicate):
            organization = _parse_organization(graph, node)
            if organization is not None:
                organizations.append(organization)
    return tuple(organizations)


def _parse_organization(graph: Graph, node: Node) -> Organization | None:
    name_literal = first_literal(
        graph,
        node,
        *schema_predicates("name"),
        *schema_predicates("legalName"),
    )
    name = literal_to_str(name_literal)
    url = first_value_as_str(graph, node, *schema_predicates("url"))

    if not name and isinstance(node, URIRef):
        name = str(node)
        if url is None:
            url = str(node)

    if not name:
        return None

    return Organization(name=name, url=url)


def _extract_language_label(graph: Graph, subject: Node) -> str | None:
    language_node = first_node(graph, subject, *schema_predicates("inLanguage"))
    if language_node is None:
        return None
    if isinstance(language_node, Literal):
        return literal_to_str(language_node)
    if isinstance(language_node, URIRef):
        return str(language_node)
    if isinstance(language_node, BNode):
        alt = literal_to_str(first_literal(graph, language_node, *schema_predicates("alternateName")))
        if alt:
            return alt
        name = literal_to_str(first_literal(graph, language_node, *schema_predicates("name")))
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
        name = literal_to_str(first_literal(graph, node, *schema_predicates("name")))
        if name:
            values.append(name)
        for value in schema_objects(graph, node, "url"):
            string_value = node_to_str(value)
            if string_value:
                values.append(string_value)
        return values or [str(node)]
    return []


def _collect_audience_roles(graph: Graph, subject: Node) -> frozenset[str]:
    roles: set[str] = set()
    for audience_node in schema_objects(graph, subject, "audience"):
        if isinstance(audience_node, Literal):
            value = literal_to_str(audience_node)
            if value:
                roles.add(value)
            continue
        if isinstance(audience_node, URIRef):
            roles.add(str(audience_node))
            continue
        if isinstance(audience_node, BNode):
            for role_literal in schema_objects(graph, audience_node, "educationalRole"):
                value = node_to_str(role_literal)
                if value:
                    roles.add(value)
            name = literal_to_str(first_literal(graph, audience_node, *schema_predicates("name")))
            if name:
                roles.add(name)
    return frozenset(roles)
