from __future__ import annotations

from typing import Iterable, Iterator

from rdflib import Dataset, Graph, Namespace
from rdflib.term import BNode, Literal, Node, URIRef

from ..data_models import literal_to_str

# Common schema namespaces appear in both HTTP and HTTPS forms in the harvest
# data. Keeping both avoids missing predicates due to protocol mismatches.
SCHEMA_HTTP = Namespace("http://schema.org/")
SCHEMA_HTTPS = Namespace("https://schema.org/")
SCHEMA_NAMESPACES: tuple[Namespace, ...] = (SCHEMA_HTTP, SCHEMA_HTTPS)
DCT = Namespace("http://purl.org/dc/terms/")


def bind_common_namespaces(dataset: Dataset) -> None:
    """Ensure the RDF dataset has schema.org namespaces registered for debugging."""
    dataset.namespace_manager.bind("schema", SCHEMA_HTTPS, override=False)
    dataset.namespace_manager.bind("schema_http", SCHEMA_HTTP, override=False)
    dataset.namespace_manager.bind("dct", DCT, override=False)


def schema_predicates(*local_names: str) -> tuple[URIRef, ...]:
    """Return schema.org predicates for every provided local name."""
    predicates: list[URIRef] = []
    for name in local_names:
        for namespace in SCHEMA_NAMESPACES:
            predicates.append(namespace[name])
    return tuple(predicates)


def schema_objects(graph: Graph, subject: Node, local_name: str) -> Iterator[Node]:
    """Yield objects for the given schema.org predicate."""
    for predicate in schema_predicates(local_name):
        yield from graph.objects(subject, predicate)


def first_literal(graph: Graph, subject: Node, *predicates: URIRef) -> Literal | None:
    """Return the first literal matching any of the supplied predicates."""
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            if isinstance(obj, Literal):
                return obj
    return None


def first_node(graph: Graph, subject: Node, *predicates: URIRef) -> Node | None:
    """Return the first RDF node matching any of the supplied predicates."""
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            return obj
    return None


def node_to_str(node: Node) -> str | None:
    """Convert an RDF node to a string representation when possible."""
    if isinstance(node, Literal):
        return literal_to_str(node)
    if isinstance(node, (URIRef, BNode)):
        return str(node)
    return None


def first_value_as_str(graph: Graph, subject: Node, *predicates: URIRef) -> str | None:
    """Return the first object for predicates converted to a string."""
    for predicate in predicates:
        for obj in graph.objects(subject, predicate):
            return node_to_str(obj)
    return None


def collect_literal_strings(graph: Graph, subject: URIRef, *predicates: URIRef) -> frozenset[str]:
    """Collect literal objects for predicates as a frozen set of strings."""
    values: set[str] = set()
    for predicate in predicates:
        for literal in graph.objects(subject, predicate):
            string_value = literal_to_str(literal) if isinstance(literal, Literal) else node_to_str(literal)
            if string_value:
                values.add(string_value)
    return frozenset(values)


def literal_to_bool(value: Literal | None) -> bool | None:
    """Parse a literal into a boolean, returning None when indeterminate."""
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
