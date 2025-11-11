# Architecture & Optimizations

This document complements `docs/STORE_OVERVIEW.md` by explaining how the repository is structured, which performance-minded decisions we made, and why those choices help the MCP server respond quickly and consistently.

## 1. High-Level Flow

1. **Harvested RDF snapshots** (`data/tess_harvest.ttl`, `data/gtn_harvest.ttl`) ship with the repo so we can answer offline queries without waiting for TeSS/GTN APIs.
2. **Loader package** (`src/elixir_training_mcp/loader/`) parses the TTL graphs into immutable `TrainingResource` dataclasses (`data_models.py`) and deduplicates overlapping metadata.
3. **Indexes + stats** (`data_store.py` + `indexes/`) precompute the search structures that power the MCP tools.
4. **TrainingDataService singleton** (`services.py`, `tools.py`) exposes read-only lookups that return JSON-friendly payloads.
5. **MCP server** (`mcp_server.py`) wires the live TeSS proxy, offline tools, and SPARQL executor into FastMCP.

Everything above runs once at process start, then individual tool calls simply read from in-memory data.

## 2. Key Architectural Decisions

### 2.1 Ship Harvested TTL Files

- Bundling the TTL files avoids runtime dependency on slow harvesting jobs (~30 minutes per TeSS scrape) and removes rate-limit risk.
- Developers can refresh snapshots via `uv run src/elixir_training_mcp/harvest/*.py` when needed, but clients always see a known-good dataset.

### 2.2 Typed, Immutable Data Models

- `TrainingResource`, `CourseInstance`, and `Organization` are frozen `@dataclass` types. They encode schema.org fields once and prevent accidental mutation when multiple indexes share the same object.
- Helper converters (e.g., `literal_to_datetime`, `literal_to_float`) centralize RDF literal parsing so edge cases (timezone-naive dates, blank strings) are handled uniformly.

### 2.3 Modular Loader Pipeline

- `loader.graph`, `loader.parser`, `loader.dedupe`, and `loader.utils` separate responsibilities so each layer can be tested in isolation (`tests/test_loader_modules.py`).
- `load_dataset` binds schema namespaces before parsing, making downstream SPARQL debugging easier and avoiding missing predicates (HTTP vs HTTPS variants).
- `_collect_*` helpers in `parser.py` normalize common schema.org constructs (nested addresses, Person blank nodes, EDAM topics) instead of scattering logic across the service layer.

### 2.4 Deterministic Deduplication

- `resolve_resource_identifier` uses `schema:url` when available and falls back to the subject URI or blank-node ID, guaranteeing stable keys.
- `select_richest` scores competing `TrainingResource` instances (`resource_quality`) so the metadata-rich version wins. This is especially important because TeSS and GTN can describe the same course with varying fields.
- The dedupe step keeps `resources_by_uri` as the single source of truth; every index just contains URI strings, which keeps memory usage predictable.

### 2.5 Eager, Read-Only Index Construction

- `_build_indexes` in `data_store.py` materializes **all** indexes (keyword, provider, location, date, topic) during startup, even if the current query only needs one. The cost is a handful of linear passes while the graphs are already hot in memory; the payoff is that no future request experiences a cold start.
- Each index stores the minimum data required (mostly tuples of URIs) and uses `MappingProxyType` so they can be safely shared between concurrent tool calls.
- Why eager construction instead of lazy loading?
  - Every MCP tool exposes the same `TrainingDataStore` object; making attributes optional would complicate the API and introduce locking to guard initialization.
  - Building indexes during `load_training_data` ensures a single, time-stamped snapshot (`TrainingDataStore.load_timestamp`) so keyword and provider searches cannot go out of sync.
  - Lookup paths become trivial: tokenization for keywords, normalized strings for provider/location/topic, and a pre-sorted schedule list for date range filtering.

### 2.6 Index-Specific Optimizations

- **KeywordIndex** (`indexes/keyword.py`): tokenizes names, descriptions, abstracts, keywords, learning levels, prerequisites, and `teaches` strings. A token bucket approach (with `append_unique`) approximates an inverted index without bringing in a search engine dependency.
- **ProviderIndex**: normalizes provider names to lowercase and trims whitespace so “ELIXIR” and “elixir ” collapse into the same bucket, guaranteeing O(1) lookup.
- **LocationIndex**: builds both country-only and `(country, city)` maps from course instances, enabling fast fallback from city-specific to country-wide queries.
- **DateIndex**: stores `CourseSchedule` entries sorted by start datetime. Date searches simply walk the sorted tuple once; they do not scan the entire resource set repeatedly.
- **TopicIndex**: stores both the raw topic string and (if the topic looks like a URI) the trailing component, so `topic_search("topic_0092")` and `topic_search("http://edamontology.org/topic_0092")` return identical results.
- **Stats**: `_build_stats` calculates distribution counters up front, so `dataset_stats` just returns cached numbers instead of reprocessing the dataset.

### 2.7 Service & MCP Layer

- `TrainingDataService` converts resources to JSON-friendly dictionaries on demand, keeping the indexes decoupled from serialization concerns.
- `get_training_data_service()` caches a singleton to avoid reparsing 7MB+ TTL files on every tool invocation; commands like `dataset_stats` therefore read shared data structures.
- `mcp_server.py` uses FastMCP with `async` HTTPX clients for live TeSS searches and synchronous RPC for offline tools. The CLI supports both STDIO and HTTP transports with configurable port/log-levels.
- A shared in-memory `rdflib.Dataset` with `default_union=True` powers the `execute_sparql_query` tool, so advanced clients can run ad-hoc queries without standing up an external triplestore.

### 2.8 Testing & Tooling

- `uv` scripts wrap linting (`ruff`), typing (`mypy`), and tests (`pytest` with coverage + async fixtures) to ensure contributors run the same commands locally.
- Tests cover the loader, indexes, tools, and service wrappers; fixtures include miniature TTL graphs mirroring TeSS/GTN quirks (blank nodes, nested addresses).
- Ruff + MyPy guard against common regressions (sorted imports, typing discipline, unsafe builtins) without requiring separate configuration steps.

### 2.9 Future-Facing Hooks

- `vectordb.py` documents an experimental path for semantic search (FastEmbed + Qdrant). Keeping it as a dormant module makes it easy to revisit vector-based retrieval without polluting the current lightweight runtime.
- Documentation (`docs/QUERY_FLOW.md`, `docs/STORE_OVERVIEW.md`) and the README call out how to connect MCP clients, regenerate data, and deploy SPARQL endpoints, reducing onboarding time.

## 3. Operational Benefits

- **Consistency:** Every offline tool is backed by the same immutable snapshot, so cross-tool answers never disagree due to race conditions.
- **Latency:** Startup parses and indexing take milliseconds relative to the 30-minute harvest pipeline, and every subsequent request is a pure in-memory lookup.
- **Reliability:** Shipping TTL dumps and caching the service removes network dependencies for keyword/provider/location/date/topic searches.
- **Extensibility:** Modular loaders and indexes mean we can add new search dimensions (e.g., accessibility filters) by adding a dedicated index without touching the loader core.
- **Observability:** `dataset_stats`, `per_source_counts`, and `source_graphs` expose enough metadata to confirm what data is loaded, which is essential when regenerating TTL files.

## 4. Quick Reference

- Build & run MCP server: `uv run elixir-training-mcp [--http --port <N>]`
- Harvest updates: `uv run src/elixir_training_mcp/harvest/harvest_tess.py`
- Tests: `uv run --group dev pytest`
- Lint: `uv run --group dev ruff check src`
- Types: `uv run --group dev mypy src`

Keeping these pieces working in lockstep is what lets the MCP server answer rich training-material queries quickly and safely, whether the user is online or offline.
