import json

import pytest

from bid_studio.developers import PROVIDERS

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, id_=1, headers=None):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers={**MCP_HEADERS, **(headers or {})})


def test_mcp_lists_tools(client):
    r = rpc(client, "tools/list")
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"search_opportunities", "create_grant_proposal", "list_workspaces"} <= names
    # human-gated actions must never be exposed to an AI client
    assert not any("approve" in n or "deliver" in n or "review_quality" in n for n in names)


def test_mcp_tool_call_hits_real_data(client):
    r = rpc(client, "tools/call", {"name": "list_workspaces", "arguments": {}})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError")
    assert len(result["structuredContent"]["items"]) >= 1


def test_mcp_search_returns_total_count_and_omits_pack_text(client):
    r = rpc(client, "tools/call", {"name": "search_opportunities", "arguments": {"limit": 2}})
    data = r.json()["result"]["structuredContent"]
    assert data["total_count"] >= len(data["items"]) >= 1
    assert all("raw_pack_text" not in i for i in data["items"])


def test_mcp_tool_error_is_reported(client):
    r = rpc(client, "tools/call", {"name": "extract_grant_criteria", "arguments": {"notice_id": 999999}})
    assert r.json()["result"]["isError"] is True


def test_mcp_requires_key_when_configured(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from bid_studio.config import settings
    from bid_studio.main import create_app

    monkeypatch.setattr(settings, "mcp_api_key", "s3cret")
    monkeypatch.setattr(settings, "seed_on_startup", False)
    with TestClient(create_app()) as c:
        assert rpc(c, "tools/list").status_code == 401
        assert rpc(c, "tools/list", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert rpc(c, "tools/list", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert rpc(c, "tools/list", headers={"X-API-Key": "s3cret"}).status_code == 200
        # executor endpoint is guarded too
        assert c.post("/api/v1/developers/tools/list_workspaces/call", json={}).status_code == 401


def test_developers_page(client):
    r = client.get("/developers")
    assert r.status_code == 200
    for needle in ("Claude Code", "OpenAI Responses API", "Gemini CLI", "search_opportunities",
                   "mcp_toolset", "/mcp"):
        assert needle in r.text


def test_dashboard_still_served_after_mount(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_server_card(client):
    card = client.get("/api/v1/developers/mcp").json()
    assert card["tool_count"] == len(card["tools"]) >= 15
    assert set(card["function_schemas"]) == set(PROVIDERS)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_schemas(client, provider):
    data = client.get(f"/api/v1/developers/tools/{provider}").json()
    assert len(data) >= 15 if provider != "gemini" else len(data[0]["function_declarations"]) >= 15
    first = data[0] if provider != "gemini" else data[0]["function_declarations"][0]
    flat = json.dumps(first)
    assert "search_opportunities" in json.dumps(data) and "properties" in json.dumps(data)
    if provider == "anthropic":
        assert "input_schema" in first
    if provider == "openai":
        assert first["type"] == "function" and "parameters" in first
    if provider == "openai-chat":
        assert "function" in first
    assert flat


def test_unknown_provider_404(client):
    assert client.get("/api/v1/developers/tools/nope").status_code == 404


def test_tool_executor(client):
    r = client.post("/api/v1/developers/tools/get_workspace_summary/call", json={"workspace_id": 1})
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/developers/tools/nope/call", json={}).status_code == 404
    assert client.post("/api/v1/developers/tools/get_workspace_summary/call", json={}).status_code == 422


def test_dashboard_links_to_developers(client):
    assert 'href="/developers"' in client.get("/").text
