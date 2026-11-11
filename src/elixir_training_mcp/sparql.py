"""Query the SPARQL endpoint, and load the SPARQL examples and the VoID schema it stores in named graphs."""

from collections import defaultdict
from typing import Any

import httpx
from typing_extensions import TypedDict

from elixir_training_mcp.config import settings

PREFIXES = {
    "schema": "https://schema.org/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dct": "http://purl.org/dc/terms/",
    "edam": "http://edamontology.org/",
}


class QueryExample(TypedDict):
    question: str
    query: str


class ClassSchema(TypedDict):
    label: str
    shex: str


async def query_sparql(query: str, endpoint_url: str | None = None, timeout: float = 30) -> dict[str, Any]:
    """Run a SPARQL query with POST, returns the SPARQL JSON results. Raises `httpx.HTTPError` on failure"""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.post(
            endpoint_url or settings.sparql_endpoint_url,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        return resp.json()


def bindings(res: dict[str, Any]) -> list[dict[str, str]]:
    """Rows of SPARQL JSON results as plain `{var: value}` dicts"""
    return [{k: v["value"] for k, v in b.items()} for b in res.get("results", {}).get("bindings", [])]


def compress(iri: str) -> str:
    """Prefixed name of an IRI, e.g. `schema:Course`, or `<iri>` when no prefix matches"""
    for prefix, ns in PREFIXES.items():
        if iri.startswith(ns) and "/" not in iri[len(ns) :]:
            return f"{prefix}:{iri[len(ns) :]}"
    return f"<{iri}>"


async def load_examples() -> list[QueryExample]:
    """SPARQL query examples of the examples graph, with the question they answer"""
    res = await query_sparql(f"""PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?question ?query WHERE {{
  GRAPH <{settings.examples_graph}> {{
    ?ex a sh:SPARQLExecutable ;
      rdfs:comment ?question ;
      sh:select|sh:ask|sh:construct|sh:describe ?query .
  }}
}}""")
    return [{"question": r["question"], "query": r["query"]} for r in bindings(res)]


async def load_classes_schema() -> list[ClassSchema]:
    """Schema of each class from the VoID description, as a ShEx shape listing its predicates and their ranges"""
    res = await query_sparql(f"""PREFIX void: <http://rdfs.org/ns/void#>
PREFIX void-ext: <http://ldf.fi/void-ext#>
SELECT DISTINCT ?cls ?prop ?range WHERE {{
  GRAPH <{settings.void_graph}> {{
    ?cp void:class ?cls ; void:propertyPartition ?pp .
    ?pp void:property ?prop .
    OPTIONAL {{
      {{ ?pp void:classPartition/void:class ?range }}
      UNION {{ ?pp void-ext:datatypePartition/void-ext:datatype ?range }}
    }}
  }}
}}""")
    # Class -> predicate -> ranges
    schema: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in bindings(res):
        ranges = schema[r["cls"]][r["prop"]]
        if "range" in r:
            ranges.add(compress(r["range"]))
    classes: list[ClassSchema] = []
    for cls, props in sorted(schema.items()):
        lines = [
            f"  {compress(p)} [ {' '.join(sorted(rs))} ]" if rs else f"  {compress(p)} IRI" for p, rs in props.items()
        ]
        shex = f"{compress(cls)} {{\n" + " ;\n".join(sorted(lines)) + "\n}"
        classes.append({"label": compress(cls), "shex": shex})
    return classes
