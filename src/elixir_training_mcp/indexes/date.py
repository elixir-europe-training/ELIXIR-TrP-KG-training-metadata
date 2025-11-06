from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Mapping

from ..data_models import TrainingResource
from .utils import normalize_datetime_input


@dataclass(frozen=True)
class CourseSchedule:
    resource_uri: str
    start: datetime
    end: datetime | None = None


@dataclass(frozen=True)
class DateIndex:
    _schedules: tuple[CourseSchedule, ...]

    @classmethod
    def from_resources(cls, resources: Mapping[str, TrainingResource]) -> "DateIndex":
        schedules: list[CourseSchedule] = []
        for uri, resource in resources.items():
            for instance in resource.course_instances:
                if instance.start_date is None:
                    continue
                schedules.append(
                    CourseSchedule(
                        resource_uri=uri,
                        start=instance.start_date,
                        end=instance.end_date,
                    )
                )
        schedules.sort(key=lambda schedule: schedule.start)
        return cls(tuple(schedules))

    def lookup(
        self,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        limit: int | None = None,
    ) -> list[str]:
        start_dt = normalize_datetime_input(start)
        end_dt = normalize_datetime_input(end)

        results: list[str] = []
        for schedule in self._schedules:
            if start_dt:
                if schedule.end:
                    if schedule.end < start_dt:
                        continue
                elif schedule.start < start_dt:
                    continue
            if end_dt and schedule.start > end_dt:
                continue
            if schedule.resource_uri not in results:
                results.append(schedule.resource_uri)
                if limit is not None and len(results) >= limit:
                    break
        return results
