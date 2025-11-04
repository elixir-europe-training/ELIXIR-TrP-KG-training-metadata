from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_sources() -> dict[str, Path]:
    return {
        "tess": FIXTURES_DIR / "tess_sample.ttl",
        "gtn": FIXTURES_DIR / "gtn_sample.ttl",
    }


def _skip_if_loader_missing():
    module = pytest.importorskip(
        "elixir_training_mcp.data_store", reason="Loader module not implemented yet."
    )
    if not hasattr(module, "load_training_data"):
        pytest.skip("load_training_data() not implemented yet.")
    return module


def test_loader_parses_sample_resources(sample_sources: dict[str, Path]) -> None:
    module = _skip_if_loader_missing()
    store = module.load_training_data(sample_sources)

    assert store.resource_count >= 2
    assert store.per_source_counts["tess"] == 3
    assert store.per_source_counts["gtn"] == 1

    tess_resource = store.resources_by_uri[
        "https://tess.example.org/courses/python-fair-data"
    ]
    assert tess_resource.source == "tess"
    assert tess_resource.provider is not None
    assert tess_resource.provider.name == "Bioinformatics.ca"
    assert tess_resource.course_instances[0].country == "Canada"
    assert "http://edamontology.org/topic_3391" in tess_resource.topics
    assert tess_resource.prerequisites == ("Basic Python programming",)
    course_instance = tess_resource.course_instances[0]
    assert course_instance.mode == "online"
    assert course_instance.capacity == 40
    assert course_instance.funders[0].name == "ELIXIR"

    overlap_resource = store.resources_by_uri["https://tess.example.org/courses/winter-metagenomics"]
    overlap_instance = overlap_resource.course_instances[0]
    assert overlap_instance.start_date is not None
    assert overlap_instance.end_date is not None

    later_resource = store.resources_by_uri["https://tess.example.org/courses/spring-genomics"]
    later_instance = later_resource.course_instances[0]
    assert later_instance.start_date is not None

    gtn_resource = store.resources_by_uri[
        "https://training.galaxyproject.org/training-material/topics/fair/tutorials/metadata-basics"
    ]
    assert gtn_resource.source == "gtn"
    assert "tutorial" in gtn_resource.learning_resource_types
    assert "FAIR" in gtn_resource.keywords
    assert gtn_resource.abstract is not None
    assert gtn_resource.authors == ("https://orcid.org/0000-0001-2345-6789",)
    assert gtn_resource.contributors == ("https://training.galaxyproject.org/hall-of-fame/hexylena/",)
    assert gtn_resource.license_url == "https://spdx.org/licenses/CC-BY-4.0.html"
    assert gtn_resource.date_published is not None
    assert gtn_resource.date_published_raw == "2023-04-17 15:35:37 +0000"
    assert gtn_resource.interactivity_type == "mixed"
    assert gtn_resource.language == "English"


def test_loader_raises_on_missing_file(tmp_path: Path) -> None:
    module = _skip_if_loader_missing()
    missing_path = tmp_path / "missing.ttl"
    with pytest.raises(FileNotFoundError):
        module.load_training_data({"missing": missing_path})


def test_keyword_index_returns_expected_resources(sample_sources: dict[str, Path]) -> None:
    module = _skip_if_loader_missing()
    store = module.load_training_data(sample_sources)
    result_ids = store.keyword_index.lookup("FAIR metadata")
    assert (
        "https://tess.example.org/courses/python-fair-data" in result_ids
    ), "Expected FAIR course from TeSS in keyword index."
    assert (
        "https://training.galaxyproject.org/training-material/topics/fair/tutorials/metadata-basics"
        in result_ids
    ), "Expected FAIR tutorial from GTN in keyword index."
    limited = store.keyword_index.lookup("FAIR metadata", limit=1)
    assert len(limited) == 1


def test_provider_location_topic_and_date_indexes(sample_sources: dict[str, Path]) -> None:
    module = _skip_if_loader_missing()
    store = module.load_training_data(sample_sources)

    provider_expected = ["https://tess.example.org/courses/python-fair-data"]
    assert store.provider_index.lookup("Bioinformatics.ca") == provider_expected
    assert store.provider_index.lookup("bioinformatics.ca") == provider_expected
    assert store.provider_index.lookup("BIOINFORMATICS.CA") == provider_expected

    location_results = store.location_index.lookup("Canada", "Toronto")
    assert "https://tess.example.org/courses/python-fair-data" in location_results
    montreal_results = store.location_index.lookup("canada", "montreal")
    assert "https://tess.example.org/courses/winter-metagenomics" in montreal_results
    country_results = store.location_index.lookup("Canada")
    assert set(country_results) == {
        "https://tess.example.org/courses/python-fair-data",
        "https://tess.example.org/courses/winter-metagenomics",
        "https://tess.example.org/courses/spring-genomics",
    }

    topic_results = store.topic_index.lookup("topic_3391")
    assert topic_results == ["https://tess.example.org/courses/python-fair-data"]

    date_results = store.date_index.lookup(date(2025, 1, 1), date(2025, 1, 31))
    assert date_results == [
        "https://tess.example.org/courses/winter-metagenomics",
        "https://tess.example.org/courses/python-fair-data",
    ]
    overlap_results = store.date_index.lookup(date(2025, 1, 15), date(2025, 1, 16))
    assert overlap_results == ["https://tess.example.org/courses/winter-metagenomics"]
