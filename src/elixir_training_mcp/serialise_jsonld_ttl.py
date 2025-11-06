"""Serialize JSON-LD to Turtle with offline context control.

This module provides functionality to convert JSON-LD files to Turtle (TTL) format
without any remote network fetches, ensuring reproducibility and offline operation.

Features:
- Offline-safe: never fetches remote @context URLs
- Rich metadata preservation: keeps nested structures (Person profiles, etc.)
- Bioschemas compliance: maintains dcterms:conformsTo and other vocabularies
- Controlled expansion: replaces all contexts with local definitions

Example:
    >>> from pathlib import Path
    >>> files = sorted(Path("data/gtn_jsonld").rglob("*.jsonld"))
    >>> # Process and serialize (see main() function for full workflow)
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pyld import jsonld
from rdflib import Graph

JSONLD_DIR = Path("data/gtn_jsonld")
OUTPUT_TTL = Path("data/gtn_output.ttl")

# ---- Local contexts ----
LOCAL_CONTEXT = {
    "@vocab": "https://schema.org/",
    "schema": "https://schema.org/",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "bioschemas": "https://bioschemas.org/"
}

# Map known remote context URLs to local, inline JSON objects.
CONTEXT_MAP = {
    "http://schema.org": {"@context": "https://schema.org/"},
    "https://schema.org": {"@context": "https://schema.org/"},
    "http://schema.org/": {"@context": "https://schema.org/"},
    "https://schema.org/": {"@context": "https://schema.org/"},
    "http://purl.org/dc/terms/": {"@context": {"dcterms": "http://purl.org/dc/terms/"}},
    "http://purl.org/dc/terms": {"@context": {"dcterms": "http://purl.org/dc/terms/"}},
    "https://bioschemas.org": {"@context": {"bioschemas": "https://bioschemas.org/"}},
    "https://bioschemas.org/": {"@context": {"bioschemas": "https://bioschemas.org/"}}
}

# ---- Offline document loader with correct signature ----
def offline_loader(url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Custom document loader for pyld that blocks remote context fetches.

    This loader intercepts pyld's context resolution and returns local definitions
    for known vocabulary URLs, preventing any network requests during JSON-LD processing.

    Args:
        url: Context URL that pyld is trying to fetch
        options: Optional pyld loader options (unused)

    Returns:
        Document loader response dict with local context definition

    Raises:
        RuntimeError: If URL is not in the local CONTEXT_MAP (blocks unknown contexts)
    """
    # Normalize URL (strip trailing '#')
    key = url.rstrip("#")
    if key in CONTEXT_MAP:
        return {
            "contextUrl": None,
            "documentUrl": url,
            "document": CONTEXT_MAP[key]
        }
    # Block any other remote fetch
    raise RuntimeError(f"Blocked remote fetch: {url}")

# Install the loader globally
jsonld.set_document_loader(offline_loader)

def promote_id_to_atid(obj: Any) -> Any:
    """Recursively promote 'id' to '@id' and remove nested @context."""
    if isinstance(obj, dict):
        if "id" in obj and "@id" not in obj:
            obj["@id"] = obj.pop("id")
        # Remove nested @context to prevent remote lookups later
        if "@context" in obj:
            obj.pop("@context", None)
        for k, v in list(obj.items()):
            obj[k] = promote_id_to_atid(v)
        return obj
    if isinstance(obj, list):
        return [promote_id_to_atid(x) for x in obj]
    return obj


def ensure_top_level_id(doc: dict[str, Any]) -> dict[str, Any]:
    """Ensure document has an @id, fallback to url/identifier or blank node."""
    if isinstance(doc, dict) and "@id" not in doc:
        doc["@id"] = doc.get("url") or doc.get("identifier") or "_:resource"
    return doc


def load_jsonld_file(path: Path) -> list[dict[str, Any]]:
    """Load and prepare JSON-LD nodes from a file for offline processing.

    Reads a JSON-LD file, promotes plain 'id' to '@id', removes nested @context
    to prevent remote fetches, and flattens @graph structures.

    Args:
        path: Path to .jsonld file to load

    Returns:
        List of cleaned JSON-LD node dictionaries ready for expansion

    Raises:
        json.JSONDecodeError: If file contains invalid JSON
        OSError: If file cannot be read
    """
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else [data]

    nodes: list[dict[str, Any]] = []
    for item in items:
        # Flatten @graph if present
        if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
            for x in item["@graph"]:
                x = promote_id_to_atid(deepcopy(x))
                x = ensure_top_level_id(x)
                nodes.append(x)
        else:
            item = promote_id_to_atid(deepcopy(item))
            item = ensure_top_level_id(item)
            nodes.append(item)
    return nodes


def nodes_to_nquads(nodes: list[dict[str, Any]]) -> str:
    """Convert JSON-LD nodes to N-Quads format using offline context expansion.

    Wraps nodes in a controlled @context envelope using LOCAL_CONTEXT, expands
    with pyld (using offline_loader), and converts to N-Quads serialization.

    Args:
        nodes: List of JSON-LD node dictionaries (already cleaned by load_jsonld_file)

    Returns:
        N-Quads serialization as a string

    Raises:
        RuntimeError: If pyld tries to fetch an unknown context URL
        ValueError: If JSON-LD expansion fails
    """
    doc = {"@context": LOCAL_CONTEXT, "@graph": nodes}
    expanded = jsonld.expand(doc)  # uses only our local context + offline loader
    nquads = jsonld.to_rdf(expanded, options={"format": "application/n-quads"})
    return nquads


def main() -> None:
    """Main entry point: load all JSON-LD files and serialize to Turtle.

    Processes all .jsonld files in JSONLD_DIR, converts them to RDF triples using
    offline context expansion, and serializes the combined graph to OUTPUT_TTL.

    The function:
    1. Discovers all .jsonld files recursively
    2. Loads and cleans each file (promotes id to @id, strips nested contexts)
    3. Converts to N-Quads via pyld with offline loader
    4. Merges into single rdflib Graph
    5. Serializes to Turtle format with bound prefixes

    Raises:
        json.JSONDecodeError: If any file contains invalid JSON (logged, continues)
        OSError: If output directory cannot be created
        RuntimeError: If unknown context URLs are encountered
    """
    files = sorted(JSONLD_DIR.rglob("*.jsonld"))
    print(f"📂 Found {len(files)} JSON-LD files under {JSONLD_DIR}")

    g = Graph()
    g.bind("schema", "https://schema.org/")
    g.bind("dcterms", "http://purl.org/dc/terms/")
    g.bind("prov", "http://www.w3.org/ns/prov#")
    g.bind("bioschemas", "https://bioschemas.org/")

    ok = err = 0
    for i, fp in enumerate(files, 1):
        try:
            nodes = load_jsonld_file(fp)
            if not nodes:
                ok += 1
            else:
                nquads = nodes_to_nquads(nodes)
                g.parse(data=nquads, format="nquads")
                ok += 1
        except (json.JSONDecodeError, OSError, RuntimeError, ValueError) as e:
            err += 1
            print(f" {fp.name}: {e}")

        if i % 100 == 0 or i == len(files):
            print(f"  Processed {i}/{len(files)} | triples: {len(g):,} | files OK:{ok} ERR:{err}")

    OUTPUT_TTL.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(OUTPUT_TTL, format="turtle")
    print(f"\n Saved {len(g):,} triples to {OUTPUT_TTL}")


if __name__ == "__main__":
    main()
