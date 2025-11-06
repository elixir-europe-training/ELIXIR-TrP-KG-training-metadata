from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef

from elixir_training_mcp.data_models import TrainingResource
from elixir_training_mcp.loader import extract_resources_from_graph
from elixir_training_mcp.loader.dedupe import resolve_resource_identifier, select_richest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def tess_graph() -> Graph:
    graph = Graph()
    graph.parse(str(FIXTURES_DIR / "tess_sample.ttl"), format="ttl")
    return graph


def test_extract_resources_from_graph_parses_expected_resource(tess_graph: Graph) -> None:
    resources = extract_resources_from_graph(tess_graph, "tess")
    uri = "https://tess.example.org/materials/python-fair-data"
    assert uri in resources
    resource = resources[uri]
    assert resource.provider is not None and resource.provider.name == "Bioinformatics.ca"
    assert resource.keywords
    assert any(instance.country == "Canada" for instance in resource.course_instances)


def test_select_richest_prefers_resource_with_more_metadata() -> None:
    uri = "https://example.org/resource"
    basic = TrainingResource(uri=uri, source="tess")
    richer = TrainingResource(uri=uri, source="tess", name="Example resource", description="Details")

    resources: dict[str, TrainingResource] = {}
    select_richest(resources, basic)
    select_richest(resources, richer)
    assert resources[uri] is richer


def test_resolve_resource_identifier_prefers_schema_url() -> None:
    schema = Namespace("https://schema.org/")
    subject = URIRef("https://example.org/node")

    graph = Graph()
    graph.add((subject, schema.url, URIRef("https://canonical.example.org/resource")))

    identifier = resolve_resource_identifier(graph, subject)
    assert identifier == "https://canonical.example.org/resource"
