# Repository Guidelines

## Project Structure & Module Organization
The MCP server lives under `src/elixir_training_mcp/`. `mcp_server.py` exposes the Typer CLI entry point `cli()` and wraps request routing. `models.py` defines Pydantic payload models for TeSS and Glittr queries, while `__init__.py` stores package metadata. Runtime configuration stays in `pyproject.toml`; generated lockfiles sit in `uv.lock`. When adding tests, place them in a new `tests/` directory mirroring the source layout (for example, `tests/test_mcp_server.py`).

The offline data loader is organised as follows:

- `data_store.py` is the public façade that returns a `TrainingDataStore` and exposes the search indexes. It keeps the legacy imports working for downstream callers.
- `loader/` contains the split-out implementation:
  - `loader/graph.py` loads TTL files into an RDF dataset and binds common namespaces.
  - `loader/parser.py` converts RDF subjects into `TrainingResource` instances.
  - `loader/dedupe.py` holds identifier resolution and “richer resource” scoring.
  - `loader/utils.py` hosts shared RDF helpers (schema predicates, literal conversions, etc.).
- `indexes` remain defined in `data_store.py` for now so the public API is unchanged.

## Build, Test, and Development Commands
- `uv run elixir-training-mcp` runs the STDIO MCP server for local client integration.
- `uv run elixir-training-mcp --http` starts the HTTP transport on the default port for remote clients (use `--port <PORT>` to override the default).
- `uv run --group dev pytest` executes the test suite with coverage settings from `pyproject.toml`; this includes `tests/test_tools.py` plus focused checks in `tests/test_loader_modules.py`, which exercise the offline search endpoints and loader internals.
- `uv run --group dev ruff check src` enforces the lint ruleset; add `--fix` only after reviewing changes.
- `uv run --group dev mypy src` validates typing expectations across the service layer.

## Coding Style & Naming Conventions
Follow Python 3.10+ typing with explicit return types on public functions. Keep imports sorted and grouped; Ruff enforces `I` and `TID` rules. Prefer descriptive module names and snake_case for functions, while Pydantic models use PascalCase. Maintain four-space indentation and target 120-character lines; document HTTP schemas or dataset constants as module-level enums when practical.

## Testing Guidelines
Use pytest with asyncio support already configured. Name new tests `test_*` and scope async fixtures at session level when they reach remote APIs. Add contract tests for each tool or resource exposed by `mcp_server.py`, and isolate network-dependent tests behind custom markers so they can be skipped offline (`pytest -m "not network"`). Keep coverage above the default threshold reported by `--cov=src`, and add regression cases whenever updating query adapters.

## MCP Server Tools
The server exposes both live and offline tools:
- `search_training_materials` queries TeSS directly (HTTP).
- Offline tools `local_keyword_search`, `local_provider_search`, `local_location_search`, `local_date_search`, `local_topic_search`, and `local_dataset_stats` read from `data/tess_harvest.ttl` and `data/gtn_harvest.ttl`. Regenerate these files with the harvest scripts before running the server if you need fresh data.

## Commit & Pull Request Guidelines
The history follows Conventional Commits (`feat:`, `fix:`, `doc:`); include scope names like `feat(models): ...` when touching isolated modules. Describe behavioral changes and reference GitHub issues using `Closes #ID`. Before opening a PR, run linting and tests locally and note the results in the description. Include screenshots or sample MCP payloads whenever you change request/response schemas, and call out breaking interface changes with the `!` syntax (`feat!: ...`).
