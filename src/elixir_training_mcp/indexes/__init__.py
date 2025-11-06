"""
Indexes for the offline training data store.

Each module constructs a read-only lookup structure over `TrainingResource`
objects. They are re-exported here so callers can do either
`from elixir_training_mcp import data_store` or
`from elixir_training_mcp.indexes import KeywordIndex`, as preferred.
"""

from .keyword import KeywordIndex
from .provider import ProviderIndex
from .location import LocationIndex
from .date import CourseSchedule, DateIndex
from .topic import TopicIndex

__all__ = [
    "CourseSchedule",
    "DateIndex",
    "KeywordIndex",
    "LocationIndex",
    "ProviderIndex",
    "TopicIndex",
]
