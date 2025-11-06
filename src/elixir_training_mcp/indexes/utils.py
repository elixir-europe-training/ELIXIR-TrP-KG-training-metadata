from __future__ import annotations

from datetime import date, datetime, timezone
import re

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str | None) -> list[str]:
    """Normalize text to lowercase tokens."""
    if not text:
        return []
    lower_text = text.lower()
    return list(TOKEN_PATTERN.findall(lower_text))


def append_unique(bucket: list[str], value: str) -> None:
    """Append a value to a list only if it is not already present."""
    if value not in bucket:
        bucket.append(value)


def normalize_datetime_input(value: datetime | date | None) -> datetime | None:
    """Convert date or naive datetime inputs into UTC-aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    combined = datetime.combine(value, datetime.min.time()).replace(tzinfo=timezone.utc)
    return combined
