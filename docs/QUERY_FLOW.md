# Offline Query Flow

This guide walks through how the repo turns harvested RDF data into searchable
results, then follows a concrete keyword search (“Seurat loading data”) from
request to response.

## Data Preparation Pipeline

1. **Harvested TTL files** – `data/tess_harvest.ttl` and `data/gtn_harvest.ttl`
   ship with the repo.
2. **Loader orchestration** – `load_training_data` in
   `src/elixir_training_mcp/data_store.py` calls the loader package to:
   - parse each TTL via `loader.graph.load_dataset`,
   - extract resources with `loader.parser.extract_resources_from_graph`,
   - keep the richest version of each resource using `loader.dedupe.select_richest`.
3. **TrainingResource objects** – The parser normalises each RDF subject into a
   `TrainingResource` dataclass (`src/elixir_training_mcp/data_models.py`),
   capturing metadata such as title, description, provider, keywords, topics,
   accessibility info, timestamps, and a tuple of `CourseInstance` objects.
4. **Indexes** – Dedicated modules under `src/elixir_training_mcp/indexes/`
   build fast lookup tables from the resource map:
   - `keyword.py` (tokens → URIs),
   - `provider.py` (provider name → URIs),
   - `location.py` (country/city → URIs),
   - `date.py` (chronological course schedules),
   - `topic.py` (topic strings and short names → URIs).
   Shared helpers live in `indexes/utils.py`.
5. **TrainingDataStore** – `data_store.load_training_data` returns a
   `TrainingDataStore` containing the RDF dataset, immutable resource map,
   per-source counts, all indexes, and summary statistics.

## TrainingResource vs CourseInstance

- **TrainingResource** describes the learning material itself: canonical URI,
  titles, descriptions, keywords, provider, authors, accessibility metadata,
  topics, licence, timestamps, and more. Many online materials exist without
  scheduled sessions.
- **CourseInstance** represents one offering of that material. It records start
  and end datetimes, delivery mode, capacity, location (country, city, address,
  latitude/longitude), and organiser/funder organisations. Some resources have
  multiple instances; others (like self-paced tutorials) have none.

## Journey From Query To Result

Example request:

```json
{
  "query": "Seurat loading data",
  "limit": 5
}
```

Execution path:

1. **MCP tool call** – `TrainingDataService.search_by_keyword` in
   `src/elixir_training_mcp/tools.py` receives the query. It delegates to the
   keyword index and then resolves each URI into a JSON-friendly dictionary.
2. **Keyword lookup** – `KeywordIndex.lookup` (`indexes/keyword.py`) tokenises
   the query (`"seurat"`, `"loading"`, `"data"`), finds matching resource URIs,
   and honours the `limit`.
3. **Resource hydration** – For each URI the service reads the corresponding
   `TrainingResource` from `store.resources_by_uri` and builds the response
   dictionary. Fields like provider, keywords, topics, accessibility metadata,
   timestamps, and nested course instances come straight from the dataclass.
4. **Result example** – One of the returned items is the GTN tutorial
   “Clustering 3K PBMCs with Seurat”. Its `TrainingResource` contains the tokens
   “seurat”, “loading”, and “data” in the name/description, so the keyword index
   matches it. The tutorial is self-paced, so `course_instances` is an empty
   list; if it had scheduled sessions they would appear as serialised
  `CourseInstance` entries.

The same resource map powers other tools (provider, location, date, and topic
searches) via their respective indexes, all sharing the common
`TrainingResource`/`CourseInstance` model and returning the same
JSON-compatible format.
