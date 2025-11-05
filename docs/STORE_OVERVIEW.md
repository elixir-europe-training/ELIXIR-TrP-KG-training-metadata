# Offline Data Store Overview

This branch turns the repository into a self-contained catalogue of training resources. Below is a plain-language guide you can share with teammates.

## 1. Harvested Data
We bundle two RDF/TTL files under `data/`:

- `data/tess_harvest.ttl`: courses and events from TeSS.
- `data/gtn_harvest.ttl`: tutorials from the Galaxy Training Network.

If the files go stale, re-harvest them with the scripts in `src/elixir_training_mcp/harvest.py`.

## 2. Data Models (`src/elixir_training_mcp/data_models.py`)
Defines the Python “shape” for each resource:

- `TrainingResource`: everything about a training item (name, description, provider, keywords, topics, authors, timestamps, accessibility info, etc.).
- `CourseInstance`: start/end dates and locations for runnable courses.
- Helper functions convert RDF literals to strings, numbers, booleans, and datetimes with timezone-aware handling.

## 3. Data Loader & Indexes (`src/elixir_training_mcp/data_store.py`)
The heart of the system:

1. **Loading**
   ```python
   load_training_data({"tess": Path(...), "gtn": Path(...)})
   ```
   - Parses each TTL with RDFLib.
   - Normalizes subjects into `TrainingResource` entries (handles blank nodes and nested schema.org objects like Person, Language, CreativeWork).
   - Keeps a canonical ID (`schema:url` when available).

2. **Indexes**
   - Keyword index (tokens → resource IDs).
   - Provider index (provider name → resource IDs).
   - Location index (country/city → resource IDs based on course instances).
   - Date index (chronological list for range queries).
   - Topic index (handles both EDAM IDs and text labels).

3. **Stats**
   - Simple diagnostics: total resources, per-source counts, type distribution, access-mode stats, audience-role stats, sample topics.

The loader returns a `TrainingDataStore` object containing the resources, indexes, stats, and the raw RDF dataset (all wrapped in read-only mappings).

## 4. Service Wrapper (`src/elixir_training_mcp/tools.py`)
`TrainingDataService` wraps the store and exposes easy-to-use methods:

- `search_by_keyword`, `search_by_provider`, `search_by_location`, `search_by_date_range`, `search_by_topic`.
- Each returns JSON-serializable dictionaries (with nested course instance info).
- `service.stats` gives the diagnostics mentioned above.

## 5. Singleton Access (`src/elixir_training_mcp/services.py`)
`get_training_data_service()` loads the TTL files (using repo-relative paths) once and caches a `TrainingDataService` instance. MCP tools call this so they don’t reparse large graphs on every request.

## 6. MCP Entry Point (`src/elixir_training_mcp/mcp_server.py`)
- Keeps the original `search_training_materials` (live TeSS API).
- Adds offline tools backed by the local store:
  - `local_keyword_search`
  - `local_provider_search`
  - `local_location_search`
  - `local_date_search`
  - `local_topic_search`
  - `local_dataset_stats`
- Includes `_parse_iso_date` and a CLI fix so HTTP transport respects the chosen port/log level.

## 7. Tests & Fixtures
- `tests/fixtures/*.ttl` mirror TeSS and GTN structures in miniature (nested persons, language nodes, accessibility info).
- `tests/test_data_loader.py` validates the loader, canonical URLs, and stats.
- `tests/test_tools.py` exercises the service wrapper.
- Run `uv run --group dev pytest` to execute all tests (currently 10).

## 8. Documentation Updates
- README lists the new MCP tools, shows sample prompts, and explains the data dependency.
- AGENTS.md outlines build/test commands, style guidance, testing expectations, and tool summaries for contributors.

## TL;DR for Teammates
1. We ship the TeSS + GTN TTL data alongside the code.
2. On startup the loader parses those files, deduplicates resources, and builds search indexes plus stats.
3. A cached service exposes convenient search methods.
4. MCP tools use those methods to answer offline queries instantly.
5. Tests cover both the loader and service layers; docs explain how to deploy and use the tools.

This file lives in `docs/STORE_OVERVIEW.md` for quick reference.
