import httpx
import pytest
from tests.test_studio import _proposal

from bid_studio.config import settings
from bid_studio.services import assistant as ai


def _ask(client, pid, **body):
    return client.post(f"/api/v1/grants/proposals/{pid}/assistant", json=body)


def test_status_reports_offline_without_key(client):
    p = _proposal(client)
    st = client.get(f"/api/v1/grants/proposals/{p['id']}/assistant/status").json()
    assert st == {"provider": "offline", "model": ""}
    assert client.get("/api/v1/grants/proposals/9999/assistant/status").status_code == 404


def test_offline_draft_is_scaffold_with_placeholders(client):
    p = _proposal(client)
    res = _ask(client, p["id"], action="draft", section_index=0).json()
    assert res["provider"] == "offline"
    assert "[TO CONFIRM" in res["text"] and "Civic Labs" in res["text"]
    assert any("API key" in n for n in res["notes"])


def test_offline_improve_cleans_filler_and_uses_unsaved_text(client):
    p = _proposal(client)
    res = _ask(
        client,
        p["id"],
        action="improve",
        text="we will utilize funds in order to deliver a very strong programme to 300 families.",
    ).json()
    assert res["text"].startswith("We will use funds to deliver a strong programme")
    assert "filler" in res["notes"][0]


def test_offline_shorten_respects_word_limit_and_keeps_numbers(client):
    p = _proposal(client)
    text = (
        "Our team has worked in many places over many years. "
        "We will reduce emissions by 40% across 12 sites by 2027. "
        "We enjoy collaboration and good communication throughout. "
        "Partners include the city council and two universities."
    )
    res = _ask(client, p["id"], action="shorten", text=text, word_limit=14).json()
    assert len(res["text"].split()) <= 14
    assert "40%" in res["text"]


def test_offline_critique_scores_coverage_and_lists_gaps(client):
    p = _proposal(client)
    empty = _ask(client, p["id"], action="critique", text="").json()
    assert empty["suggested_score"] == 0.0 and empty["gaps"]
    strong = _ask(
        client,
        p["id"],
        action="critique",
        text="Impact will reach 500 households by 2027 with measured outcomes. " * 15,
    ).json()
    assert strong["suggested_score"] > empty["suggested_score"]
    assert any("evidence" in g.lower() for g in strong["gaps"])
    assert strong["provider"] == "offline"


def test_ask_offline_explains_it_needs_a_key_and_validates(client):
    p = _proposal(client)
    res = _ask(client, p["id"], action="ask", instruction="Why is this weak?").json()
    assert "ANTHROPIC_API_KEY" in res["text"]
    assert _ask(client, p["id"], action="ask", instruction="  ").status_code == 422
    assert _ask(client, p["id"], action="nope").status_code == 422
    assert _ask(client, p["id"], action="draft", section_index=99).status_code == 422


def test_claude_path_builds_grounded_prompt_and_returns_text(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return "A polished answer."

    monkeypatch.setattr(ai, "call_claude", fake)
    p = _proposal(client)
    pid = p["id"]
    assert client.get(f"/api/v1/grants/proposals/{pid}/assistant/status").json()["provider"] == "claude"
    res = _ask(client, pid, action="improve", text="Draft text here", instruction="Be concrete").json()
    assert res == {
        "text": "A polished answer.", "provider": "claude", "model": settings.assistant_model,
        "suggested_score": None, "strengths": [], "gaps": [], "notes": [],
    }
    prompt = seen["prompt"]
    assert "Draft text here" in prompt and "Be concrete" in prompt
    assert "Civic Labs" in prompt and "Studio Test Fund" in prompt


def test_claude_critique_json_is_parsed_and_clamped(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(
        ai,
        "call_claude",
        lambda prompt: 'Sure: {"suggested_score": 99, "strengths": ["Clear"], "gaps": ["No KPIs"], "summary": "Decent."}',
    )
    p = _proposal(client)
    res = _ask(client, p["id"], action="critique", text="x").json()
    max_score = p["sections"][0]["max_score"]
    assert res["suggested_score"] == max_score
    assert res["strengths"] == ["Clear"] and res["gaps"] == ["No KPIs"] and res["text"] == "Decent."

    monkeypatch.setattr(ai, "call_claude", lambda prompt: "not json at all")
    plain = _ask(client, p["id"], action="critique", text="x").json()
    assert plain["suggested_score"] is None and plain["text"] == "not json at all"


@pytest.mark.parametrize(
    "exc,code,msg",
    [
        (
            httpx.HTTPStatusError(
                "bad", request=httpx.Request("POST", "http://x"), response=httpx.Response(401)
            ),
            502,
            "HTTP 401",
        ),
        (httpx.ConnectError("down"), 502, "Could not reach"),
    ],
)
def test_provider_failures_become_502(client, monkeypatch, exc, code, msg):
    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    def boom(prompt):
        raise exc

    monkeypatch.setattr(ai, "call_claude", boom)
    p = _proposal(client)
    res = _ask(client, p["id"], action="draft")
    assert res.status_code == code and msg in res.json()["detail"]


def test_call_claude_sends_expected_request(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "secret-key")
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json)
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert ai.call_claude("prompt") == "Hello world"
    assert captured["url"] == ai.ANTHROPIC_URL
    assert captured["headers"]["x-api-key"] == "secret-key"
    assert captured["json"]["messages"] == [{"role": "user", "content": "prompt"}]
    assert captured["json"]["system"] == ai.SYSTEM_PROMPT


def test_weakly_related_library_items_are_not_used_as_material(client):
    p = _proposal(client)
    res = _ask(client, p["id"], action="draft", section_index=0).json()
    assert "penetration" not in res["text"].lower()
