"""Embedded LanceDB index of the SPARQL examples and classes schemas, searched with hybrid search: dense vectors and
BM25 full-text search, fused with Reciprocal Rank Fusion. LanceDB generates the embeddings itself on insert and search,
with a fastembed (ONNX, no torch) embedding function registered in its registry."""

import logging
from functools import cache
from typing import Any, Literal

import lancedb
import numpy as np
from fastembed import TextEmbedding
from lancedb.embeddings import TextEmbeddingFunction, get_registry, register
from lancedb.pydantic import LanceModel, Vector

from elixir_training_mcp.config import settings
from elixir_training_mcp.sparql import load_classes_schema, load_examples

logger = logging.getLogger(__name__)

TABLE = "docs"
DocType = Literal["example", "class"]


@cache
def fastembed_model(name: str) -> TextEmbedding:
    """Loaded on first use, it takes a few seconds (and downloads the model the first time)"""
    return TextEmbedding(name, cache_dir=str(settings.fastembed_cache_path))


@register("fastembed")
class FastEmbedEmbeddings(TextEmbeddingFunction):
    """fastembed model, with an instruction before queries (none before documents) as expected by Qwen3 embeddings"""

    name: str = settings.embedding_model
    query_instruction: str = "Given a question, retrieve relevant SPARQL query examples and classes schemas"

    def ndims(self) -> int:
        return TextEmbedding.get_embedding_size(self.name)

    def compute_query_embeddings(self, query: str, *args: Any, **kwargs: Any) -> list[np.ndarray | None]:
        return self.generate_embeddings([f"Instruct: {self.query_instruction}\nQuery:{query}"])

    def generate_embeddings(self, texts: list[str] | np.ndarray, *args: Any, **kwargs: Any) -> list[np.ndarray | None]:
        return list(fastembed_model(self.name).embed(list(texts)))


embedder = get_registry().get("fastembed").create()


class Doc(LanceModel):
    doc_type: str
    label: str
    # Returned to the client: the SPARQL query of an example, or the ShEx shape of a class
    answer: str
    # Embedded and full-text indexed: the question of an example, or the ShEx shape of a class
    text: str = embedder.SourceField()
    vector: Vector(embedder.ndims()) = embedder.VectorField()  # type: ignore[valid-type]


@cache
def db() -> lancedb.DBConnection:
    return lancedb.connect(settings.lancedb_path)


async def init_index() -> None:
    """(Re)build the index from the examples and VoID graphs of the endpoint. Keeps the existing index if the endpoint
    can not be reached"""
    try:
        examples = await load_examples()
        classes = await load_classes_schema()
    except Exception as e:
        if TABLE in db().table_names():
            logger.warning(f"Could not load docs from {settings.sparql_endpoint_url}, using the existing index: {e}")
            return
        raise RuntimeError(f"Could not load docs from {settings.sparql_endpoint_url} to build the index: {e}") from e
    docs = [
        {"doc_type": "example", "label": ex["question"], "answer": ex["query"], "text": ex["question"]}
        for ex in examples
    ]
    docs += [{"doc_type": "class", "label": c["label"], "answer": c["shex"], "text": c["shex"]} for c in classes]
    if not docs:
        logger.warning(
            f"No SPARQL examples nor VoID found in {settings.sparql_endpoint_url}, in the graphs "
            f"<{settings.examples_graph}> and <{settings.void_graph}>: `get_sparql_examples` and `get_sparql_schema` "
            "will not work. Check SPARQL_ENDPOINT_URL, or load them with `docker compose run --rm --no-deps generate-metadata`"
        )
        return
    table = db().create_table(TABLE, schema=Doc, mode="overwrite")
    table.add(docs)
    table.create_fts_index("text", replace=True)
    logger.info(f"Indexed {len(examples)} SPARQL examples and {len(classes)} classes in {settings.lancedb_path}")


def search(queries: list[str], doc_type: DocType, limit: int | None = None) -> list[dict[str, Any]]:
    """Hybrid search of the docs of a type for each query, deduplicated, in the order of the queries"""
    if TABLE not in db().table_names():
        raise LookupError(
            f"The index is empty: no SPARQL examples nor VoID were found in {settings.sparql_endpoint_url}"
        )
    table = db().open_table(TABLE)
    results: dict[str, dict[str, Any]] = {}
    for query in queries:
        hits = (
            table.search(query, query_type="hybrid")
            .where(f"doc_type = '{doc_type}'", prefilter=True)
            .limit(limit or settings.retrieved_docs)
            .to_list()
        )
        for hit in hits:
            results.setdefault(hit["answer"], hit)
    return list(results.values())
