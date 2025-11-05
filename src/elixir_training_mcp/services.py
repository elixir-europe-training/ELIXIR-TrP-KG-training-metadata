"""Singleton TrainingDataService used by MCP tools."""

from __future__ import annotations

from pathlib import Path

from elixir_training_mcp import data_store
from elixir_training_mcp.tools import TrainingDataService


_service_instance: TrainingDataService | None = None
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def get_training_data_service() -> TrainingDataService:
    global _service_instance  # pylint: disable=global-statement
    if _service_instance is None:
        store = data_store.load_training_data({
            "tess": _DATA_DIR / "tess_harvest.ttl",
            "gtn": _DATA_DIR / "gtn_harvest.ttl",
        })
        _service_instance = TrainingDataService(store)
    return _service_instance
