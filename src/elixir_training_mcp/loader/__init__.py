from __future__ import annotations

"""
Utilities for loading and parsing harvested training metadata.

The loader package breaks the original ``data_store`` module into focused
components so the orchestration layer can stay slim while behaviour remains
unchanged.
"""

from .graph import load_dataset, load_source_graph
from .parser import extract_resources_from_graph
from .dedupe import is_richer_resource, resolve_resource_identifier

__all__ = [
    "extract_resources_from_graph",
    "is_richer_resource",
    "load_dataset",
    "load_source_graph",
    "resolve_resource_identifier",
]
