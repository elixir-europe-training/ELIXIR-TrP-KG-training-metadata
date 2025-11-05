from __future__ import annotations

from datetime import date
from pathlib import Path

from elixir_training_mcp import data_store
from elixir_training_mcp.tools import TrainingDataService


def make_service() -> TrainingDataService:
    store = data_store.load_training_data(
        {
            "tess": Path("tests/fixtures/tess_sample.ttl"),
            "gtn": Path("tests/fixtures/gtn_sample.ttl"),
        }
    )
    return TrainingDataService(store)


def test_keyword_query_returns_expected_resources():
    service = make_service()
    results = service.search_by_keyword("FAIR")
    uris = {item["uri"] for item in results}
    assert "https://tess.example.org/materials/python-fair-data" in uris
    assert "https://training.galaxyproject.org/training-material/topics/fair/tutorials/metadata-basics.html" in uris


def test_date_range_query_filters_instances():
    service = make_service()
    results = service.search_by_date_range(date(2025, 1, 1), date(2025, 1, 31))
    uris = [item["uri"] for item in results]
    assert uris[0] == "https://tess.example.org/courses/winter-metagenomics"


def test_stats_exposed():
    service = make_service()
    stats = service.stats
    assert stats["total_resources"] == 4
    assert stats["per_source"]["tess"] == 3


def test_provider_search_returns_expected_course():
    service = make_service()
    results = service.search_by_provider("Bioinformatics.ca")
    assert results[0]["uri"] == "https://tess.example.org/materials/python-fair-data"


def test_location_search_matches_city():
    service = make_service()
    results = service.search_by_location("Canada", "Toronto")
    uris = [item["uri"] for item in results]
    assert "https://tess.example.org/materials/python-fair-data" in uris


def test_topic_search_matches_edam_topic():
    service = make_service()
    results = service.search_by_topic("topic_3391")
    assert results[0]["uri"] == "https://tess.example.org/materials/python-fair-data"
