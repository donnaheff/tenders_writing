import pytest
from tests.test_doc_services import create, url

from bid_studio.config import settings
from bid_studio.services import assistant as ai
from bid_studio.services import service_templates as tpl
from bid_studio.services import ux_copy

ENDUSER = ["kb_article", "kb_troubleshooting", "tutorial", "onboarding_guide", "training_module"]
EXPERT = ["technical_specification", "technical_report", "architecture_doc"]


@pytest.mark.parametrize("key", ENDUSER + EXPERT + ["white_paper", "faq", "ux_copy"])
def test_templates_are_well_formed(key):
    t = tpl.TYPES[key]
    ids = [s[0] for s in t["sections"]]
    assert t["kind"] == ("enduser" if key in ENDUSER + ["faq", "ux_copy"] else "expert" if key in EXPERT else "marketing")
    assert len(ids) == len(set(ids)) and all(title and len(prompt) > 40 for _, title, prompt in t["sections"])
    if key not in ("faq",):
        assert ids  # everything except the FAQ set has sections


@pytest.mark.parametrize("key", ENDUSER + EXPERT + ["white_paper"])
def test_section_documents_create_and_export(client, key):
    p = create(client, key)
    assert p["status"] == "drafting" and not p["questionnaire"] and not p["copydeck"]
    assert len(p["sections"]) == len(tpl.TYPES[key]["sections"])
    assert "_Not yet written._" in client.get(url(p["id"], "/export")).json()["markdown"]


def test_catalogue_flags_item_based_types():
    cat = {c["key"]: c for c in tpl.catalogue()}
    assert cat["faq"]["questionnaire"] and cat["security_questionnaire"]["questionnaire"]
    assert cat["ux_copy"]["copydeck"] and not cat["ux_copy"]["questionnaire"]
    assert not cat["kb_article"]["questionnaire"] and not cat["kb_article"]["copydeck"]


def test_white_paper_prompts_demand_sources():
    prompts = " ".join(p for _, _, p in tpl.TYPES["white_paper"]["sections"]).lower()
    assert "cite" in prompts and "source" in prompts


# ---------------------------------------------------------------- FAQ

def test_faq_is_a_question_set_matched_to_the_library(client):
    p = create(client, "faq", questions="How is data encrypted at rest and in transit?\nWhere can I find my invoices?")
    assert p["questionnaire"] and p["stats"]["total"] == 2
    enc, inv = p["items"]
    assert enc["status"] in ("matched", "needs_review") and "AES-256" in enc["answer"]
    assert inv["status"] == "unanswered"
    assert client.post("/api/v1/services/projects", json={"workspace_id": 1, "doc_type": "faq", "title": "Empty FAQ"}).status_code == 422
    inv.update(answer="Open Billing, then choose Invoices.", status="approved")
    saved = client.put(url(p["id"]), json={"items": [enc, inv]}).json()
    assert saved["stats"]["approved"] == 1
    md = client.get(url(p["id"], "/export")).json()["markdown"]
    assert "Where can I find my invoices?" in md and "Open Billing" in md


def test_faq_assistant_uses_faq_guidance(client, monkeypatch):
    p = create(client, "faq", questions="Can I export my data?")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "Yes.")
    client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": p["items"][0]["id"]})
    assert "Answer this user question directly" in seen["p"] and "security question" not in seen["p"]


# ---------------------------------------------------------------- UX copy

def test_parse_strings_formats_and_defaults():
    items = ux_copy.parse_strings("Login | Button | Sign in\nSettings | error | We could not save. Try again.\nJust some copy\n\nHome | weird type | Hello | with pipe\nTwo | parts")
    assert [(i["screen"], i["element"]) for i in items] == [("Login", "button"), ("Settings", "error"), ("", "label"), ("Home", "label"), ("", "label")]
    assert items[3]["text"] == "Hello | with pipe" and items[4]["text"] == "Two | parts"
    items = ux_copy.assign_ids([{"id": "S1"}, {"id": "S3"}], items)
    assert [i["id"] for i in items] == ["S4", "S5", "S6", "S7", "S8"]


def test_lint_rules():
    rules = [("Sign in", "Log in")]
    lint = lambda element, text, **kw: ux_copy.lint_item({**ux_copy.new_item("S1", "x", element, text), **kw}, rules)  # noqa: E731
    assert lint("button", "Save changes") == []
    assert any("one to four words" in n for n in lint("button", "Click here to save all of your changes now"))
    assert any("end punctuation" in n for n in lint("button", "Save."))
    assert any("vague" in n for n in lint("error", "Oops! Something went wrong."))
    assert any("exclamation" in n for n in lint("error", "Payment failed! Check your card."))
    assert any("next step" in n for n in lint("error", "Your card number is invalid for this payment."))
    assert lint("error", "Your card was declined. Check the number or try another card.") == []
    assert any("Too short" in n for n in lint("error", "Invalid"))
    assert any("limit is 10" in n for n in lint("label", "A very long label", max_chars=10))
    assert any("ALL CAPS" in n for n in lint("label", "SAVE YOUR WORK NOW"))
    assert any("Log in" in n and "Sign in" in n for n in lint("button", "Log in"))
    assert lint("label", "") == []
    assert any("empty" in n.lower() or "belongs" in n for n in lint("empty_state", "Nothing here"))


def test_terminology_rules_parse_the_style_guide():
    secs = [{"id": "terminology", "text": 'Use "Sign in", not "Log in"\nUse “workspace” rather than “account”\nnoise'}]
    assert ux_copy.terminology_rules(secs) == [("Sign in", "Log in"), ("workspace", "account")]
    assert ux_copy.terminology_rules([]) == []


def make_deck(client, **kw):
    return create(client, "ux_copy", questions="Login | button | Sign in\nLogin | error | Oops! Something went wrong.\nSettings | label | Account name", **kw)


def test_copy_deck_creates_strings_and_flags_problems(client):
    p = make_deck(client)
    assert p["copydeck"] and not p["questionnaire"] and [i["id"] for i in p["items"]] == ["S1", "S2", "S3"]
    assert [s["id"] for s in p["sections"]] == ["voice", "terminology", "rules"]
    assert "Buttons" in p["element_rules"]["button"] or p["element_rules"]["button"]
    assert set(p["lint"]) == {"S2"} and p["stats"]["flagged"] == 1 and p["stats"]["strings"] == 3

    secs = p["sections"]
    secs[1]["text"] = 'Use "workspace", not "account"'
    saved = client.put(url(p["id"]), json={"sections": secs}).json()
    assert set(saved["lint"]) == {"S2", "S3"}  # "Account name" now breaks the terminology rule
    assert any('Uses "account"' in w for w in saved["lint"]["S3"])


def test_copy_deck_save_validates_items_and_readiness_gates_submission(client):
    p = make_deck(client)
    pid = p["id"]
    r = p["readiness"]
    assert r["ready"] is True and any("style warnings" in w for w in r["warnings"])  # warnings do not block

    items = p["items"]
    items[0]["max_chars"] = 3
    over = client.put(url(pid), json={"items": items}).json()["readiness"]
    assert over["ready"] is False and "Over the character limit: S1" in over["blockers"]
    items[0]["max_chars"] = None
    items[2]["text"] = ""
    empty = client.put(url(pid), json={"items": items}).json()["readiness"]
    assert "Empty copy: S3" in empty["blockers"]

    bad_element = [{**items[0], "element": "nonsense"}]
    assert client.put(url(pid), json={"items": bad_element}).status_code == 422
    bad_status = [{**items[0], "status": "matched"}]
    assert client.put(url(pid), json={"items": bad_status}).status_code == 422
    assert client.put(url(pid), json={"items": [{"id": "S1", "bogus": 1, "text": "x" * 600}]}).status_code == 422

    none = create(client, "ux_copy")
    assert none["readiness"]["blockers"] == ["No strings yet"]
    kb = create(client, "kb_article")
    assert client.put(url(kb["id"]), json={"items": []}).status_code == 422  # not an item-based type


def test_bulk_add_strings_and_limits(client):
    p = make_deck(client)
    more = client.post(url(p["id"], "/strings"), json={"text": "Cart | confirmation | Delete this item?\nCart | button | Remove"}).json()
    assert [i["id"] for i in more["items"]][-2:] == ["S4", "S5"] and more["items"][3]["element"] == "confirmation"
    assert client.post(url(p["id"], "/strings"), json={"text": "  \n \n"}).status_code == 422
    assert client.post(url(create(client, "sop")["id"], "/strings"), json={"text": "a | label | b"}).status_code == 409
    assert client.post(url(p["id"], "/questions"), json={"questions": "Why?"}).status_code == 409


def test_copy_deck_export_and_assistant(client, monkeypatch):
    p = make_deck(client)
    md = client.get(url(p["id"], "/export")).json()["markdown"]
    assert "## Copy deck" in md and "| S1 | Login | button | Sign in | 7 | draft |" in md and "## Voice and tone" in md

    offline = client.post(url(p["id"], "/assistant"), json={"action": "improve", "target_id": "S2"}).json()
    assert offline["provider"] == "offline"

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "We could not sign you in. Check your password and try again.")
    items = p["items"]
    items[1].update(notes="Shown after three failed attempts", max_chars=80)
    client.put(url(p["id"]), json={"items": items})
    res = client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "S2"}).json()
    assert res["provider"] == "claude" and res["text"].startswith("We could not sign you in")
    for must in ("Maximum 80 characters", "Say what happened", "Shown after three failed attempts", "Login: error"):
        assert must in seen["p"], must
    assert client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "S99"}).status_code == 404


def test_new_job_types_match_their_document_kinds(client):
    from tests.test_marketplace import job_ws, new_client, register

    c = new_client(client)
    register(c, "docs@clients.test", "client", "Dee", "Dee Docs")
    ws = job_ws({"client": c})
    mk = lambda t: client.post("/api/v1/services/projects", json={"workspace_id": ws, "doc_type": t, "title": "Doc for job"}).json()["id"]  # noqa: E731
    kb, spec, wp, sop = mk("kb_article"), mk("technical_specification"), mk("white_paper"), mk("sop")
    post = lambda **kw: c.post("/api/v1/market/jobs", json={"title": "Write this please", **kw})  # noqa: E731
    assert post(job_type="end_user_docs", doc_project_id=kb).status_code == 201
    assert post(job_type="expert_docs", doc_project_id=spec).status_code == 201
    assert post(job_type="technical_marketing", doc_project_id=wp).status_code == 201
    assert post(job_type="end_user_docs", doc_project_id=spec).status_code == 422
    assert post(job_type="expert_docs", doc_project_id=sop).status_code == 422
