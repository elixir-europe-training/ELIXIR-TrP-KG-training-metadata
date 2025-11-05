from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Iterable, Optional

from rdflib.term import Literal


@dataclass(frozen=True)
class Organization:
    name: str
    url: str | None = None


@dataclass(frozen=True)
class CourseInstance:
    start_date: datetime | None = None
    start_raw: str | None = None
    end_date: datetime | None = None
    end_raw: str | None = None
    mode: str | None = None
    capacity: int | None = None
    country: str | None = None
    locality: str | None = None
    postal_code: str | None = None
    street_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    funders: tuple[Organization, ...] = field(default_factory=tuple)
    organizers: tuple[Organization, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrainingResource:
    uri: str
    source: str
    types: frozenset[str] = field(default_factory=frozenset)
    name: str | None = None
    description: str | None = None
    abstract: str | None = None
    headline: str | None = None
    url: str | None = None
    provider: Organization | None = None
    keywords: frozenset[str] = field(default_factory=frozenset)
    topics: frozenset[str] = field(default_factory=frozenset)
    identifiers: frozenset[str] = field(default_factory=frozenset)
    authors: tuple[str, ...] = field(default_factory=tuple)
    contributors: tuple[str, ...] = field(default_factory=tuple)
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    teaches: tuple[str, ...] = field(default_factory=tuple)
    learning_resource_types: frozenset[str] = field(default_factory=frozenset)
    educational_levels: frozenset[str] = field(default_factory=frozenset)
    language: str | None = None
    interactivity_type: str | None = None
    access_modes: frozenset[str] = field(default_factory=frozenset)
    access_mode_sufficient: frozenset[str] = field(default_factory=frozenset)
    accessibility_controls: frozenset[str] = field(default_factory=frozenset)
    accessibility_features: frozenset[str] = field(default_factory=frozenset)
    accessibility_summary: str | None = None
    audience_roles: frozenset[str] = field(default_factory=frozenset)
    license_url: str | None = None
    is_accessible_for_free: bool | None = None
    is_family_friendly: bool | None = None
    creative_work_status: str | None = None
    version: str | None = None
    date_published: datetime | None = None
    date_published_raw: str | None = None
    date_modified: datetime | None = None
    date_modified_raw: str | None = None
    course_instances: tuple[CourseInstance, ...] = field(default_factory=tuple)


def literal_to_str(value: Optional[Literal]) -> str | None:
    if value is None:
        return None
    try:
        python_value = value.toPython()
    except (AttributeError, TypeError, ValueError):
        return str(value)
    if python_value is None:
        return None
    if isinstance(python_value, (str, int, float)):
        return str(python_value)
    if isinstance(python_value, datetime):
        return python_value.isoformat()
    if isinstance(python_value, date):
        return python_value.isoformat()
    return str(value)


def literal_to_int(value: Optional[Literal]) -> int | None:
    if value is None:
        return None
    try:
        python_value = value.toPython()
    except (AttributeError, TypeError, ValueError):
        python_value = None
    if isinstance(python_value, int):
        return python_value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def literal_to_float(value: Optional[Literal]) -> float | None:
    if value is None:
        return None
    try:
        python_value = value.toPython()
    except (AttributeError, TypeError, ValueError):
        python_value = None
    if isinstance(python_value, float):
        return python_value
    if isinstance(python_value, int):
        return float(python_value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def literal_to_datetime(value: Optional[Literal]) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    raw = str(value)
    try:
        python_value = value.toPython()
    except (AttributeError, TypeError, ValueError):
        python_value = None
    if isinstance(python_value, datetime):
        if python_value.tzinfo is None:
            python_value = python_value.replace(tzinfo=timezone.utc)
        return python_value, raw
    if isinstance(python_value, date):
        combined = datetime.combine(python_value, time.min)
        return combined.replace(tzinfo=timezone.utc), raw
    parsed = _parse_datetime_string(raw)
    if parsed is not None:
        return parsed, raw
    return None, raw


def _parse_datetime_string(raw: str) -> datetime | None:
    formats = [
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if raw.endswith(" UTC"):
        try:
            parsed = datetime.strptime(raw.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def literals_to_strings(values: Iterable[Literal]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        string_value = literal_to_str(value)
        if string_value:
            result.append(string_value)
    return tuple(result)


def keywords_to_lower_set(values: Iterable[Literal]) -> frozenset[str]:
    strings: list[str] = []
    for value in values:
        string_value = literal_to_str(value)
        if string_value:
            strings.append(string_value.lower())
    return frozenset(strings)
