"""FastAPI app serving the MCP server on `/mcp`, an AG-UI agent using it on `/chat`, and the light-chat UI on `/`."""

import argparse
import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from light_chat_ui import chat_router, setup_logging
from light_chat_ui.mcp_apps import PROXIED_REQUEST, UIToolset, proxied_response, ui_meta
from mcp.server.transport_security import TransportSecuritySettings
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.toolsets import ToolsetTool
from pydantic_ai.ui.ag_ui import AGUIAdapter

from elixir_training_mcp.config import settings
from elixir_training_mcp.mcp_server import mcp
from elixir_training_mcp.vectordb import init_index

# Logs of all libraries in the uvicorn style, without a line per HTTP request
setup_logging()
# No first-run banner of Pydantic AI
os.environ["PYDANTIC_AI_NO_BANNER"] = "1"


class AppsToolset(UIToolset):
    """MCP server whose raw results are sent to the chat only for the tools showing a UI (MCP Apps)"""

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any]
    ) -> Any:
        result = await super().call_tool(name, tool_args, ctx, tool)
        return result if ui_meta(tool).get("resourceUri") else result.return_value


# The MCP server of this app, called in-process by the agent
toolsets: list[UIToolset] = [AppsToolset(mcp, id=mcp.name)]
# Failed tool calls are sent back to the model a few times, e.g. to fix an invalid SPARQL query
agent = Agent(toolsets=toolsets, deps_type=str, retries={"tools": 3})
provider = OpenAIProvider(
    base_url=settings.openai_base_url,
    api_key=settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,
)


@agent.instructions
def instructions(ctx: RunContext[str]) -> str:
    """One system prompt (some models reject several), with the context sent by the frontend (AG-UI `context`)"""
    prompt = (
        "You are a helpful assistant helping users find training courses, events and materials in the life sciences, "
        "from ELIXIR TeSS and the Galaxy Training Network, using the tools of the MCP server. "
        f"Today is {date.today().isoformat()}. Always cite the URLs of the trainings you mention.\n\n"
        f"## Instructions of the MCP server\n\n{mcp.instructions}"
    )
    return f"{prompt}\n\n{ctx.deps}" if ctx.deps else prompt


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Build the vector index, and run the MCP session manager for the app lifetime"""
    await init_index()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="ELIXIR training agent", lifespan=lifespan)


@app.post("/chat")
async def chat(request: Request) -> Response:
    """AG-UI endpoint streaming the agent response, with the model picked in `forwardedProps.model`"""
    body = await request.json()  # cached, the adapter reads the body again
    forwarded = body.get("forwardedProps") or {}
    # MCP request from a widget, e.g. reading its UI resource or calling a tool of its server
    if PROXIED_REQUEST in forwarded:
        return await proxied_response(body, toolsets)
    model = forwarded.get("model") or settings.models[0]
    if model not in settings.models:
        raise HTTPException(400, f"Unknown model {model}, available: {', '.join(settings.models)}")
    context = "\n\n".join(f"{c['description']}:\n{c['value']}" for c in body.get("context") or [])
    return await AGUIAdapter.dispatch_request(
        request, agent=agent, model=OpenAIChatModel(model, provider=provider), deps=context
    )


# Chat UI at `/`, the model picked in the settings is sent in `forwardedProps.model`
app.include_router(
    chat_router(
        path="/",
        # Relative to the page, so it works behind a reverse proxy serving the app under a prefix
        url="chat",
        title="ELIXIR training agent",
        settings={"models": settings.models},
        themeSwitch=True,
        welcome=(
            "## Find trainings in the life sciences\nThe agent queries a knowledge graph of the courses, events and "
            "materials harvested from [ELIXIR TeSS](https://tess.elixir-europe.org) and the "
            "[Galaxy Training Network](https://training.galaxyproject.org) with SPARQL."
        ),
        placeholder="Ask about trainings",
        examples=[
            "Show the upcoming trainings of SIB",
            "Show the learning resources of SIB on proteomics",
            "Show the map of the instructors teaching single-cell courses",
            "Which organizations provided the most courses in 2025?",
            "Which online courses on single-cell RNA-seq start in the next 3 months?",
            "Quelles formations en Python sont proposées en France ?",
            "Which organizations provide the most trainings on machine learning?",
        ],
    )
)

# The MCP SDK only accepts localhost Host and Origin headers (DNS rebinding protection): the public hostnames of the
# app, behind a reverse proxy, are added to the allowed ones
local_hosts = ["127.0.0.1", "localhost", "[::1]"]
transport_security = TransportSecuritySettings(
    allowed_hosts=[f"{h}:*" for h in local_hosts] + settings.allowed_hosts,
    allowed_origins=[f"http://{h}:*" for h in local_hosts]
    + [f"{scheme}://{h}" for h in settings.allowed_hosts for scheme in ("https", "http")],
)
# MCP server at `/mcp`, its route added to the app instead of mounting it under a prefix
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=transport_security)
app.router.routes.extend(mcp_app.routes)


def cli() -> None:
    """Start the app over HTTP, or only the MCP server over STDIO"""
    parser = argparse.ArgumentParser(description="MCP server and agent to search ELIXIR trainings with SPARQL")
    parser.add_argument("--stdio", action="store_true", help="Run only the MCP server with the STDIO transport")
    parser.add_argument("--host", default="127.0.0.1", help="Host of the HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="Port of the HTTP server")
    args = parser.parse_args()
    if args.stdio:
        asyncio.run(init_index())
        mcp.run()
    else:
        uvicorn.run(app, host=args.host, port=args.port, proxy_headers=True, forwarded_allow_ips="*")
