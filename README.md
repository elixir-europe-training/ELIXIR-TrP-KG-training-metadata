# Project 18: Mining the potential of knowledge graphs for metadata on training

[![PyPI - Version](https://img.shields.io/pypi/v/elixir-training-mcp.svg?logo=pypi&label=PyPI&logoColor=silver)](https://pypi.org/project/elixir-training-mcp/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/elixir-training-mcp.svg?logo=python&label=Python&logoColor=silver)](https://pypi.org/project/elixir-training-mcp/)


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


> [!NOTE]
>
> TeSS contains training materials and courses from various providers, such as GTN (Galaxy Training Network) training materials. Metadata about material in TeSS and GTN can be matched on `schema:url`

Deploy a SPARQL endpoint on http://localhost:8000:

```sh
uv run rdflib-endpoint serve src/elixir_training_mcp/data/*_harvest.ttl
```

## 💬 MCP server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server to access and search through the training materials of multiple Elixir repositories, such as [TeSS](https://tess.elixir-europe.org/) and [Glittr](https://glittr.org/).

### ⚡️ Usage

> [!IMPORTANT]
>
> Requirement: [`uv`](https://docs.astral.sh/uv/getting-started/installation/), to easily handle python scripts and virtual environments

Use with STDIO transport:

```sh
uv run elixir-training-mcp
```

Use with Deploy as Streamable HTTP server:

```sh
uv run elixir-training-mcp --http
```

### 🧰 Available MCP tools

Once the server is running you can call the following tools from your MCP-compatible client:

| Tool | Description |
| ---- | ----------- |
| `search_training_materials` | Proxies the live TeSS API and returns raw JSON results. |
| `keyword_search` | Searches the harvested TTL datasets (TeSS + GTN) by free-text keyword and returns enriched metadata. |
| `provider_search` | Filters harvested resources by provider name (case-insensitive). |
| `location_search` | Returns TeSS course instances in a given country (optionally city). |
| `date_search` | Finds TeSS course instances starting within a provided ISO date range. |
| `topic_search` | Matches harvested resources by EDAM identifier or topic label. |
| `dataset_stats` | Summarises dataset diagnostics (resource counts, type distribution, access modes). |

> [!NOTE]
> The local tools read from `data/tess_harvest.ttl` and `data/gtn_harvest.ttl`. Regenerate these files with the harvest scripts if you need fresher data.

### 🔌 Connect client to MCP server

Follow the instructions of your favorite chat client.

To add a new MCP server to [**VSCode GitHub Copilot**](https://code.visualstudio.com/docs/copilot/overview):

- Install the [`GitHub.copilot`](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension
- Open the Command Palette (`ctrl+shift+p` or `cmd+shift+p`)
- Search for `MCP: Add Server...`
  - Choose `STDIO`, and provide the command: `uvx elixir-training-mcp`
  - Or choose `HTTP`, and provide the MCP server URL, e.g. http://localhost:8000/mcp

To use it with STDIO transport, your VSCode `mcp.json` should look like:

```json
{
   "servers": {
      "elixir-training-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": ["elixir-training-mcp"]
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
>          "args": ["run", "elixir-training-mcp"]
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

