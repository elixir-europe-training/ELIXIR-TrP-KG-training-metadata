"""Harvest training data from TeSS repositories.

Downloads the full JSON-LD dumps of training materials and events from a
TeSS (Training e-Support System) repository, and converts them to Turtle.
"""

from pathlib import Path

import httpx
from rdflib import Graph, URIRef
from rdflib.term import Node

# TeSS is behind a Cloudflare challenge that only lets through requests accepting application/json,
# so JSON-LD requests must also list it, otherwise they get a 403 HTML challenge page
JSONLD_ACCEPT = "application/ld+json, application/json;q=0.9"
USER_AGENT = "elixir-trainer (+https://github.com/elixir-europe-training/ELIXIR-trainer)"

# TeSS JSON-LD uses `"@context": "http://schema.org"`, we normalize all schema.org IRIs to https
SCHEMA_HTTP = "http://schema.org/"
SCHEMA = "https://schema.org/"

OUTPUT_TTL = Path("data/tess_harvest.ttl")


def to_https_schema(g: Graph) -> None:
    """Rewrite in place every http://schema.org/ IRI (subject, predicate or object) to https://schema.org/."""

    def fix(term: Node) -> Node:
        if isinstance(term, URIRef) and term.startswith(SCHEMA_HTTP):
            return URIRef(SCHEMA + term[len(SCHEMA_HTTP):])
        return term

    for s, p, o in list(g):
        fixed = (fix(s), fix(p), fix(o))
        if fixed != (s, p, o):
            g.remove((s, p, o))
            g.add(fixed)


def enrich_sib_organization(g: Graph) -> None:
    """Enrich the graph by replacing SIB organizations with canonical ROR URI.

    Consolidates all SIB organization instances into a single canonical ROR URI
    using a SPARQL INSERT/DELETE query.

    Args:
        g: RDFlib Graph to enrich in place
    """
    query = """PREFIX schema: <https://schema.org/>
    DELETE { ?org ?p ?o . ?s1 ?p1 ?org }
    INSERT {
        <https://ror.org/002n09z45> ?p ?o ;
            schema:name "SIB Swiss Institute of Bioinformatics" .
        ?s1 ?p1 <https://ror.org/002n09z45>
    } WHERE {
        ?org a schema:Organization ;
            schema:name ?name .
        FILTER (contains(?name, 'SIB')) .
        ?org ?p ?o .
        FILTER(?o != schema:name) .
        ?s1 ?p1 ?org
    }"""
    g.update(query)



def coords_to_wikidata(lat: float, lon: float) -> str | None:
    params: dict[str, str | int | float] = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "extratags": 1,
        "zoom": 18, # get building level info
    }
    resp = httpx.get("https://nominatim.openstreetmap.org/reverse", params=params, headers={"User-Agent": "geo-wikidata-resolver"})
    resp.raise_for_status()
    data = resp.json()
    # # Prefer Wikidata if available
    # wikidata_id = data.get("extratags", {}).get("wikidata")
    # if wikidata_id:
    #     return f"https://www.wikidata.org/entity/{wikidata_id}"

    # Otherwise fallback to OpenStreetMap entity
    osm_type = data.get("osm_type")
    osm_id = data.get("osm_id")
    if osm_type and osm_id:
        osm_type_letter = {"node": "node", "way": "way", "relation": "relation"}.get(osm_type)
        return f"https://www.openstreetmap.org/{osm_type_letter}/{osm_id}"
    return None


def enrich_locations_osm(g: Graph) -> None:
    """Enrich the graph by replacing blank node locations with OSM IRIs.

    For each schema:Place blank node with coordinates, queries the OpenStreetMap
    Nominatim API to get the corresponding OSM IRI. If an IRI is found, replaces
    the blank node subject with the OSM IRI, otherwise leaves it as a blank node.

    Args:
        g: RDFlib Graph to enrich in place
    """
    # Query all blank node locations with coordinates
    query_string = """PREFIX schema: <https://schema.org/>
    SELECT ?location ?lat ?lon
    WHERE {
        ?location a schema:Place ;
            schema:latitude ?lat ;
            schema:longitude ?lon .
        FILTER(isBlank(?location))
    }"""

    results = g.query(query_string)

    updates = []  # Store (old_blank_node, new_iri, properties) tuples
    for row in results:
        if isinstance(row, bool):
            continue
        blank_node = row[0]  # location
        try:
            lat = float(str(row[1]))  # lat
            lon = float(str(row[2]))  # lon

            # Get OSM IRI from coordinates
            osm_iri = coords_to_wikidata(lat, lon)

            if osm_iri:
                # Collect all properties of this blank node
                properties = list(g.predicate_objects(blank_node))
                updates.append((blank_node, URIRef(osm_iri), properties))
                print(f"Found OSM IRI for ({lat}, {lon}): {osm_iri}")
            else:
                print(f"No OSM IRI found for ({lat}, {lon}), keeping blank node")

        except (ValueError, TypeError) as e:
            print(f"Error processing location {blank_node}: {e}")

    # Apply updates: remove blank node and add URIRef with same properties
    for blank_node, new_iri, properties in updates:
        # Remove all triples with the blank node as subject
        for pred, obj in properties:
            g.remove((blank_node, pred, obj))

        # Add the same properties with the new IRI as subject
        for pred, obj in properties:
            g.add((new_iri, pred, obj))

        # Update all triples where the blank node was used as object
        for s, p, o in list(g.triples((None, None, blank_node))):
            g.remove((s, p, o))
            g.add((s, p, new_iri))

        print(f"Updated location from blank node to {new_iri}")



def harvest_tess_data(repo_url: str, resource_types: list[str], output: Path = OUTPUT_TTL) -> Graph:
    """Harvest TeSS events and materials from their full JSON-LD dumps into a Turtle file.

    Each `{repo_url}/{resource_type}.jsonld` returns a JSON-LD array with all the resources
    of this type (expired events included), so no pagination or per-resource fetching is needed.

    Args:
        repo_url: Base URL of the TeSS repository (e.g. "https://tess.elixir-europe.org")
        resource_types: Types of resources to harvest, e.g. ["materials", "events"]
        output: Turtle file to write, by default data/tess_harvest.ttl (loaded by the Qlever triplestore)

    Returns:
        The harvested RDFLib Graph

    Raises:
        httpx.HTTPError: If downloading a dump fails
    """
    base_url = repo_url.rstrip("/")
    g = Graph()
    g.bind("schema", SCHEMA)

    with httpx.Client(follow_redirects=True, timeout=300, headers={"User-Agent": USER_AGENT}) as client:
        for resource_type in resource_types:
            dump_url = f"{base_url}/{resource_type}.jsonld"
            print(f"Downloading {dump_url}")
            response = client.get(dump_url, headers={"accept": JSONLD_ACCEPT})
            response.raise_for_status()
            print(f"Parsing {len(response.json())} {resource_type}")
            g.parse(data=response.text, format="json-ld")

    to_https_schema(g)
    # Enrich graph with canonical ROR URI for SIB
    enrich_sib_organization(g)

    output.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output, format="ttl")
    print(f"Harvested {len(g)} triples in {output}")
    return g


if __name__ == "__main__":
    harvest_tess_data("https://tess.elixir-europe.org", ["materials", "events"])
    # 4620 materials / 16782 events (2026-11)


# NOTE: in TeSS `schema:name "TheAlgorithms/Python" ;` matches the slug of the github repo URL
# provided by @id in glittr
