# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides access to ELIXIR training materials from platforms like TeSS (Training eSupport System) and Glittr. The project aims to create queryable knowledge graphs from Bioschemas-formatted training metadata to enable use cases like custom learning paths, trainer profiles, and cross-database connections.

## Architecture

### Core Components

- **MCP Server (`src/elixir_training_mcp/mcp_server.py`)**: FastMCP-based server that exposes tools for searching training materials. Supports both STDIO and Streamable HTTP transports.
  - Main tool: `search_training_materials()` - queries the TeSS API to find relevant training materials
  - CLI entry point: `cli()` function handles argument parsing and server initialization

- **Data Models (`src/elixir_training_mcp/models.py`)**: Pydantic models defining the structure of TeSS API responses:
  - `TessTrainingMaterial`: Represents a training resource with metadata (title, URL, description, topics, operations)
  - `TessScientificTopic`: Represents EDAM ontology topics associated with materials

### External Dependencies

- **TeSS API**: Primary data source at `https://tess.elixir-europe.org`
  - Search endpoint: `/materials?q={query}`
  - Returns JSON with training material metadata
  - Uses Bioschemas training profile standard
  - Full API documentation: https://tess.elixir-europe.org/api/json_api

## Development Commands

### Running the MCP Server

```bash
# Run with STDIO transport (default)
uv run elixir-training-mcp

# Run with HTTP transport
uv run elixir-training-mcp --http

# Run with custom port
uv run elixir-training-mcp --http --port 8000
```

### Testing

```bash
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_specific.py

# Run with verbose output
uv run pytest -vvv
```

### Type Checking

```bash
# Run mypy type checking
uv run mypy src/
```

### Code Quality

```bash
# Run pre-commit hooks
uv run pre-commit run --all-files

# Install pre-commit hooks
uv run pre-commit install
```

### Linting

```bash
# Ruff is configured in pyproject.toml
# Check code
uv run ruff check src/

# Format code
uv run ruff format src/
```

## Project Configuration

- **Build System**: Uses `hatchling` as build backend
- **Python Version**: Requires Python >=3.10
- **Package Manager**: Uses `uv` for dependency management (not pip)
- **Version Source**: Version is defined in `src/elixir_training_mcp/__init__.py`

## Key Development Notes

- The project uses `uv` (not pip) for all Python operations - always prefix commands with `uv run`
- MCP server transport mode is determined by CLI arguments, not configuration files
- The server returns JSON responses by default (`json_response=True`)
- TeSS API queries are URL-encoded using `urllib.parse.quote()`
- All API calls use async/await pattern with `httpx.AsyncClient`
