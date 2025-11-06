"""Singleton TrainingDataService used by MCP tools."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from elixir_training_mcp import data_store
from elixir_training_mcp.tools import TrainingDataService

_service_instance: TrainingDataService | None = None
# _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def get_training_data_service() -> TrainingDataService:
    global _service_instance  # pylint: disable=global-statement
    if _service_instance is None:
        tess_path = Path(str(files("elixir_training_mcp").joinpath("data/tess_harvest.ttl")))
        gtn_path = Path(str(files("elixir_training_mcp").joinpath("data/gtn_harvest.ttl")))
        store = data_store.load_training_data({
            "tess": tess_path,
            "gtn": gtn_path,
        })
        _service_instance = TrainingDataService(store)
    return _service_instance
