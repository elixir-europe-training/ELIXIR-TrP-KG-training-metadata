import argparse
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

from elixir_training_mcp.models import TessTrainingMaterial

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


# @mcp.tool()
# async def harvest_tess_repository(
#     repo_url: str,
#     resource_type: str = "events",
# ) -> list[dict[str, object]]:
#     """Harvest all data from a TeSS repository.

#     Fetches all training materials or events from a TeSS repository and retrieves
#     the full JSON-LD representation for each resource. Processes items page by page,
#     with parallel fetching of JSON-LD data (5 at a time).

#     Args:
#         repo_url: Base URL of the TeSS repository
#             (e.g., "https://tess.elixir-europe.org")
#         resource_type: Type of resource to harvest - "events" or "materials"
#             (default: "events")

#     Returns:
#         List of all harvested resources with their full JSON-LD data
#     """
#     return await harvest_tess_data(
#         repo_url=repo_url,
#         resource_type=resource_type,
#         per_page=100,
#         max_concurrent=5,
#     )


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
        mcp.run()
        mcp.settings.port = args.port
        mcp.settings.log_level = "INFO"
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
