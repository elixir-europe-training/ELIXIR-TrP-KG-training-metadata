"""Harvest training events and catalogue courses from the SciLifeLab Training Portal (https://training.scilifelab.se).

The portal runs a fork of TeSS (https://github.com/SciLifeLab-TrainingHub-Platform/TeSS) without the `.jsonld`
endpoints, and with a catalogue of courses, linked to their scheduled events, that have no Bioschemas markup.
So we fetch the JSON records, and serialize them to Bioschemas JSON-LD with the properties of the upstream TeSS
generators (https://github.com/ElixirTeSS/TeSS/tree/master/lib/bioschemas):
- events become a schema:Course with a schema:CourseInstance, like the TeSS "workshops and courses" events
- catalogue courses become a schema:Course without instance, that their events point to with schema:isPartOf
SciLifeLab specific fields are mapped following the Dublin Core / TeSS / Bioschemas alignment.
"""

import asyncio
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from rdflib import Graph

from elixir_training_mcp.harvest.harvest_tess import JSONLD_ACCEPT, SCHEMA, USER_AGENT, to_https_schema

BASE_URL = "https://training.scilifelab.se"
OUTPUT_TTL = Path("data/scilifelab_harvest.ttl")

COURSE_PROFILE = "https://bioschemas.org/profiles/Course/1.0-RELEASE"
COURSE_INSTANCE_PROFILE = "https://bioschemas.org/profiles/CourseInstance/1.0-RELEASE"
EDAM = "http://edamontology.org"

# Placeholders used in SciLifeLab records, dropped like blank values
PLACEHOLDERS = {"n/a", "none"}
# Pseudo node and content provider of the resources not provided by SciLifeLab
SKIPPED_ORGANIZATIONS = {"external", "not listed"}
# Legacy TeSS cost basis values stored as price audience type, they do not describe a type of customer
COST_BASIS = {"free", "charge"}
ORCID_PATTERN = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def is_blank(value: Any) -> bool:
    """Like Ruby `blank?` used by the TeSS generators to skip properties, also treating placeholders as blank."""
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDERS | {""}
    return value is None or value == [] or value == {}


def compact(node: dict[str, Any]) -> dict[str, Any]:
    """Drop the blank properties of a JSON-LD node."""
    return {key: value for key, value in node.items() if not is_blank(value)}


def clean(values: list[Any] | None) -> list[Any]:
    """Drop the blank values of a list, and strip strings."""
    return [value.strip() if isinstance(value, str) else value for value in values or [] if not is_blank(value)]


def markdown_to_array(markdown: str | None) -> list[str]:
    """Port of TeSS `markdown_to_array`: split a markdown list starting with ' * ' in its items."""
    if markdown is None or is_blank(markdown):
        return []
    if markdown.startswith(" * "):
        items = re.findall(r" \* (.+)(?:\n|\Z)", markdown)
        if items:
            return items
    return [markdown]


def tess_datetime(value: str | None) -> str | None:
    """Format an ISO 8601 date time like TeSS JSON-LD (Ruby `Time#to_s` in UTC), e.g. "2024-02-12 09:00:00 UTC"."""
    if value is None or is_blank(value):
        return None
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def tess_date(value: str | None) -> str | None:
    """Format an ISO 8601 date time as a date, like the TeSS material dates, e.g. "2024-02-12"."""
    if value is None or is_blank(value):
        return None
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d")


def organization(name: str | None, url: str | None = None) -> dict[str, Any] | None:
    """A schema:Organization, or None for blank names and the SciLifeLab pseudo organizations."""
    if name is None or is_blank(name) or name.strip().lower() in SKIPPED_ORGANIZATIONS:
        return None
    return compact({"@type": "Organization", "name": name.strip(), "url": url})


def provider(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Port of TeSS `provider`: the content providers, nodes and host institutions, unique by name."""
    candidates = [organization(cp.get("title"), cp.get("url")) for cp in record.get("content_providers") or []]
    candidates += [organization(node.get("name")) for node in record.get("nodes") or []]
    candidates += [organization(name) for name in record.get("host_institutions") or []]
    organizations: dict[str, dict[str, Any]] = {}
    for org in candidates:
        if org is not None:
            organizations.setdefault(org["name"].lower(), org)
    return list(organizations.values())


def person(record: dict[str, Any]) -> dict[str, Any]:
    """Port of TeSS `person` (ORCID as @id and identifier), with the affiliation as schema:memberOf like GTN."""
    node: dict[str, Any] = {"@type": "Person", "name": record["name"].strip()}
    orcid = ORCID_PATTERN.search(record.get("orcid") or "")
    if orcid:
        node["@id"] = node["identifier"] = f"https://orcid.org/{orcid.group(0)}"
    node["memberOf"] = organization(record.get("affiliation"))
    return compact(node)


def audience(values: list[str] | None) -> list[dict[str, Any]]:
    """Port of the TeSS target audiences: one schema:Audience per audience type."""
    return [{"@type": "Audience", "audienceType": value} for value in clean(values)]


def term(record: dict[str, Any]) -> dict[str, Any]:
    """Port of TeSS `term`: an EDAM scientific topic or operation as a schema:DefinedTerm."""
    return compact(
        {
            "@type": "DefinedTerm",
            "@id": record.get("uri"),
            "inDefinedTermSet": EDAM,
            "name": record.get("preferred_label"),
            "url": record.get("uri"),
        }
    )


def location(event: dict[str, Any]) -> dict[str, Any] | None:
    """Port of TeSS `address`: a schema:Place with a schema:PostalAddress, if the event has any address field."""
    address = compact(
        {
            "streetAddress": event.get("venue"),
            "addressLocality": event.get("city"),
            "addressRegion": event.get("county"),
            "addressCountry": event.get("country"),
            "postalCode": event.get("postcode"),
        }
    )
    if not address:
        return None
    return compact(
        {
            "@type": "Place",
            "address": {"@type": "PostalAddress", **address},
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
        }
    )


def license_url(licence: str | None) -> str | None:
    """Like the TeSS licence dictionary lookup: the SPDX reference URL of a licence id."""
    if licence is None or is_blank(licence) or licence == "notspecified" or licence.startswith("other-"):
        return None
    if licence.startswith(("http://", "https://")):
        return licence
    return f"https://spdx.org/licenses/{licence.strip()}.html"


def offers(event: dict[str, Any]) -> list[dict[str, Any]]:
    """The access cost: one schema:Offer per price, with the audience type as eligible customer type, like in the
    Bioschemas CourseInstance profile example."""
    result = []
    for price in event.get("event_prices") or []:
        cost = Decimal(str(price.get("cost") or 0))
        audience_type = (price.get("audience_type") or "").strip()
        # Some events are charged, but their price is only given in the description
        if audience_type.lower() == "charge" and cost == 0:
            continue
        offer: dict[str, Any] = {"@type": "Offer", "price": f"{cost:.2f}", "priceCurrency": price.get("currency")}
        if audience_type and audience_type.lower() not in COST_BASIS:
            offer["eligibleCustomerType"] = {"@type": "BusinessEntityType", "name": audience_type}
        result.append(compact(offer))
    return result


def course_iri(course: dict[str, Any]) -> str:
    return f"{BASE_URL}/courses/{course['slug']}"


def event_to_bioschemas(event: dict[str, Any], course_iris: dict[int, list[str]]) -> dict[str, Any]:
    """An event as a schema:Course with a schema:CourseInstance, port of the TeSS CourseGenerator and
    CourseInstanceGenerator, with the SciLifeLab fields of the alignment."""
    instance = {
        "@type": "CourseInstance",
        "dct:conformsTo": {"@type": "CreativeWork", "@id": COURSE_INSTANCE_PROFILE},
        "startDate": tess_datetime(event.get("start")),
        "endDate": tess_datetime(event.get("end")),
        "location": location(event),
        "funder": [org for org in (organization(sponsor) for sponsor in event.get("sponsors") or []) if org],
        "maximumAttendeeCapacity": event.get("capacity"),
        "courseMode": event.get("presence"),
        "duration": event.get("duration"),
        "contact": event.get("contact"),
        "offers": offers(event),
    }
    return compact(
        {
            "@id": f"{BASE_URL}/events/{event['slug']}",
            "@type": "Course",
            "dct:conformsTo": {"@type": "CreativeWork", "@id": COURSE_PROFILE},
            "name": event.get("title"),
            "alternateName": event.get("subtitle"),
            "url": event.get("url"),
            "description": event.get("description"),
            "keywords": clean(event.get("keywords")),
            "provider": provider(event),
            "inLanguage": event.get("language"),
            "audience": audience(event.get("target_audience")),
            "about": [term(topic) for topic in event.get("scientific_topics") or [] if topic.get("uri")],
            "hasCourseInstance": [compact(instance)],
            # Knowledge and technical prerequisites
            "coursePrerequisites": markdown_to_array(event.get("prerequisites"))
            + markdown_to_array(event.get("tech_requirements")),
            "teaches": markdown_to_array(event.get("learning_objectives")),
            "mentions": [
                compact({"@type": "Thing", "name": resource.get("title"), "url": resource.get("url")})
                for resource in event.get("external_resources") or []
            ],
            "isPartOf": [{"@id": iri} for iri in course_iris.get(event["id"], [])],
        }
    )


def course_to_bioschemas(course: dict[str, Any]) -> dict[str, Any]:
    """A catalogue course as a schema:Course without instance (its events point to it with schema:isPartOf), with
    the properties of the TeSS LearningResourceGenerator, as the alignment maps the courses to materials."""
    authors = [author for author in course.get("authors") or [] if not is_blank(author.get("name"))]
    contributors = [c for c in course.get("contributors") or [] if not is_blank(c.get("name"))]
    return compact(
        {
            "@id": course_iri(course),
            "@type": "Course",
            "dct:conformsTo": {"@type": "CreativeWork", "@id": COURSE_PROFILE},
            "name": course.get("title"),
            "url": course.get("url"),
            "description": course.get("description"),
            "keywords": clean(course.get("keywords")),
            "author": [person(author) for author in authors],
            "contributor": [person(contributor) for contributor in contributors],
            "provider": provider(course),
            "audience": audience(course.get("target_audience")),
            "dateCreated": tess_date(course.get("created_at")),
            "dateModified": tess_date(course.get("updated_at")),
            "license": license_url(course.get("licence")),
            # Knowledge and technical prerequisites
            "coursePrerequisites": markdown_to_array(course.get("prerequisites_knowledge"))
            + markdown_to_array(course.get("prerequisites_technical")),
            "teaches": markdown_to_array(course.get("learning_outcomes")),
            "inLanguage": course.get("language"),
            "timeRequired": course.get("structure_and_duration"),
            # Author contact details, formatted like the TeSS contacts: "name - email"
            "contact": [f"{a['name'].strip()} - {a['email'].strip()}" for a in authors if not is_blank(a.get("email"))],
        }
    )


async def fetch_json_parallel(
    client: httpx.AsyncClient, urls: list[str], max_concurrent: int = 5
) -> list[dict[str, Any]]:
    """Fetch the JSON of each URL, with at most `max_concurrent` requests at a time."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(url: str) -> dict[str, Any]:
        async with semaphore:
            response = await client.get(url, headers={"accept": JSONLD_ACCEPT})
            response.raise_for_status()
            return response.json()

    return await asyncio.gather(*(fetch_one(url) for url in urls))


async def fetch_records(
    client: httpx.AsyncClient,
    resource: str,
    per_page: int = 100,
    max_concurrent: int = 5,
    **params: str,
) -> list[dict[str, Any]]:
    """List all the records of a resource type with the JSON:API endpoint, then fetch the full JSON of each record.

    The attributes only given in the list (event presence, course creation and update dates) are kept.
    """
    listed: list[dict[str, Any]] = []
    page_number = 1
    while True:
        print(f"Fetching {resource} page {page_number}")
        response = await client.get(
            f"{BASE_URL}/{resource}.json_api",
            params={"per_page": per_page, "page_number": page_number, **params},
            headers={"accept": "application/vnd.api+json"},
        )
        response.raise_for_status()
        page = response.json()
        # Events follow JSON:API, courses are a plain list (or an empty JSON:API document after the last page)
        items = page if isinstance(page, list) else page.get("data", [])
        listed += [{k.replace("-", "_"): v for k, v in item.get("attributes", item).items()} for item in items]
        if len(items) < per_page:
            break
        page_number += 1

    print(f"Fetching {len(listed)} {resource} in parallel...")
    urls = [f"{BASE_URL}/{resource}/{item['slug']}.json" for item in listed]
    details = await fetch_json_parallel(client, urls, max_concurrent=max_concurrent)
    return [{**item, **detail} for item, detail in zip(listed, details, strict=True)]


async def harvest_scilifelab(max_concurrent: int = 5, output: Path = OUTPUT_TTL) -> Graph:
    """Harvest all the events and catalogue courses of the SciLifeLab Training Portal to Bioschemas RDF."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        events = await fetch_records(client, "events", max_concurrent=max_concurrent, include_expired="true")
        courses = await fetch_records(client, "courses", max_concurrent=max_concurrent)

    # Catalogue courses list their scheduled events, the events point to their course with schema:isPartOf
    course_iris: dict[int, list[str]] = defaultdict(list)
    for course in courses:
        for event in course.get("events") or []:
            course_iris[event["id"]].append(course_iri(course))

    nodes = [event_to_bioschemas(event, course_iris) for event in events]
    nodes += [course_to_bioschemas(course) for course in courses]

    # Same context as TeSS JSON-LD, so the properties are typed the same way, then normalized to https like TeSS
    g = Graph()
    g.parse(data=json.dumps({"@context": "http://schema.org", "@graph": nodes}), format="json-ld")
    to_https_schema(g)
    g.bind("schema", SCHEMA)
    g.bind("dct", "http://purl.org/dc/terms/")

    output.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output, format="ttl")
    linked = sum(1 for event in events if event["id"] in course_iris)
    print(f"Harvested {len(events)} events ({linked} linked to a catalogue course) and {len(courses)} courses")
    print(f"Saved {len(g):,} triples to {output}")
    return g


if __name__ == "__main__":
    asyncio.run(harvest_scilifelab())
