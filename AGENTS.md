# Repository Guidelines

## Project Structure & Module Organization
The package lives under `src/elixir_training_mcp/`:

- `main.py`: FastAPI app serving the MCP server on `/mcp`, a Pydantic AI agent over AG-UI on `/chat`, and the light-chat UI on `/`. The `cli()` entry point starts it with uvicorn, or the MCP server alone with `--stdio`.
- `mcp_server.py`: MCP server (`MCPServer` of the MCP SDK v2) with the `get_sparql_examples`, `get_sparql_schema` and `execute_sparql_query` tools, and the `show_upcoming_trainings` and `show_instructors_map` MCP App tools (`Apps` extension).
- `widgets/`: self-contained HTML of the MCP Apps widgets, speaking the MCP Apps protocol over `postMessage` without SDK or build step.
- `sparql.py`: SPARQL queries to the endpoint, loading the examples and the VoID schema from their named graphs.
- `vectordb.py`: embedded LanceDB index of the examples and classes schemas, with a fastembed embedding function registered in the LanceDB registry, searched with hybrid search.
- `config.py`: settings from environment variables or `.env`.
- `harvest/`: harvesters of TeSS, GTN and the SciLifeLab Training Portal producing the `data/*.ttl` files loaded in Qlever by `compose.yml`.

SPARQL examples are in `docs/sparql-examples.ttl`, the VoID generation query in `docs/generate-void.ru`.

## Build, Test, and Development Commands
- `docker compose up -d` deploys the Qlever SPARQL endpoint on port 7001 (`QLEVER_PORT` to change it), with the VoID and examples graphs.
- `uv run elixir-trainer` starts the app on http://localhost:8000 (`--port` to change it).
- `docker compose up -d --build` deploys the Qlever endpoint and the app (`api` service, built from the `Dockerfile`).
- `uv run elixir-trainer --stdio` runs only the MCP server with the STDIO transport.
- `uv run --group dev ruff check src` enforces the lint ruleset.
- `uv run --group dev mypy src` validates typing.

## Coding Style & Naming Conventions
Follow Python 3.11+ typing with explicit return types on public functions. Keep imports sorted and grouped; Ruff enforces `I` and `TID` rules. Prefer descriptive module names and snake_case for functions, while Pydantic models use PascalCase. Maintain four-space indentation and target 120-character lines; document HTTP schemas or dataset constants as module-level enums when practical.

## Testing Guidelines
Use pytest with asyncio support already configured. Name new tests `test_*` and scope async fixtures at session level when they reach remote APIs. Add contract tests for each tool or resource exposed by `mcp_server.py`, and isolate network-dependent tests behind custom markers so they can be skipped offline (`pytest -m "not network"`). Keep coverage above the default threshold reported by `--cov=src`, and add regression cases whenever updating query adapters.

## Commit & Pull Request Guidelines
The history follows Conventional Commits (`feat:`, `fix:`, `doc:`); include scope names like `feat(models): ...` when touching isolated modules. Describe behavioral changes and reference GitHub issues using `Closes #ID`. Before opening a PR, run linting and tests locally and note the results in the description. Include screenshots or sample MCP payloads whenever you change request/response schemas, and call out breaking interface changes with the `!` syntax (`feat!: ...`).
