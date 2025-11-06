import argparse
from datetime import datetime
from importlib.resources import files
from typing import Any

from fastembed import TextEmbedding
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import DatetimeRange, Distance, FieldCondition, Filter, MatchValue, PointStruct, Range, VectorParams
from rdflib import Dataset


class TrainingMaterial(BaseModel):
    """Model for training material from search query results."""

    course: str
    name: str
    description: str | None = None
    provider: str | None = None
    keywords: str | None = None
    teaches: str | None = None
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    country: str | None = None
    locality: str | None = None
    capacity: int | None = None
    mode: str | None = None

    class Config:
        populate_by_name = True


# Create MCP server https://github.com/modelcontextprotocol/python-sdk
mcp = FastMCP(
    name="Elixir Training MCP",
    debug=False,
    dependencies=["mcp", "httpx", "pydantic", "qdrant_client", "fastembed"],
    instructions="Provide tools that helps users access data about training materials.",
    json_response=True,
)

# Initialize embedding model and Qdrant client
embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
qdrant_client = QdrantClient(path="data/qdrant")
# qdrant_client = QdrantClient(":memory:")
COLLECTION_NAME = "training_materials"

# Load and index training materials at startup
def initialize_search_index() -> None:
    """Load TTL files, extract materials via SPARQL, and index them in Qdrant."""
    # g = Dataset(default_union=True)

    # # Load both TTL files
    # with files("elixir_training_mcp").joinpath("data/tess_harvest.ttl").open("rb") as f:
    #     g.parse(f, format="ttl")

    # with files("elixir_training_mcp").joinpath("data/gtn_harvest.ttl").open("rb") as f:
    #     g.parse(f, format="ttl")

    # SPARQL query to get all training materials with relevant fields
    query = """PREFIX schema: <http://schema.org/>
    PREFIX dct: <http://purl.org/dc/terms/>
    SELECT DISTINCT ?course ?name ?description ?provider ?keywords ?teaches ?startDate ?endDate ?country ?locality ?capacity ?mode
    WHERE {
      ?course a schema:Course ;
        schema:name ?name .
      OPTIONAL { ?course schema:description ?description . }
      OPTIONAL {
        ?course schema:provider ?providerOrg .
        ?providerOrg schema:name ?provider .
      }
      OPTIONAL { ?course schema:keywords ?keywords . }
      OPTIONAL { ?course schema:teaches ?teaches . }
      OPTIONAL {
        ?course schema:hasCourseInstance ?instance .
        OPTIONAL { ?instance schema:startDate ?startDate . }
        OPTIONAL { ?instance schema:endDate ?endDate . }
        OPTIONAL { ?instance schema:courseMode ?mode . }
        OPTIONAL { ?instance schema:maximumAttendeeCapacity ?capacity . }
        OPTIONAL {
          ?instance schema:location ?location .
          ?location schema:address ?address .
          OPTIONAL { ?address schema:addressCountry ?country . }
          OPTIONAL { ?address schema:addressLocality ?locality . }
        }
      }
    }"""

    results = list(g.query(query))

    # Create collection with vector configuration
    vector_size = 384  # BAAI/bge-small-en-v1.5 dimension
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    # Prepare documents for indexing
    points = []
    for idx, row in enumerate(results):
        if isinstance(row, bool):
            continue

        # Convert SPARQL result row to dict - row is a ResultRow object with attributes
        row_dict: dict[str, Any] = {}
        for var_name in ["course", "name", "description", "provider", "keywords", "teaches",
                         "startDate", "endDate", "country", "locality", "capacity", "mode"]:
            value = getattr(row, var_name, None)
            if value is not None:
                # Convert capacity to int, everything else to string
                if var_name == "capacity":
                    try:
                        row_dict[var_name] = int(value)
                    except (ValueError, TypeError):
                        pass
                else:
                    row_dict[var_name] = str(value)

        try:
            material = TrainingMaterial.model_validate(row_dict)
        except Exception as e:
            print(f"Skipping row {idx} due to validation error: {e}")
            continue

        # Create searchable text combining name, description, keywords, and teaches
        search_text = f"{material.name}"
        if material.description:
            search_text += f" {material.description}"
        if material.keywords:
            search_text += f" {material.keywords}"
        if material.teaches:
            search_text += f" {material.teaches}"

        # Generate embedding
        embedding = next(iter(embedding_model.embed([search_text]))).tolist()

        # Prepare payload with all metadata
        payload: dict[str, Any] = {
            "course_id": material.course,
            "name": material.name,
            "description": material.description,
            "search_text": search_text,
        }
        # Add optional fields to payload
        if material.provider:
            payload["provider"] = material.provider
        if material.keywords:
            payload["keywords"] = material.keywords
        if material.teaches:
            payload["teaches"] = material.teaches
        if material.start_date:
            payload["start_date"] = material.start_date
        if material.end_date:
            payload["end_date"] = material.end_date
        if material.country:
            payload["country"] = material.country
        if material.locality:
            payload["locality"] = material.locality
        if material.capacity:
            payload["capacity"] = material.capacity
        if material.mode:
            payload["mode"] = material.mode

        points.append(
            PointStruct(
                id=idx,
                vector=embedding,
                payload=payload,
            )
        )

    # Index all points in Qdrant
    if points:
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)

    print(f"Indexed {len(points)} training materials in Qdrant")


# Initialize the search index at module load
initialize_search_index()

@mcp.tool()
async def search_training_materials(
    search_query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    # location: str | None = None,
    max_capacity: int | None = None,
) -> list[dict[str, Any]]:
    """Search training materials relevant to the user question.

    Args:
        search_query: Natural language question
        date_from: Optional start date filter (ISO format)
        date_to: Optional end date filter (ISO format)
        location: Optional location filter (country or city)
        max_capacity: Optional maximum capacity filter

    Returns:
        List of training materials
    """
    # Generate embedding for the search query
    query_embedding = next(iter(embedding_model.embed([search_query]))).tolist()

    # Build filters - only basic matching is supported to avoid type complexity
    filter_conditions: list[Any] = []
    location_filter: Filter | None = None

    # if location:
    #     # Try to match country or locality with OR logic
    #     location_filter = Filter(
    #         should=[
    #             FieldCondition(key="country", match=MatchValue(value=location)),
    #             FieldCondition(key="locality", match=MatchValue(value=location)),
    #         ]
    #     )

    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from)
            filter_conditions.append(
                FieldCondition(key="start_date", range=DatetimeRange(gte=date_from_dt))
            )
        except ValueError:
            pass  # Skip invalid date format

    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to)
            filter_conditions.append(
                FieldCondition(key="end_date", range=DatetimeRange(lte=date_to_dt))
            )
        except ValueError:
            pass  # Skip invalid date format

    if max_capacity is not None:
        filter_conditions.append(
            FieldCondition(key="capacity", range=Range(lte=max_capacity))
        )

    # Combine all filters with AND logic
    query_filter = None
    if filter_conditions or location_filter:
        must_conditions: list[Any] = filter_conditions.copy()
        if location_filter:
            must_conditions.append(location_filter)
        query_filter = Filter(must=must_conditions)

    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=20,
    )

    # Format results
    results = []
    for hit in search_results:
        if hit.payload:
            results.append({
                "course_id": hit.payload["course_id"],
                "name": hit.payload["name"],
                "description": hit.payload.get("description", ""),
                "provider": hit.payload.get("provider"),
                "keywords": hit.payload.get("keywords"),
                "teaches": hit.payload.get("teaches"),
                "start_date": hit.payload.get("start_date"),
                "end_date": hit.payload.get("end_date"),
                "country": hit.payload.get("country"),
                "locality": hit.payload.get("locality"),
                "capacity": hit.payload.get("capacity"),
                "mode": hit.payload.get("mode"),
                "relevance_score": hit.score,
            })

    return results



# @mcp.tool()
# async def local_dataset_stats() -> dict[str, Any]:
#     """Return high-level diagnostics about the loaded training datasets."""
#     collection_info = qdrant_client.get_collection(collection_name=COLLECTION_NAME)

#     vectors_config = collection_info.config.params.vectors
#     if isinstance(vectors_config, dict):
#         # Multi-vector config (not our case)
#         first_config = next(iter(vectors_config.values()))
#         vector_size = first_config.size
#         distance = first_config.distance.name
#     elif vectors_config is not None:
#         # Single vector config (our case)
#         vector_size = vectors_config.size
#         distance = vectors_config.distance.name
#     else:
#         vector_size = 0
#         distance = "UNKNOWN"

#     return {
#         "total_materials": collection_info.points_count,
#         "vector_size": vector_size,
#         "distance_metric": distance,
#     }



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
        description="A Model Context Protocol (MCP) server for accessing training resources at Elixir."
    )
    parser.add_argument("--http", action="store_true", help="Use Streamable HTTP transport")
    parser.add_argument("--port", type=int, default=8888, help="Port to run the server on")
    args = parser.parse_args()
    if args.http:
        mcp.settings.port = args.port
        mcp.settings.log_level = "INFO"
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
