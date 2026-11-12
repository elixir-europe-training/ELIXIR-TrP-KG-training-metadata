# Project 18: Mining the potential of knowledge graphs for metadata on training

[![PyPI - Version](https://img.shields.io/pypi/v/elixir-training-mcp.svg?logo=pypi&label=PyPI&logoColor=silver)](https://pypi.org/project/elixir-training-mcp/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/elixir-training-mcp.svg?logo=python&label=Python&logoColor=silver)](https://pypi.org/project/elixir-training-mcp/)
[![Generate paper PDF](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/actions/workflows/paper.yml/badge.svg)](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/actions/workflows/paper.yml)

## Abstract

Knowledge graphs (KGs) can greatly increase the potential of data by revealing hidden relationships and turning it into useful information. A KG is a graph-based representation of data that stores relations between subjects, predicates and objects in triplestores. These entities are typically described in pre-defined ontologies, which increase interoperability and connect data that would otherwise remain isolated in siloed databases. This structured data representation can greatly facilitate complex querying and applications to deep learning approaches like generative AI.

ELIXIR and its Nodes are making a major effort to make the wealth of open training materials on the computational life sciences reusable, amongst others by guidelines and support for annotating training materials with standardized metadata. One major step in standardizing metadata is the use of the Bioschemas training profile, which became a standard for representing training metadata. Despite being standardized and interoperable, there is still a lot of potential to turn these resources into valuable information, linking training data across various databases.

In this project, we aim to create queryable KGs derived from training metadata in the Bioschemas format available from platforms like TeSS and glittr.org. In a subsequent step, we will investigate the potential of such KGs for several use cases, including construction of custom learning paths, creation of detailed trainer profiles, and connection of  training metadata to other databases. These use-cases will also shed light on the limits on the currently available metadata, and will help to make future choices on richer metadata and standards.

## Leads

Geert van Geest, Harshita Gupta, Vincent Emonet

## 🚜 Harvesting training data

[![Harvest](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/actions/workflows/harvest.yml/badge.svg)](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/actions/workflows/harvest.yml)

> [!IMPORTANT]
>
> Data is automatically harvested by a workflow every first day of the month, and can be downloaded from GitHub workflows latest run artifacts: https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/actions/workflows/harvest.yml
>
> You can unzip the artifact and replace the `.ttl` files in the folder `src/elixir_training_mcp/data/` with the new files from the artifact.

Otherwise you can run harvesting manually (takes ~30min)

Harvest TeSS:

```sh
uv run src/elixir_training_mcp/harvest/harvest_tess.py
```

Harvest GTN:

```sh
uv run src/elixir_training_mcp/harvest/harvest_gtn.py
```

Harvest the [SciLifeLab Training Portal](https://training.scilifelab.se) (events and catalogue courses):

```sh
uv run src/elixir_training_mcp/harvest/harvest_scilifelab.py
```


> [!NOTE]
>
> TeSS contains training materials and courses from various providers, such as GTN (Galaxy Training Network) training materials. Metadata about material in TeSS and GTN can be matched on `schema:url`

Deploy a SPARQL endpoint on http://localhost:8000:

```sh
uv run rdflib-endpoint serve src/elixir_training_mcp/data/*_harvest.ttl
```

Or deploy a QLever SPARQL endpoint on http://localhost:7001, loading each `data/*.ttl` file in its own named graph. Create a `.env` file with an access token used for SPARQL updates (to insert the VoID description generated from the graph):

```sh
echo "QLEVER_ACCESS_TOKEN=$(openssl rand -hex 24)" > .env
docker compose up -d
```

Once the endpoint is up, the `generate-metadata` job runs [`docs/generate-void.ru`](docs/generate-void.ru) to store VoID statistics (class and property partitions) in the `https://w3id.org/elixir-trainer/graph/void` named graph, then loads [`docs/sparql-examples.ttl`](docs/sparql-examples.ttl) in the `https://w3id.org/elixir-trainer/graph/sparql-examples` named graph. To regenerate them without rebuilding the index:

```sh
docker compose run --rm --no-deps generate-metadata
```

## 💬 MCP server and agent

A remote [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server to search the training knowledge graph with SPARQL, with [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview) showing the upcoming trainings of an organization, and a map of the instructors by country. The same app serves a chat agent using it ([Pydantic AI](https://ai.pydantic.dev) with the [light-chat](https://github.com/vemonet/light-chat) UI):

- `/mcp`: MCP server (Streamable HTTP)
- `/chat`: [AG-UI](https://docs.ag-ui.com) endpoint of the agent
- `/`: chat UI, showing the MCP Apps widgets

### 🧰 Available MCP tools

| Tool | Description |
| ---- | ----------- |
| `get_sparql_examples` | SPARQL query examples relevant to a question |
| `get_sparql_schema` | Schema of the classes relevant to some concepts (predicates and types of their values, as ShEx) |
| `execute_sparql_query` | Run a SPARQL SELECT or ASK query on the endpoint |
| `show_upcoming_trainings` | MCP App: interactive view of the upcoming trainings of an organization (e.g. `SIB`), filterable by text, mode and country |
| `show_instructors_map` | MCP App: map of the instructors by country (e.g. `Switzerland`), listing the instructors of the selected country, sortable by number of courses, recent course or countries, and filterable by topic, mode, provider and date |

The examples and classes schemas are loaded at startup from the `sparql-examples` and `void` named graphs of the SPARQL endpoint, and indexed in an embedded [LanceDB](https://lancedb.com) vector store (`data/lancedb`), searched with hybrid search (vectors and BM25 full-text search, fused with Reciprocal Rank Fusion). LanceDB generates the embeddings with [`Qwen/Qwen3-Embedding-0.6B`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) (Apache 2.0, 100+ languages), quantized to int8 and run with ONNX by [fastembed](https://github.com/qdrant/fastembed) (1.1 GB downloaded on first start).

### ⚡️ Usage

> [!IMPORTANT]
>
> Requirements: [`uv`](https://docs.astral.sh/uv/getting-started/installation/), and the SPARQL endpoint deployed with `docker compose up -d` (see above).

Configure the agent in a `.env` file, it uses an OpenAI-compatible endpoint ([OpenRouter](https://openrouter.ai) by default):

```sh
OPENAI_API_KEY=sk-or-...
# Optional
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODELS=deepseek/deepseek-v4.1-flash-1017,mistralai/mistral-large-4-0
SPARQL_ENDPOINT_URL=http://localhost:7001
# Public hostnames of the app, when deployed behind a reverse proxy
ALLOWED_HOSTS=training.example.org
```

Start the app on http://localhost:8000:

```sh
uv run elixir-trainer
```

Or only the MCP server with the STDIO transport:

```sh
uv run elixir-trainer --stdio
```

### 🐳 Deploy with Docker

The `api` service of [`compose.yml`](compose.yml) deploys the app on http://localhost:8000 (`API_PORT` to change it), next to the Qlever endpoint. It starts once the SPARQL examples and VoID are loaded, and reads the agent configuration (`OPENAI_API_KEY`, `MODELS`, `ALLOWED_HOSTS`...) from the `.env` file. The embedding model is downloaded on the first start only, in the `fastembed-cache` volume.

Deploy everything:

```sh
docker compose up -d --build
```

> [!TIP]
>
> To skip the first download, copy a local cache of the model (`data/fastembed`, filled when running the app with `uv`) in the volume before the first start:
>
> ```sh
> docker compose build api
> docker volume create elixir-trp-kg-training-metadata_fastembed-cache
> docker run --rm -v elixir-trp-kg-training-metadata_fastembed-cache:/cache -v ./data/fastembed:/src:ro elixir-trp-kg-training-metadata-api cp -a /src/. /cache/
> ```

When deployed behind a reverse proxy, add its public hostname to `ALLOWED_HOSTS` in `.env`, so the MCP server accepts the requests forwarded to `/mcp`.

Check lint and types:

```sh
uv run --group dev ruff check src
uv run --group dev mypy src
```

### 🔌 Connect client to MCP server

Follow the instructions of your favorite chat client.

To add a new MCP server to [**VSCode GitHub Copilot**](https://code.visualstudio.com/docs/copilot/overview):

- Install the [`GitHub.copilot`](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension
- Open the Command Palette (`ctrl+shift+p` or `cmd+shift+p`)
- Search for `MCP: Add Server...`
  - Choose `STDIO`, and provide the command: `uvx --from elixir-training-mcp elixir-trainer --stdio`
  - Or choose `HTTP`, and provide the MCP server URL, e.g. http://localhost:8000/mcp

To use it with STDIO transport, your VSCode `mcp.json` should look like:

```json
{
   "servers": {
      "elixir-training-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": ["--from", "elixir-training-mcp", "elixir-trainer", "--stdio"]
      }
   }
}
```

> [!TIP]
>
> You can use a local folder for development:
>
> ```json
> {
>    "servers": {
>       "elixir-training-mcp": {
>          "type": "stdio",
>          "cwd": "~/dev/ELIXIR-TrP-KG-training-metadata",
>          "command": "uv",
>          "args": ["run", "elixir-trainer", "--stdio"]
>       }
>    }
> }
> ```

You can also connect to a running server using Streamable HTTP:

```json
{
    "servers": {
        "elixir-training-mcp-http": {
            "url": "http://localhost:8000/mcp",
            "type": "http"
        }
    }
}
```

