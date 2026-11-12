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
from mcp.server.apps import Apps, ResourceCsp
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
them to the user in an interactive view, and returns a summary.
To show where instructors teach, or the instructors of a country, use `show_instructors_map`: it shows a map of the
instructors by country, filterable by topic, to the user.
To compare the number of courses of organizations, overall or in a year, and their onsite or online share, use
`show_courses_by_organization`: it shows a bar chart of the courses per organization split by course mode, filterable
by year, to the user."""

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


# Data sent to the widget in `structuredContent`, as read by `widgets/instructors-map.html`
class TaughtCourse(TypedDict):
    name: str
    url: str | None
    startDate: str | None
    mode: str | None
    locality: str | None
    country: str | None
    # EDAM topics, and the free text keywords not already in the topics
    topics: list[str]
    keywords: list[str]
    providers: list[str]


class Instructor(TypedDict):
    name: str
    orcid: str | None
    affiliations: list[str]
    # Indexes of the courses in `InstructorsMapData.courses`
    courses: list[int]


class InstructorsMapData(TypedDict):
    country: str | None
    topic: str | None
    instructors: list[Instructor]
    courses: list[TaughtCourse]
    query: str


# Course instances with their instructors, each encoded as `IRI~name~affiliation;affiliation` (the IRI is empty for
# blank nodes). Instructors are grouped in a subquery first, to get their affiliations once
INSTRUCTORS_QUERY = """PREFIX schema: <https://schema.org/>
SELECT ?course ?instance (SAMPLE(?n) AS ?name) (SAMPLE(?u) AS ?url) (SAMPLE(?start) AS ?startDate)
  (SAMPLE(?m) AS ?mode) (SAMPLE(?loc) AS ?locality) (SAMPLE(?ctry) AS ?country)
  (GROUP_CONCAT(DISTINCT ?instructor; separator="|") AS ?instructors)
  (GROUP_CONCAT(DISTINCT ?topic; separator="|") AS ?topics)
  (GROUP_CONCAT(DISTINCT ?kw; separator="|") AS ?keywords)
  (GROUP_CONCAT(DISTINCT ?providerName; separator="|") AS ?providers)
WHERE {
  {
    SELECT ?p (SAMPLE(?pn) AS ?pName) (GROUP_CONCAT(DISTINCT ?affName; separator=";") AS ?affs) WHERE {
      ?x schema:instructor ?p .
      ?p schema:name ?pn .
      OPTIONAL { ?p schema:memberOf/schema:name ?affName }
    } GROUP BY ?p
  }
  ?course schema:hasCourseInstance ?instance .
  ?instance schema:instructor ?p .
  BIND(CONCAT(IF(isIRI(?p), STR(?p), ""), "~", ?pName, "~", COALESCE(?affs, "")) AS ?instructor)
  OPTIONAL { ?course schema:name ?n }
  OPTIONAL { ?course schema:url ?u }
  OPTIONAL { ?course schema:about/schema:name ?topic }
  OPTIONAL { ?course schema:keywords ?kw }
  OPTIONAL { ?course schema:provider/schema:name ?providerName }
  OPTIONAL { ?instance schema:startDate ?start }
  OPTIONAL { ?instance schema:courseMode ?m }
  OPTIONAL {
    ?instance schema:location/schema:address ?address .
    OPTIONAL { ?address schema:addressLocality ?loc }
    OPTIONAL { ?address schema:addressCountry ?ctry }
  }
}
GROUP BY ?course ?instance"""


def unique_ci(values: Iterable[str]) -> list[str]:
    """Values without the case-insensitive duplicates, in their first order"""
    seen: dict[str, str] = {}
    for v in values:
        seen.setdefault(v.lower(), v)
    return list(seen.values())


def to_instructors_map(rows: list[dict[str, str]]) -> tuple[list[TaughtCourse], list[Instructor]]:
    """Courses and their instructors. Instructors are merged by name: many are blank nodes, and the same ORCID is
    sometimes given to different people"""
    courses: list[TaughtCourse] = []
    instructors: dict[str, Instructor] = {}
    for raw in rows:
        row = {k: html.unescape(v) for k, v in raw.items()}

        def split(key: str, row: dict[str, str] = row) -> list[str]:
            return [v.strip() for v in row.get(key, "").split("|") if v.strip()]

        index = len(courses)
        topics = unique_ci(split("topics"))
        lower_topics = {t.lower() for t in topics}
        courses.append(
            {
                "name": row.get("name") or row["course"],
                "url": row.get("url") or (row["course"] if row["course"].startswith("http") else None),
                "startDate": row["startDate"][:10] if row.get("startDate") else None,
                "mode": row.get("mode"),
                "locality": row.get("locality"),
                "country": row.get("country"),
                "topics": topics,
                "keywords": [k for k in unique_ci(split("keywords")) if k.lower() not in lower_topics],
                "providers": sorted(unique_ci(split("providers")), key=len)[:2],
            }
        )
        for value in split("instructors"):
            iri, name, affs = [*value.split("~", 2), "", ""][:3]
            name = " ".join(name.split())
            if not name:
                continue
            # Same person written with or without hyphens, e.g. "Carlevaro-Fita" and "Carlevaro Fita"
            key = re.sub(r"[\s-]+", " ", name.lower())
            person = instructors.setdefault(key, {"name": name, "orcid": None, "affiliations": [], "courses": []})
            if iri.startswith("https://orcid.org/") and not person["orcid"]:
                person["orcid"] = iri
            person["affiliations"] = unique_ci(person["affiliations"] + [a for a in affs.split(";") if a])
            if index not in person["courses"]:
                person["courses"].append(index)
    return courses, list(instructors.values())


def place(c: TaughtCourse) -> str:
    """Country of a course, or `Online` / `No location` without address, as grouped in the widget"""
    if c["country"] and c["country"] != "Virtual":
        return c["country"]
    return "Online" if c["country"] == "Virtual" or c["mode"] == "online" else "No location"


@apps.tool(resource_uri="ui://elixir-training/instructors-map.html", annotations=READ_ONLY)
async def show_instructors_map(country: str | None = None, topic: str | None = None) -> CallToolResult:
    """Show a map of the instructors of courses by country to the user, in an interactive view where they can pick a
    country, and sort and filter its instructors by number of courses, topic, mode, provider and date. Only a summary
    is returned to you, do not repeat the list in your answer.

    Args:
        country: Country to select first, in English (e.g. "Switzerland", "United Kingdom")
        topic: Topic to filter the courses first, matched case-insensitively on part of their topics, keywords and
            name (e.g. "single-cell", "proteomics", "python")
    """
    try:
        res = await query_sparql(INSTRUCTORS_QUERY)
    except httpx.HTTPError as e:
        raise ToolError(f"Could not query the SPARQL endpoint: {e!r}") from e
    courses, instructors = to_instructors_map(bindings(res))
    country = country.strip() if country else None
    topic = topic.strip() if topic else None
    data: InstructorsMapData = {
        "country": country,
        "topic": topic,
        "instructors": instructors,
        "courses": courses,
        "query": INSTRUCTORS_QUERY,
    }

    # Summary for the model, with the same initial filters as the widget
    def matches(c: TaughtCourse) -> bool:
        return not topic or topic.lower() in " ".join([c["name"], *c["topics"], *c["keywords"]]).lower()

    kept = {i for i, c in enumerate(courses) if matches(c)}
    by_country: dict[str, set[str]] = {}
    for p in instructors:
        for i in kept.intersection(p["courses"]):
            by_country.setdefault(place(courses[i]), set()).add(p["name"])
    lines = [
        f"Shown to the user: map of {len(instructors)} instructors of {len(courses)} courses"
        + (f", filtered on the topic {topic!r} ({len(kept)} courses)" if topic else ""),
        "Instructors per country: "
        + ", ".join(f"{c} ({len(n)})" for c, n in sorted(by_country.items(), key=lambda x: -len(x[1]))[:12]),
    ]
    if country:
        local = sorted(
            (
                (p, [i for i in p["courses"] if i in kept and place(courses[i]).lower() == country.lower()])
                for p in instructors
            ),
            key=lambda x: -len(x[1]),
        )
        local = [x for x in local if x[1]]
        lines.append(f"{len(local)} instructors in {country}, with the most courses:")
        lines += [f"- {p['name']} ({len(ix)} courses) {p['orcid'] or ''}".rstrip() for p, ix in local[:15]]
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))], structured_content=dict(data))


apps.add_html_resource(
    "ui://elixir-training/instructors-map.html",
    (WIDGETS / "instructors-map.html").read_text(),
    title="Instructors map",
    # d3 and the countries of Natural Earth (world-atlas) are loaded from jsDelivr
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"], connect_domains=["https://cdn.jsdelivr.net"]),
)


# Data sent to the widget in `structuredContent`, as read by `widgets/courses-by-organization.html`
NO_DATE = "No date"
NO_MODE = "unknown"
# Order of the course modes in the stacked bars, other modes come after
MODES = ["onsite", "online", "hybrid"]


class OrganizationCourses(TypedDict):
    # `None` for the courses without provider
    name: str | None
    url: str | None
    # Number of courses per start year (or `NO_DATE`) and course mode
    counts: dict[str, dict[str, int]]
    # Distinct courses per mode and in total over all years
    mode_totals: dict[str, int]
    total: int


class CoursesByOrganizationData(TypedDict):
    year: str | None
    organization: str | None
    years: list[str]
    modes: list[str]
    # Distinct courses per year, a course can have many providers
    year_totals: dict[str, int]
    organizations: list[OrganizationCourses]
    total: int
    query: str


# Courses with the year they start, their mode and their providers. The names of each provider are concatenated in a subquery, an
# organization IRI can have many names (e.g. the ROR ID of SIB)
COURSES_BY_ORGANIZATION_QUERY = """PREFIX schema: <https://schema.org/>
SELECT ?course ?year ?mode ?orgNames ?orgUrl WHERE {
  ?course a schema:Course .
  OPTIONAL {
    ?course schema:hasCourseInstance ?instance .
    OPTIONAL { ?instance schema:startDate ?start }
    OPTIONAL { ?instance schema:courseMode ?mode }
  }
  OPTIONAL {
    ?course schema:provider ?org .
    {
      SELECT ?org (GROUP_CONCAT(DISTINCT ?n; separator="|") AS ?orgNames) (SAMPLE(?u) AS ?orgUrl) WHERE {
        ?org schema:name ?n .
        OPTIONAL { ?org schema:url ?u }
      } GROUP BY ?org
    }
  }
  BIND(SUBSTR(STR(?start), 1, 4) AS ?year)
}"""


def to_courses_by_organization(rows: list[dict[str, str]]) -> list[OrganizationCourses]:
    """Courses per organization, year and mode, organizations identified by their name and URL. Providers with many
    names (only IRIs) take their shortest name"""
    # (name, url) -> year -> mode -> course IRIs
    courses: dict[tuple[str | None, str | None], dict[str, dict[str, set[str]]]] = {}
    for raw in rows:
        row = {k: html.unescape(v) for k, v in raw.items()}
        names = [" ".join(n.split()) for n in row.get("orgNames", "").split("|") if n.strip()]
        name = min(names, key=len) if names else None
        url = ((row.get("orgUrl") or "").strip() or None) if name else None
        year = row.get("year") or NO_DATE
        mode = row.get("mode") or NO_MODE
        courses.setdefault((name, url), {}).setdefault(year, {}).setdefault(mode, set()).add(row["course"])
    orgs: list[OrganizationCourses] = []
    for (name, url), by_year in courses.items():
        by_mode: dict[str, set[str]] = {}
        for modes in by_year.values():
            for mode, c in modes.items():
                by_mode.setdefault(mode, set()).update(c)
        orgs.append(
            {
                "name": name,
                "url": url,
                "counts": {y: {m: len(c) for m, c in modes.items()} for y, modes in sorted(by_year.items())},
                "mode_totals": {m: len(c) for m, c in by_mode.items()},
                "total": len(set().union(*by_mode.values())),
            }
        )
    return sorted(orgs, key=lambda o: -o["total"])


def org_label(o: OrganizationCourses) -> str:
    return f"{o['name']} ({o['url']})" if o["name"] and o["url"] else o["name"] or "No organization"


def mode_order(mode: str) -> tuple[int, str]:
    return (MODES.index(mode) if mode in MODES else len(MODES) + (mode == NO_MODE), mode)


@apps.tool(resource_uri="ui://elixir-training/courses-by-organization.html", annotations=READ_ONLY)
async def show_courses_by_organization(year: int | None = None, organization: str | None = None) -> CallToolResult:
    """Show a bar chart of the number of courses provided by each organization to the user, split by course mode
    (onsite, online, hybrid), with a dropdown to filter on the year they start. Organizations are identified by their name and URL, and courses
    without provider are shown as "No organization". Only a summary is returned to you, do not repeat it in full.

    Args:
        year: Year to select first in the dropdown (e.g. 2025), all years by default
        organization: Show only the organizations whose name or URL contains this text, case-insensitively
            (e.g. "ELIXIR", "SIB", "carpentry")
    """
    organization = organization.strip() if organization else None
    try:
        res = await query_sparql(COURSES_BY_ORGANIZATION_QUERY)
    except httpx.HTTPError as e:
        raise ToolError(f"Could not query the SPARQL endpoint: {e!r}") from e
    rows = bindings(res)
    orgs = to_courses_by_organization(rows)
    # Years in order, courses without start date last
    by_year: dict[str, set[str]] = {}
    for r in rows:
        by_year.setdefault(r.get("year") or NO_DATE, set()).add(r["course"])
    years = sorted(by_year, key=lambda y: (y == NO_DATE, y))
    modes = sorted({m for o in orgs for m in o["mode_totals"]}, key=mode_order)
    # Years are strings in the data, as the keys of the counts
    selected = str(year) if year else None
    data: CoursesByOrganizationData = {
        "year": selected,
        "organization": organization,
        "years": years,
        "modes": modes,
        "year_totals": {y: len(by_year[y]) for y in years},
        "organizations": orgs,
        "total": len({r["course"] for r in rows}),
        "query": COURSES_BY_ORGANIZATION_QUERY,
    }

    # Summary for the model, with the same initial filters as the widget
    def by_mode(o: OrganizationCourses) -> dict[str, int]:
        return o["counts"].get(selected, {}) if selected else o["mode_totals"]

    def count(o: OrganizationCourses) -> int:
        return sum(by_mode(o).values()) if selected else o["total"]

    def line(o: OrganizationCourses) -> str:
        split = ", ".join(f"{m} {n}" for m, n in sorted(by_mode(o).items(), key=lambda x: mode_order(x[0])))
        return f"- {org_label(o)}: {count(o)} ({split})"

    kept = [
        o for o in orgs if count(o) and (not organization or organization.lower() in f"{o['name']} {o['url']}".lower())
    ]
    no_org = next((o for o in orgs if o["name"] is None), None)
    dated = [y for y in years if y != NO_DATE]
    lines = [
        f"Shown to the user: bar chart of {data['total']} courses from {len(orgs) - bool(no_org)} organizations, "
        + (f"in {year}" if year else f"from {dated[0]} to {dated[-1]}" if dated else "")
        + ", split by course mode"
        + (f", filtered on organizations matching {organization!r} ({len(kept)})" if organization else ""),
        f"Courses without organization{f' in {year}' if year else ''}: {count(no_org) if no_org else 0}",
        "Organizations with the most courses:",
        *[line(o) for o in sorted(kept, key=lambda o: -count(o))[:15] if o["name"]],
    ]
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))], structured_content=dict(data))


apps.add_html_resource(
    "ui://elixir-training/courses-by-organization.html",
    (WIDGETS / "courses-by-organization.html").read_text(),
    title="Courses by organization",
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
