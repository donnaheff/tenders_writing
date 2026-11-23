"""Developer portal: MCP catalog, per-provider tool schemas, and a function-call executor.

The MCP server is the single source of truth. OpenAI, Anthropic and Gemini function
definitions are generated from the same tool list, so they can never drift apart.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bid_studio.config import settings
from bid_studio.mcp_server import INSTRUCTIONS, SERVER_NAME, SERVER_VERSION, build_server

PROVIDERS = ("openai", "openai-chat", "anthropic", "gemini")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter(tags=["developers"])


def _check_key(authorization: str | None, x_api_key: str | None) -> None:
    if not settings.mcp_api_key:
        return
    supplied = x_api_key or (authorization or "").removeprefix("Bearer ")
    if not hmac.compare_digest(supplied.encode(), settings.mcp_api_key.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


def format_tools(provider: str, tools: list[dict[str, Any]]) -> Any:
    """Convert MCP tool definitions into a provider's native function-calling shape."""
    if provider == "openai":  # Responses API
        return [
            {"type": "function", "name": t["name"], "description": t["description"],
             "parameters": t["input_schema"]}
            for t in tools
        ]
    if provider == "openai-chat":  # Chat Completions API
        return [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]
    if provider == "anthropic":  # Messages API
        return [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in tools
        ]
    if provider == "gemini":  # Gemini API / google-genai
        return [{"function_declarations": [
            {"name": t["name"], "description": t["description"],
             "parametersJsonSchema": t["input_schema"]}
            for t in tools
        ]}]
    raise ValueError(provider)


async def tool_catalog() -> list[dict[str, Any]]:
    out = []
    for t in await build_server().list_tools():
        ann = t.annotations
        out.append({
            "name": t.name,
            "description": (t.description or "").strip(),
            "input_schema": t.input_schema,
            "read_only": bool(ann and ann.read_only_hint),
        })
    return out


def base_url(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url)).rstrip("/")


def connection_snippets(url: str) -> list[dict[str, str]]:
    """Copy-paste setup for each major AI client. `url` is the public base URL."""
    mcp_url = f"{url}/mcp"
    auth = " (add the API key if one is configured)" if settings.mcp_api_key else ""
    key_hdr = '"Authorization": "Bearer $BID_STUDIO_API_KEY"'
    return [
        {
            "id": "claude-code", "name": "Claude Code", "lang": "bash",
            "note": "One command, available in every project.",
            "code": f"claude mcp add --transport http bid-studio {mcp_url} "
                    f'--header "Authorization: Bearer $BID_STUDIO_API_KEY" --scope user',
        },
        {
            "id": "claude-desktop", "name": "Claude Desktop / claude.ai", "lang": "json",
            "note": "claude.ai: Settings → Connectors → Add custom connector, and paste the URL. "
                    "Desktop (stdio) config below goes in claude_desktop_config.json.",
            "code": '{\n  "mcpServers": {\n    "bid-studio": {\n      "command": "bid-studio-mcp",\n'
                    f'      "env": {{ "BID_STUDIO_API_URL": "{url}", "BID_STUDIO_API_KEY": "<your key>" }}\n'
                    "    }\n  }\n}",
        },
        {
            "id": "claude-api", "name": "Claude API (MCP connector)", "lang": "python",
            "note": "Messages API with the remote MCP connector beta.",
            "code": "import anthropic\n\nclient = anthropic.Anthropic()\n"
                    "resp = client.beta.messages.create(\n"
                    '    model="claude-sonnet-5-5",\n    max_tokens=2048,\n'
                    '    messages=[{"role": "user", "content": "Find open IT tenders over 100k"}],\n'
                    f'    mcp_servers=[{{"type": "url", "url": "{mcp_url}", "name": "bid-studio",\n'
                    '                  "authorization_token": BID_STUDIO_API_KEY}],\n'
                    '    tools=[{"type": "mcp_toolset", "mcp_server_name": "bid-studio"}],\n'
                    '    betas=["mcp-client-2025-11-20"],\n)\nprint(resp.content)',
        },
        {
            "id": "openai-responses", "name": "OpenAI Responses API", "lang": "python",
            "note": "Remote MCP is a built-in tool; OpenAI calls your server directly.",
            "code": "from openai import OpenAI\n\nclient = OpenAI()\nresp = client.responses.create(\n"
                    '    model="gpt-5",\n    input="Find open IT tenders over 100k",\n'
                    f'    tools=[{{"type": "mcp", "server_label": "bid_studio",\n'
                    f'             "server_url": "{mcp_url}",\n'
                    '             "headers": {"Authorization": f"Bearer {BID_STUDIO_API_KEY}"},\n'
                    '             "require_approval": "never"}],\n)\nprint(resp.output_text)',
        },
        {
            "id": "openai-agents", "name": "OpenAI Agents SDK", "lang": "python",
            "note": "Use the MCP server as agent tools.",
            "code": "from agents import Agent, Runner\nfrom agents.mcp import MCPServerStreamableHttp\n\n"
                    "async with MCPServerStreamableHttp(params={\n"
                    f'    "url": "{mcp_url}",\n'
                    '    "headers": {"Authorization": f"Bearer {BID_STUDIO_API_KEY}"},\n}) as server:\n'
                    '    agent = Agent(name="Bid writer", mcp_servers=[server])\n'
                    '    print((await Runner.run(agent, "Summarise my open grant calls")).final_output)',
        },
        {
            "id": "chatgpt", "name": "ChatGPT", "lang": "text",
            "note": "Settings → Connectors → Advanced → Developer mode → add a custom MCP connector.",
            "code": f"Server URL: {mcp_url}\nAuthentication: API key / Bearer{auth}",
        },
        {
            "id": "gemini-cli", "name": "Gemini CLI", "lang": "json",
            "note": "Add to ~/.gemini/settings.json.",
            "code": '{\n  "mcpServers": {\n    "bid-studio": {\n'
                    f'      "httpUrl": "{mcp_url}",\n      "headers": {{ {key_hdr} }}\n    }}\n  }}\n}}',
        },
        {
            "id": "cursor", "name": "Cursor / VS Code", "lang": "json",
            "note": "Cursor: ~/.cursor/mcp.json. VS Code: .vscode/mcp.json (use \"servers\" and "
                    '"type": "http").',
            "code": '{\n  "mcpServers": {\n    "bid-studio": {\n'
                    f'      "url": "{mcp_url}",\n      "headers": {{ {key_hdr} }}\n    }}\n  }}\n}}',
        },
        {
            "id": "inspector", "name": "MCP Inspector (debug)", "lang": "bash",
            "note": "Browse and call tools interactively.",
            "code": f"npx @modelcontextprotocol/inspector --transport http --server-url {mcp_url}",
        },
    ]


@router.get("/developers", response_class=HTMLResponse, include_in_schema=False)
async def developers_page(request: Request):
    url = base_url(request)
    tools = await tool_catalog()
    return templates.TemplateResponse(
        request=request,
        name="developers.html",
        context={
            "app_name": settings.app_name,
            "base_url": url,
            "mcp_url": f"{url}/mcp",
            "auth_required": bool(settings.mcp_api_key),
            "tools": tools,
            "snippets": connection_snippets(url),
            "providers": PROVIDERS,
            "instructions": INSTRUCTIONS,
            "version": SERVER_VERSION,
        },
    )


@router.get("/api/v1/developers/mcp")
async def mcp_server_card(request: Request):
    """Machine-readable description of the MCP endpoint."""
    url = base_url(request)
    tools = await tool_catalog()
    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "transports": {"streamable_http": f"{url}/mcp", "stdio": "bid-studio-mcp"},
        "auth": {"type": "bearer", "required": bool(settings.mcp_api_key),
                 "headers": ["Authorization: Bearer <key>", "X-API-Key: <key>"]},
        "tool_count": len(tools),
        "tools": [{"name": t["name"], "description": t["description"],
                   "read_only": t["read_only"]} for t in tools],
        "function_schemas": {p: f"{url}/api/v1/developers/tools/{p}" for p in PROVIDERS},
    }


@router.get("/api/v1/developers/tools/{provider}")
async def provider_tool_schemas(provider: str):
    """Tool definitions in OpenAI / Anthropic / Gemini function-calling format."""
    if provider not in PROVIDERS:
        raise HTTPException(404, f"Unknown provider. Choose one of: {', '.join(PROVIDERS)}")
    return format_tools(provider, await tool_catalog())


@router.post("/api/v1/developers/tools/{name}/call")
async def call_tool(
    name: str,
    arguments: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    """Execute a tool by name. Lets plain function-calling integrations (no MCP client) run
    the tool calls a model emits, using the same tools as the MCP server."""
    _check_key(authorization, x_api_key)
    server = build_server()
    if name not in {t.name for t in await server.list_tools()}:
        raise HTTPException(404, f"Unknown tool: {name}")
    try:
        result = await server.call_tool(name, arguments)
    except Exception as exc:  # validation errors etc.
        raise HTTPException(422, str(exc)) from exc
    if result.is_error:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise HTTPException(400, text or "Tool call failed")
    return result.structured_content or {
        "text": " ".join(getattr(c, "text", "") for c in result.content)
    }
