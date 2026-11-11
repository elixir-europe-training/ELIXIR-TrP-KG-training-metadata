"""Configuration from environment variables, named as the fields in upper case, e.g. `SPARQL_ENDPOINT_URL`."""

from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Comma-separated list in an environment variable, e.g. `a,b`, instead of the JSON parsed by default
CommaList = Annotated[
    list[str],
    NoDecode,
    BeforeValidator(lambda v: [i.strip() for i in v.split(",") if i.strip()] if isinstance(v, str) else v),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SPARQL endpoint with the harvested training data, the VoID description and the SPARQL examples
    # sparql_endpoint_url: str = "http://localhost:7001"
    sparql_endpoint_url: str = "https://biosoda.unil.ch/elixir-trainer/sparql"
    graph_base: str = "https://w3id.org/elixir-trainer/graph/"

    # Embedded LanceDB vector store, rebuilt at startup from the examples and VoID of the endpoint
    lancedb_path: Path = Path("data/lancedb")
    # Small, open (Apache 2.0) and multilingual embedding model, run with ONNX by fastembed (int8 weights, 1.1 GB)
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B-Q"
    # Downloaded models, kept across restarts (fastembed only downloads a model missing from it)
    fastembed_cache_path: Path = Path("data/fastembed")
    retrieved_docs: int = 5

    # OpenAI-compatible endpoint of the chat agent, with its tool calling models (the first is the default)
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: SecretStr | None = None
    models: CommaList = [
        "deepseek/deepseek-v4.1-flash-1017",
        "mistralai/mistral-large-4-0",
        "anthropic/claude-haiku-5.5",
        "openai/gpt-6-luna",
    ]

    # Public hostnames of the app, e.g. `training.example.org`, accepted by the MCP DNS rebinding protection
    allowed_hosts: CommaList = [
        "biosoda.unil.ch",
    ]

    @property
    def examples_graph(self) -> str:
        return f"{self.graph_base}sparql-examples"

    @property
    def void_graph(self) -> str:
        return f"{self.graph_base}void"


settings = Settings()
