from __future__ import annotations

from datetime import datetime, timezone

from elixir_training_mcp.data_models import CourseInstance, Organization, TrainingResource
from elixir_training_mcp.indexes import (
    DateIndex,
    KeywordIndex,
    LocationIndex,
    ProviderIndex,
    TopicIndex,
)


def _sample_resources() -> dict[str, TrainingResource]:
    uri_a = "https://example.org/resources/a"
    uri_b = "https://example.org/resources/b"

    resource_a = TrainingResource(
        uri=uri_a,
        source="tess",
        name="Introduction to FAIR data",
        description="Learn about FAIR principles.",
        keywords=frozenset({"FAIR", "metadata"}),
        learning_resource_types=frozenset({"online course"}),
        educational_levels=frozenset({"beginner"}),
        prerequisites=("Basic Python",),
        teaches=("FAIR data management",),
        provider=Organization(name="Bioinformatics.ca"),
        course_instances=(
            CourseInstance(
                start_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
                end_date=datetime(2025, 1, 16, tzinfo=timezone.utc),
                country="Canada",
                locality="Toronto",
            ),
        ),
        topics=frozenset({"http://edamontology.org/topic_3391", "FAIR data"}),
    )

    resource_b = TrainingResource(
        uri=uri_b,
        source="gtn",
        name="Advanced Metagenomics Workshop",
        keywords=frozenset({"metagenomics"}),
        provider=Organization(name="Galaxy Training Network"),
        course_instances=(
            CourseInstance(
                start_date=datetime(2025, 2, 10, tzinfo=timezone.utc),
                end_date=datetime(2025, 2, 12, tzinfo=timezone.utc),
                country="France",
                locality="Paris",
            ),
        ),
        topics=frozenset({"http://edamontology.org/topic_1234"}),
    )

    return {uri_a: resource_a, uri_b: resource_b}


def test_keyword_index_collects_tokens() -> None:
    index = KeywordIndex.from_resources(_sample_resources())
    results = index.lookup("fair data")
    assert "https://example.org/resources/a" in results


def test_provider_index_normalizes_names() -> None:
    index = ProviderIndex.from_resources(_sample_resources())
    assert index.lookup("bioinformatics.ca") == ["https://example.org/resources/a"]
    assert index.lookup("BIOINFORMATICS.CA") == ["https://example.org/resources/a"]


def test_location_index_handles_city_and_country() -> None:
    index = LocationIndex.from_resources(_sample_resources())
    assert index.lookup("canada", "toronto") == ["https://example.org/resources/a"]
    assert "https://example.org/resources/b" in index.lookup("france")


def test_date_index_filters_by_range() -> None:
    index = DateIndex.from_resources(_sample_resources())
    results = index.lookup(datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 31, tzinfo=timezone.utc))
    assert results == ["https://example.org/resources/a"]


def test_topic_index_matches_short_names() -> None:
    index = TopicIndex.from_resources(_sample_resources())
    assert index.lookup("topic_3391") == ["https://example.org/resources/a"]
    assert "https://example.org/resources/a" in index.lookup("fair data")
