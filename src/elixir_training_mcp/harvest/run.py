"""Run all the harvesters, validate their output, and promote the valid ones to the data directory loaded by Qlever.

Each source is harvested in `{data_dir}/staging/`, so a failing source keeps its previous Turtle file in `data_dir`,
and the other sources are still updated. Transient network errors are retried before giving up.
The failures are written to `{data_dir}/harvest-failures.json`, read by `scripts/report-failure.sh` to open GitHub issues.
"""

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from rdflib import Graph

from elixir_training_mcp.harvest.harvest_gtn import harvest_gtn
from elixir_training_mcp.harvest.harvest_scilifelab import harvest_scilifelab
from elixir_training_mcp.harvest.harvest_tess import harvest_tess_data

# Harvester of each source, called with the staging directory, and the Turtle file it produces
SOURCES: dict[str, tuple[Callable[[Path], Graph], str]] = {
    "tess": (
        lambda staging: harvest_tess_data(
            "https://tess.elixir-europe.org", ["materials", "events"], staging / "tess_harvest.ttl"
        ),
        "tess_harvest.ttl",
    ),
    "gtn": (
        lambda staging: asyncio.run(harvest_gtn(staging / "gtn_output.ttl", staging / "gtn_jsonld")),
        "gtn_output.ttl",
    ),
    "scilifelab": (
        lambda staging: asyncio.run(harvest_scilifelab(output=staging / "scilifelab_harvest.ttl")),
        "scilifelab_harvest.ttl",
    ),
}

# A source producing less than this ratio of the triples of its previous harvest is rejected
MIN_TRIPLES_RATIO = 0.5
RETRIES = 3
RETRY_DELAY_S = 120


class ValidationError(Exception):
    """The harvested graph does not look like a complete harvest of the source"""


def is_transient(e: Exception) -> bool:
    """Network errors, rate limits and server errors are worth retrying, not the other errors"""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code == 429 or e.response.status_code >= 500
    return isinstance(e, httpx.TransportError)


def harvest_with_retries(source: str, staging: Path) -> Graph:
    harvest, _ = SOURCES[source]
    for attempt in range(1, RETRIES + 1):
        try:
            return harvest(staging)
        except Exception as e:
            if attempt == RETRIES or not is_transient(e):
                raise
            print(f"⚠️ {source} attempt {attempt} failed with a transient error, retrying: {e!r}")
            time.sleep(RETRY_DELAY_S * attempt)
    raise AssertionError("unreachable")


def fingerprint(source: str, e: Exception) -> str:
    """Identify a failure by its source, exception type and innermost frame in our code, so the same failure
    recurring every week is reported in the same GitHub issue"""
    frames = [f for f in traceback.extract_tb(e.__traceback__) if "elixir_training_mcp" in f.filename]
    location = f"{Path(frames[-1].filename).name}:{frames[-1].name}" if frames else ""
    return hashlib.sha256(f"{source}|{type(e).__name__}|{location}".encode()).hexdigest()[:12]


def harvest_all(data_dir: Path, sources: list[str]) -> list[dict[str, Any]]:
    """Harvest each source in the staging directory, and move its Turtle file to `data_dir` if valid.
    Returns the failures."""
    staging = data_dir / "staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    # Triples count of the previous harvest of each file, to detect a source returning partial data
    stats_file = data_dir / "harvest-stats.json"
    stats: dict[str, int] = json.loads(stats_file.read_text()) if stats_file.exists() else {}
    failures: list[dict[str, Any]] = []

    for source in sources:
        filename = SOURCES[source][1]
        print(f"\n🌾 Harvesting {source}")
        try:
            g = harvest_with_retries(source, staging)
            previous = stats.get(filename, 0)
            if len(g) == 0:
                raise ValidationError(f"{source} harvest produced no triples")
            if len(g) < previous * MIN_TRIPLES_RATIO:
                raise ValidationError(
                    f"{source} harvest produced {len(g):,} triples, less than {MIN_TRIPLES_RATIO:.0%} "
                    f"of the {previous:,} triples of the previous harvest"
                )
            (staging / filename).replace(data_dir / filename)
            stats[filename] = len(g)
            print(f"✅ {source}: {len(g):,} triples in {data_dir / filename} (previously {previous:,})")
        except Exception as e:
            print(f"❌ {source} failed, keeping its previous data:")
            traceback.print_exc()
            failures.append(
                {
                    "source": source,
                    "fingerprint": fingerprint(source, e),
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": "".join(traceback.format_exception(e)),
                }
            )

    stats_file.write_text(json.dumps(stats, indent=2))
    return failures


def cli() -> None:
    parser = argparse.ArgumentParser(description="Harvest the training sources into the data directory of Qlever")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Directory of the Turtle files")
    parser.add_argument("--source", nargs="+", choices=list(SOURCES), default=list(SOURCES), help="Sources to harvest")
    args = parser.parse_args()

    failures_file = args.data_dir / "harvest-failures.json"
    failures_file.unlink(missing_ok=True)
    failures = harvest_all(args.data_dir, args.source)
    if failures:
        failures_file.write_text(json.dumps(failures, indent=2))
        print(f"\n❌ Failed sources: {', '.join(f['source'] for f in failures)}, details in {failures_file}")
        sys.exit(1)
    print("\n✅ All sources harvested")


if __name__ == "__main__":
    cli()
