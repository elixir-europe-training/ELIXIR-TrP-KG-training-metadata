from typing import Any

from pydantic import AnyUrl, BaseModel, Field


class TessScientificTopic(BaseModel):
    preferred_label: str # Data visualisation
    uri: AnyUrl # http://edamontology.org/topic_0092


class TessTrainingMaterial(BaseModel):
    id: int
    title: str # fhdsl/better_plots
    url: AnyUrl # https://tess.elixir-europe.org/materials/fhdsl-better_plots
    description: str | None = None
    doi: str | None = None
    remote_updated_date: str | None = None
    remote_created_date: str | None = None
    scientific_topics: list[TessScientificTopic] = Field(default_factory=list)
    operations: list[dict[str, Any]] = Field(default_factory=list)
    external_resources: list[dict[str, Any]] = Field(default_factory=list)
