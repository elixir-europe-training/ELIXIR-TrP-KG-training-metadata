"""MCP tool implementations backed by the local training data store."""

from __future__ import annotations

from typing import Any, Mapping

from elixir_training_mcp import data_store


class TrainingDataService:
    """Thin wrapper exposing search helpers backed by the TrainingDataStore."""

    def __init__(self, store: data_store.TrainingDataStore) -> None:
        self._store = store

    @property
    def stats(self) -> Mapping[str, Any]:
        return self._store.stats

    def search_by_keyword(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        uris = self._store.keyword_index.lookup(query, limit=limit)
        return [self._resource_to_dict(uri) for uri in uris]

    def search_by_provider(self, provider: str, limit: int | None = None) -> list[dict[str, Any]]:
        uris = self._store.provider_index.lookup(provider, limit=limit)
        return [self._resource_to_dict(uri) for uri in uris]

    def search_by_location(self, country: str, city: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        uris = self._store.location_index.lookup(country=country, city=city, limit=limit)
        return [self._resource_to_dict(uri) for uri in uris]

    def search_by_date_range(
        self,
        start: data_store.datetime | data_store.date | None,
        end: data_store.datetime | data_store.date | None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        uris = self._store.date_index.lookup(start=start, end=end, limit=limit)
        return [self._resource_to_dict(uri) for uri in uris]

    def search_by_topic(self, topic: str, limit: int | None = None) -> list[dict[str, Any]]:
        uris = self._store.topic_index.lookup(topic, limit=limit)
        return [self._resource_to_dict(uri) for uri in uris]

    def _resource_to_dict(self, uri: str) -> dict[str, Any]:
        resource = self._store.resources_by_uri[uri]
        return {
            "uri": resource.uri,
            "source": resource.source,
            "name": resource.name,
            "description": resource.description,
            "abstract": resource.abstract,
            "headline": resource.headline,
            "url": resource.url,
            "provider": _organization_to_dict(resource.provider),
            "keywords": sorted(resource.keywords),
            "topics": sorted(resource.topics),
            "identifiers": sorted(resource.identifiers),
            "authors": list(resource.authors),
            "contributors": list(resource.contributors),
            "prerequisites": list(resource.prerequisites),
            "teaches": list(resource.teaches),
            "learning_resource_types": sorted(resource.learning_resource_types),
            "educational_levels": sorted(resource.educational_levels),
            "language": resource.language,
            "interactivity_type": resource.interactivity_type,
            "access_modes": sorted(resource.access_modes),
            "access_mode_sufficient": sorted(resource.access_mode_sufficient),
            "accessibility_controls": sorted(resource.accessibility_controls),
            "accessibility_features": sorted(resource.accessibility_features),
            "accessibility_summary": resource.accessibility_summary,
            "audience_roles": sorted(resource.audience_roles),
            "license_url": resource.license_url,
            "is_accessible_for_free": resource.is_accessible_for_free,
            "is_family_friendly": resource.is_family_friendly,
            "creative_work_status": resource.creative_work_status,
            "version": resource.version,
            "date_published": resource.date_published.isoformat() if resource.date_published else None,
            "date_published_raw": resource.date_published_raw,
            "date_modified": resource.date_modified.isoformat() if resource.date_modified else None,
            "date_modified_raw": resource.date_modified_raw,
            "course_instances": [
                {
                    "start_date": instance.start_date.isoformat() if instance.start_date else None,
                    "start_raw": instance.start_raw,
                    "end_date": instance.end_date.isoformat() if instance.end_date else None,
                    "end_raw": instance.end_raw,
                    "mode": instance.mode,
                    "capacity": instance.capacity,
                    "country": instance.country,
                    "locality": instance.locality,
                    "postal_code": instance.postal_code,
                    "street_address": instance.street_address,
                    "latitude": instance.latitude,
                    "longitude": instance.longitude,
                    "funders": [_organization_to_dict(org) for org in instance.funders],
                    "organizers": [_organization_to_dict(org) for org in instance.organizers],
                }
                for instance in resource.course_instances
            ],
        }


def _organization_to_dict(org: data_store.Organization | None) -> dict[str, Any] | None:
    if org is None:
        return None
    return {"name": org.name, "url": org.url}
