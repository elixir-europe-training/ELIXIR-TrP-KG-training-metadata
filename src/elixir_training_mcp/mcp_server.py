"""MCP server with tools to write and run SPARQL queries over the ELIXIR training knowledge graph, and an MCP App
showing the upcoming trainings of an organization."""

import asyncio
import html
import json
import re
from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, NotRequired

import httpx
from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from typing_extensions import TypedDict

from elixir_training_mcp import __version__
from elixir_training_mcp.sparql import ClassSchema, QueryExample, bindings, query_sparql
from elixir_training_mcp.vectordb import DocType, search

MAX_RESULT_ROWS = 50
WIDGETS = Path(__file__).parent / "widgets"
# All tools only read data, hosts list them as read-only tools
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

INSTRUCTIONS = """Training events, courses and materials in the life sciences, harvested from ELIXIR TeSS and the Galaxy
Training Network (GTN), in a knowledge graph using the schema.org and Bioschemas vocabularies.

To answer a question: search relevant query examples with `get_sparql_examples`, check the classes and predicates with
`get_sparql_schema`, then run the query with `execute_sparql_query`.
To show the upcoming trainings of an organization (e.g. SIB, VIB, EMBL-EBI), use `show_upcoming_trainings`: it shows
them to the user in an interactive view, and returns a summary."""

SPARQL_GUIDELINES = """## SPARQL query guidelines
- Base the query on the examples and classes schemas, never use classes or predicates not found in them
- Use the `https://schema.org/` namespace for the schema prefix (not `http://`)
- Dates are plain strings like "2026-05-27 09:00:00 UTC": compare them as strings, e.g. `FILTER(STR(?startDate) >= "2026-11-10")`
- Names of organizations vary (e.g. "SIB", "SIB Swiss Institute of Bioinformatics"): match them case-insensitively with `CONTAINS(LCASE(?name), "sib")`
"""


class ExamplesResults(TypedDict):
    query_examples: list[QueryExample]


class SchemaResults(TypedDict):
    classes_schemas: list[ClassSchema]


class SparqlQueryResults(TypedDict):
    """SPARQL JSON results, truncated to the first rows"""

    head: dict[str, Any]
    results: dict[str, Any]
    total_results: NotRequired[int]
    truncated: NotRequired[bool]


# Data sent to the widget in `structuredContent`, as read by `widgets/upcoming-trainings.html`
class Training(TypedDict):
    id: str
    name: str
    url: str | None
    startDate: str
    endDate: str | None
    mode: str | None
    locality: str | None
    country: str | None
    description: str | None
    organizations: list[str]
    keywords: list[str]


class TrainingsData(TypedDict):
    organization: str
    fromDate: str
    total: int
    trainings: list[Training]
    query: str


async def search_docs(queries: list[str], doc_type: DocType) -> list[dict[str, Any]]:
    """Search the index in a thread (embedding the queries is CPU bound), errors returned to the client as tool errors"""
    try:
        return await asyncio.to_thread(search, queries, doc_type)
    except LookupError as e:
        raise ToolError(f"{e}, use `execute_sparql_query` directly") from e


# MCP Apps extension, its tools and resources are registered before creating the server, which reads them once
apps = Apps()


def sparql_string(value: str) -> str:
    """SPARQL string literal of a value, with quotes and backslashes escaped"""
    return '"' + re.sub(r'(["\\])', r"\\\1", value).replace("\n", " ") + '"'


def upcoming_trainings_query(organization: str, from_date: str, limit: int) -> str:
    """Course instances starting from a date, with a provider or organizer matching the organization name or IRI.
    The matching instances are selected first in a subquery, then their details are retrieved"""
    if re.fullmatch(r"https?://[^\s<>\"{}|\\^`]+", organization):
        org_match = f"VALUES ?org {{ <{organization}> }}"
    else:
        org_match = f"?org schema:name ?orgName .\n      FILTER(CONTAINS(LCASE(?orgName), LCASE({sparql_string(organization)})))"
    return f"""PREFIX schema: <https://schema.org/>
SELECT ?course (SAMPLE(?n) AS ?name) (SAMPLE(?u) AS ?url) (SAMPLE(?start) AS ?startDate) (SAMPLE(?end) AS ?endDate)
  (SAMPLE(?m) AS ?mode) (SAMPLE(?loc) AS ?locality) (SAMPLE(?ctry) AS ?country) (SAMPLE(?desc) AS ?description)
  (GROUP_CONCAT(DISTINCT ?providerName; separator="|") AS ?organizations)
  (GROUP_CONCAT(DISTINCT ?kw; separator="|") AS ?keywords)
WHERE {{
  {{
    SELECT DISTINCT ?course ?instance ?start WHERE {{
      {org_match}
      {{ ?course schema:provider ?org }} UNION {{ ?instance schema:organizer ?org }}
      ?course schema:hasCourseInstance ?instance .
      ?instance schema:startDate ?start .
      FILTER(STR(?start) >= {sparql_string(from_date)})
    }}
  }}
  ?course schema:name ?n .
  OPTIONAL {{ ?course schema:provider/schema:name ?providerName }}
  OPTIONAL {{ ?course schema:url ?u }}
  OPTIONAL {{ ?course schema:description ?desc }}
  OPTIONAL {{ ?course schema:keywords ?kw }}
  OPTIONAL {{ ?instance schema:endDate ?end }}
  OPTIONAL {{ ?instance schema:courseMode ?m }}
  OPTIONAL {{
    ?instance schema:location/schema:address ?address .
    OPTIONAL {{ ?address schema:addressLocality ?loc }}
    OPTIONAL {{ ?address schema:addressCountry ?ctry }}
  }}
}}
GROUP BY ?course ?instance
ORDER BY ?startDate
LIMIT {limit}"""


def to_training(row: dict[str, str]) -> Training:
    # Some harvested values contain HTML entities, e.g. `&amp;`
    row = {k: html.unescape(v) for k, v in row.items()}
    split = lambda key: [v for v in row.get(key, "").split("|") if v]  # noqa: E731
    # Short plain text description, without the markdown heading lines and line breaks
    desc = re.sub(r"\s+", " ", re.sub(r"^#+ .*$", "", row.get("description", ""), flags=re.MULTILINE)).strip()
    return {
        "id": row["course"],
        "name": row["name"],
        "url": row.get("url") or (row["course"] if row["course"].startswith("http") else None),
        "startDate": row["startDate"],
        "endDate": row.get("endDate"),
        "mode": row.get("mode"),
        "locality": row.get("locality"),
        "country": row.get("country"),
        "description": (desc[:300] + "...") if len(desc) > 300 else desc or None,
        # An organization IRI can have many names (e.g. the ROR ID of SIB), the 2 shortest are kept
        "organizations": sorted(split("organizations"), key=len)[:2],
        "keywords": split("keywords")[:6],
    }


def top_counts(values: Iterable[str], top: int = 8) -> str:
    return ", ".join(f"{k} ({n})" for k, n in Counter(values).most_common(top))


def training_line(t: Training) -> str:
    place = ", ".join(v for v in [t["mode"], t["locality"], t["country"]] if v)
    return f"- {t['startDate'][:10]} {t['name']} ({place}) {t['url'] or ''}"


@apps.tool(resource_uri="ui://elixir-training/upcoming-trainings.html", annotations=READ_ONLY)
async def show_upcoming_trainings(organization: str, from_date: str | None = None, limit: int = 300) -> CallToolResult:
    """Show the upcoming trainings (courses and events) of an organization to the user in an interactive view, with
    their dates, mode, location and topics. Only a summary is returned to you, do not repeat the list in your answer.

    Args:
        organization: Name of the organization providing or organizing the trainings, matched case-insensitively
            on part of the name (e.g. "SIB", "VIB", "EMBL-EBI", "Galaxy"), or its IRI (e.g. a ROR ID
            https://ror.org/002n09z45)
        from_date: Show trainings starting from this date (YYYY-MM-DD), today by default
        limit: Maximum number of trainings
    """
    from_date = from_date or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_date):
        raise ToolError(f"Invalid date {from_date!r}, use the YYYY-MM-DD format")
    query = upcoming_trainings_query(organization.strip(), from_date, limit)
    try:
        res = await query_sparql(query)
    except httpx.HTTPError as e:
        raise ToolError(f"Could not query the SPARQL endpoint: {e!r}") from e
    trainings = [to_training(r) for r in bindings(res)]
    data: TrainingsData = {
        "organization": organization,
        "fromDate": from_date,
        "total": len(trainings),
        "trainings": trainings,
        "query": query,
    }
    if not trainings:
        text = (
            f"No trainings found from {from_date} for organizations matching {organization!r}. "
            "Try a shorter or different name, e.g. an acronym."
        )
    else:
        text = "\n".join(
            [
                f"Shown to the user: {len(trainings)} trainings from {from_date} of organizations matching {organization!r}"
                + (" (limit reached)" if len(trainings) >= limit else ""),
                f"Providers: {top_counts(o for t in trainings for o in t['organizations'])}",
                f"Modes: {top_counts(t['mode'] or 'unknown' for t in trainings)}",
                f"Countries: {top_counts(t['country'] or 'unknown' for t in trainings)}",
                "First trainings:",
                *[training_line(t) for t in trainings[:15]],
            ]
        )
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=dict(data))


apps.add_html_resource(
    "ui://elixir-training/upcoming-trainings.html",
    (WIDGETS / "upcoming-trainings.html").read_text(),
    title="Upcoming trainings",
)


mcp = MCPServer(
    "elixir-training",
    title="ELIXIR training",
    description="Search training events and materials in the life sciences from ELIXIR TeSS and GTN with SPARQL",
    website_url="https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata",
    instructions=INSTRUCTIONS,
    version=__version__,
    extensions=[apps],
)


@mcp.tool(
    annotations=READ_ONLY,
    description=f"""Get SPARQL query examples relevant to a question about trainings.

Use the examples as a base to write a SPARQL query answering the question, and `get_sparql_schema` to check the
classes and predicates used in the query.

Args:
    question: The question to be answered with a SPARQL query
    steps: Split the question in standalone smaller parts if relevant (leave empty if the question is already 1 step)

Returns:
    Relevant SPARQL query examples, with the question they answer

{SPARQL_GUIDELINES}""",
)
async def get_sparql_examples(question: str, steps: list[str] | None = None) -> ExamplesResults:
    hits = await search_docs([question, *(steps or [])], "example")
    return {"query_examples": [{"question": h["label"], "query": h["answer"]} for h in hits]}


@mcp.tool(annotations=READ_ONLY)
async def get_sparql_schema(classes: list[str]) -> SchemaResults:
    """Get the schema of classes in the knowledge graph: their predicates and the types of their values.

    Args:
        classes: Concepts and potential classes to look for, e.g. "Course", "location", "trainer"

    Returns:
        Relevant classes schemas in the ShEx format
    """
    hits = await search_docs(classes, "class")
    return {"classes_schemas": [{"label": h["label"], "shex": h["answer"]} for h in hits]}


@mcp.tool(annotations=READ_ONLY)
async def execute_sparql_query(sparql_query: str) -> SparqlQueryResults:
    """Execute a SPARQL SELECT or ASK query on the training knowledge graph.

    If the query returns no results, make it less restrictive (e.g. case-insensitive `CONTAINS` instead of exact
    string match), or break it down in smaller parts and check them one by one.

    Args:
        sparql_query: A valid SPARQL SELECT or ASK query

    Returns:
        The results in the SPARQL JSON format (first 50 rows), with the total number of results
    """
    try:
        res = await query_sparql(sparql_query)
    except httpx.HTTPStatusError as e:
        # Qlever puts the parse or execution error in the response body
        body = e.response.text.strip()[:2000] or "(empty response body)"
        raise ToolError(f"The SPARQL endpoint returned HTTP {e.response.status_code}:\n{body}") from e
    except httpx.TimeoutException as e:
        raise ToolError("The SPARQL query timed out, make it more specific or add a LIMIT") from e
    except httpx.HTTPError as e:
        raise ToolError(f"Could not reach the SPARQL endpoint: {e!r}") from e
    except json.JSONDecodeError as e:
        raise ToolError("The SPARQL endpoint did not return SPARQL JSON results, use a SELECT or ASK query") from e
    if "boolean" in res:
        return {"head": res.get("head", {}), "results": {"boolean": res["boolean"]}}
    rows = res.get("results", {}).get("bindings", [])
    return {
        "head": res.get("head", {}),
        "results": {"bindings": rows[:MAX_RESULT_ROWS]},
        "total_results": len(rows),
        "truncated": len(rows) > MAX_RESULT_ROWS,
    }
