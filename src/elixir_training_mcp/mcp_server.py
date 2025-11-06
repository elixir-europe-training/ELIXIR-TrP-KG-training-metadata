import argparse
from datetime import date
from typing import Any, Optional
from importlib.resources import files
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from rdflib import Dataset

from elixir_training_mcp.models import TessTrainingMaterial
from elixir_training_mcp.services import get_training_data_service

# Create MCP server https://github.com/modelcontextprotocol/python-sdk
mcp = FastMCP(
    name="Elixir Training MCP",
    debug=False,
    dependencies=["mcp", "httpx", "pydantic"],
    instructions="Provide tools that helps users access data about training materials.",
    json_response=True,
)

# https://tess.elixir-europe.org/materials?q=python+data+science
# TeSS API docs: https://tess.elixir-europe.org/api/json_api#tag/materials
# Find training materials about data science with python
# https://glittr.org/
# https://github.com/sib-swiss/glittr

# get all events/materials URLs by crawling through: https://tess.elixir-europe.org/events.json_api?per_page=100
# more docs here: https://tess.elixir-europe.org/api/json_api
# https://tess.elixir-europe.org/events/career-guidance-for-phds-and-postdocs-328f5f9f-38a5-4c62-b4d9-823218893d8f.jsonld


# curl 'https://tess.elixir-europe.org/events/training-data-stewards-for-life-sciences.jsonld' > training-data-stewards-for-life-sciences.jsonld
# sparql --data training-data-stewards-for-life-sciences.jsonld 'SELECT * { ?s a ?o}'|less


@mcp.tool()
async def search_training_materials(
    search: str,
) -> list[TessTrainingMaterial]:
    """Search training materials relevant to the user question.

    Args:
        search: Natural language question

    Returns:
        List of training materials
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://tess.elixir-europe.org/materials?q={quote(search)}",
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def keyword_search(query: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Search locally harvested training resources by free-text keywords."""

    service = get_training_data_service()
    return service.search_by_keyword(query, limit=limit)


@mcp.tool()
async def provider_search(provider: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Return resources published by a specific provider name (case-insensitive)."""

    service = get_training_data_service()
    return service.search_by_provider(provider, limit=limit)


@mcp.tool()
async def location_search(
    country: str,
    city: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Find scheduled courses by country (and optional city) using harvested data."""

    service = get_training_data_service()
    return service.search_by_location(country=country, city=city, limit=limit)


@mcp.tool()
async def date_search(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Find courses whose start dates fall within an ISO date range."""

    service = get_training_data_service()
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    return service.search_by_date_range(start=start, end=end, limit=limit)


@mcp.tool()
async def topic_search(topic: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Search harvested resources by topic identifier or label."""

    service = get_training_data_service()
    return service.search_by_topic(topic, limit=limit)


@mcp.tool()
async def dataset_stats() -> dict[str, Any]:
    """Return high-level diagnostics about the loaded training datasets."""

    service = get_training_data_service()
    return dict(service.stats)



@mcp.tool()
async def get_sparql_docs() -> str:
    """Retrieve docs to help write SPARQL queries to retrieve training data."""
    with files("elixir_training_mcp").joinpath("QUERIES.md").open("rb") as f:
        content = f.read().decode("utf-8")
    return content


g = Dataset(default_union=True)
with files("elixir_training_mcp").joinpath("data/tess_harvest.ttl").open("rb") as f:
    g.parse(f, format="ttl")
with files("elixir_training_mcp").joinpath("data/gtn_harvest.ttl").open("rb") as f:
    g.parse(f, format="ttl")


@mcp.tool()
async def execute_sparql_query(sparql_query: str) -> str:
    """Formulate and execute a SPARQL query to answer complex questions.

    Usually called after calling `get_sparql_docs` to get query examples.

    Args:
        sparql_query: The SPARQL query string to execute.

    Returns:
        The SPARQL query results in string format."""
    results = g.query(sparql_query)

    # Format results as a string
    output_lines = []
    for row in results:
        if isinstance(row, bool):
            continue
        row_str = ", ".join(str(item) for item in row)
        output_lines.append(row_str)

    return "\n".join(output_lines)


def cli() -> None:
    """Run the MCP server with appropriate transport."""
    parser = argparse.ArgumentParser(
        description="A Model Context Protocol (MCP) server for BioData resources at the SIB."
    )
    parser.add_argument("--http", action="store_true", help="Use Streamable HTTP transport")
    parser.add_argument("--port", type=int, default=8888, help="Port to run the server on")
    # parser.add_argument("settings_filepath", type=str, nargs="?", default="sparql-mcp.json", help="Path to settings file")
    args = parser.parse_args()
    # settings = Settings.from_file(args.settings_filepath)
    if args.http:
        mcp.settings.port = args.port
        mcp.settings.log_level = "INFO"
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
