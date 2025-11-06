from __future__ import annotations

from pathlib import Path
from typing import Mapping, MutableMapping

from rdflib import Dataset, Graph, URIRef

from .utils import bind_common_namespaces


def load_source_graph(dataset: Dataset, source_key: str, file_path: Path) -> tuple[Graph, URIRef]:
    """
    Parse a single TTL file into a named graph within the dataset.

    The graph URI is derived from the source key to provide stable references.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"TTL file not found for source '{source_key}': {file_path}")

    graph_uri = URIRef(f"urn:graph:{source_key}")
    graph = dataset.graph(graph_uri)
    graph.parse(str(file_path), format="ttl")
    return graph, graph_uri


def load_dataset(
    source_paths: Mapping[str, Path]
) -> tuple[Dataset, MutableMapping[str, Graph], dict[str, str]]:
    """
    Load all source TTL files into an RDF dataset.

    Returns the populated dataset, a mutable mapping of ``source_key`` to
    graph objects, and a mapping to the graph URI strings (used in diagnostics).
    """
    dataset = Dataset()
    bind_common_namespaces(dataset)

    graphs: MutableMapping[str, Graph] = {}
    source_graphs: dict[str, str] = {}

    for source_key, file_path in source_paths.items():
        graph, graph_uri = load_source_graph(dataset, source_key, file_path)
        graphs[source_key] = graph
        source_graphs[source_key] = str(graph_uri)

    return dataset, graphs, source_graphs
