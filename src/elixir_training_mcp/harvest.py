"""Harvest training data from TeSS repositories.

This module provides functionality to harvest all training materials or events
from a TeSS (Training e-Support System) repository using the JSON:API format.

Features:
- Paginated iteration through TeSS data
- Parallel fetching of JSON-LD data (5 at a time)
- Support for both events and materials endpoints
"""

import asyncio
import json
from pathlib import Path
from typing import Any
from importlib.resources import files

import httpx
from rdflib import Graph


def enrich_sib_organization(g: Graph) -> None:
    """Enrich the graph by replacing SIB organizations with canonical ROR URI.

    Consolidates all SIB organization instances into a single canonical ROR URI
    using a SPARQL INSERT/DELETE query.

    Args:
        g: RDFlib Graph to enrich in place
    """
    query = """PREFIX schema: <http://schema.org/>
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


async def harvest_tess_data(
    repo_url: str,
    resource_types: list[str],
    per_page: int = 100,
    max_concurrent: int = 5,
) -> list[dict[str, Any]]:
    """Harvest all data from a TeSS repository.

    Fetches paginated data from a TeSS repository and retrieves the full JSON-LD
    representation for each resource. Processes items page by page, and fetches
    JSON-LD data 5 at a time in parallel.

    Args:
        repo_url: Base URL of the TeSS repository
            (e.g., "https://tess.elixir-europe.org")
        resource_type: Type of resource to harvest - "events" or "materials"
            (default: "events")
        per_page: Number of items per page (default: 100)
        max_concurrent: Maximum number of concurrent JSON-LD fetches
            (default: 5)

    Returns:
        List of all harvested resources with their full JSON-LD data

    Raises:
        httpx.HTTPError: If any HTTP request fails

    Example:
        >>> data = await harvest_tess_data(
        ...     "https://tess.elixir-europe.org",
        ...     resource_type="events"
        ... )
    """
    base_url = repo_url.rstrip("/")
    all_data: list[dict[str, Any]] = []
    g = Graph()
    g.bind("schema", "http://schema.org/")

    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        for resource_type in resource_types:
            page_number = 1
            while True:
                # Fetch a page of data
                page_url = f"{base_url}/{resource_type}.json_api?per_page={per_page}&page_number={page_number}"

                print(f"Fetching page {page_number}: {page_url}")
                response = await client.get(page_url, headers={"accept": "application/vnd.api+json"})
                response.raise_for_status()
                page_data = response.json()

                # Extract items from this page
                items = page_data.get("data", [])
                if not items:
                    break

                # Collect the self links for JSON-LD fetching
                jsonld_urls = []
                for item in items:
                    if "links" in item and "self" in item["links"]:
                        self_link = item["links"]["self"]
                        jsonld_url = f"{base_url}{self_link}.jsonld"
                        jsonld_urls.append(jsonld_url)

                # Fetch JSON-LD data in parallel (5 at a time)
                print(f"Fetching {len(jsonld_urls)} JSON-LD resources in parallel...")
                jsonld_data = await _fetch_jsonld_parallel(client, jsonld_urls, max_concurrent=max_concurrent)

                # Load each JSON-LD file into the graph
                for jsonld_item in jsonld_data:
                    if jsonld_item:
                        g.parse(data=json.dumps(jsonld_item), format="json-ld")

                all_data.extend(jsonld_data)

                # Check if there are more pages
                links = page_data.get("links", {})
                if "next" not in links:
                    break

                page_number += 1

    # g.parse("data/tess_harvest.ttl", format="ttl")
    # Enrich graph with canonical ROR URI for SIB
    enrich_sib_organization(g)

    # Create data folder if it doesn't exist
    Path("data").mkdir(exist_ok=True)
    g.serialize(str(files("elixir_training_mcp").joinpath("data/tess_harvest.ttl")), format="ttl")
    print(f"Harvested {len(all_data)} total resources")
    return all_data


async def _fetch_jsonld_parallel(
    client: httpx.AsyncClient,
    urls: list[str],
    max_concurrent: int = 5,
) -> list[dict[str, Any]]:
    """Fetch JSON-LD data from multiple URLs in parallel.

    Fetches JSON-LD data with a concurrency limit to avoid overwhelming the server.

    Args:
        client: httpx AsyncClient instance
        urls: List of JSON-LD URLs to fetch
        max_concurrent: Maximum number of concurrent requests

    Returns:
        List of parsed JSON-LD data

    Raises:
        httpx.HTTPError: If any request fails
    """
    results: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(url: str) -> dict[str, Any]:
        async with semaphore:
            # print(f"  Fetching: {url}")
            response = await client.get(url, headers={"accept": "application/ld+json"})
            response.raise_for_status()
            return response.json()

    # Create tasks for all URLs
    tasks = [fetch_one(url) for url in urls]

    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)

    return results


if __name__ == "__main__":
    asyncio.run(harvest_tess_data("https://tess.elixir-europe.org", ["events", "materials"]))
    # 237 events / 3335 materials


# NOTE: in TeSS `schema:name "TheAlgorithms/Python" ;` matches the slug of the github repo URL
# provided by @id in glittr
