# App serving the MCP server on /mcp, the agent on /chat and the chat UI on /
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    # Embedding models are downloaded there on first start, mount a volume to keep them across restarts
    FASTEMBED_CACHE_PATH=/cache/fastembed

# Dependencies first, in their own layer. Larger timeout than uv's 30s for slow networks
ARG UV_HTTP_TIMEOUT=300
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

EXPOSE 8000
CMD ["elixir-trainer", "--host", "0.0.0.0", "--port", "8000"]
