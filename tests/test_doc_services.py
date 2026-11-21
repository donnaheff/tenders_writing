from bid_studio.config import settings
from bid_studio.services import assistant as ai
from bid_studio.services import questionnaire as qn
from bid_studio.services import service_templates as tpl

QUESTIONS = """1. Do you hold ISO 27001 certification?
- How is data encrypted at rest and in transit?
* What is your incident response SLA and penetration testing cadence?
Do you have a dedicated unicorn wrangler on staff?
Do you hold ISO 27001 certification?
"""


def create(client, doc_type="user_guide", **extra):
    body = {"workspace_id": 1, "doc_type": doc_type, "title": "Acme docs", "client_name": "Acme Ltd",
            "client_email": "docs@acme.test", "fixed_fee": 1200, **extra}
    res = client.post("/api/v1/services/projects", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def url(pid, tail=""):
    return f"/api/v1/services/projects/{pid}{tail}"


def test_templates_cover_techdoc_and_compliance():
    kinds = {k: v["kind"] for k, v in tpl.TYPES.items()}
    assert {"user_guide", "api_reference", "sop", "release_notes"} <= {k for k, v in kinds.items() if v == "techdoc"}
    assert {"infosec_policy", "data_protection_policy", "incident_response_plan", "quality_manual",
            "security_questionnaire"} <= {k for k, v in kinds.items() if v == "compliance"}
    for key, t in tpl.TYPES.items():
        ids = [s[0] for s in t["sections"]]
        assert len(ids) == len(set(ids)) and all(s[2] for s in t["sections"]), key


def test_parse_questions_cleans_numbering_blanks_and_duplicates():
    qs = qn.parse_questions(QUESTIONS)
    assert len(qs) == 4 and qs[0] == "Do you hold ISO 27001 certification?"
    assert qn.parse_questions("\n  \n- \n") == []


def test_create_techdoc_project_instantiates_sections(client):
    p = create(client, "api_reference", brief="REST API for payments")
    assert p["kind"] == "techdoc" and p["status"] == "drafting" and not p["questionnaire"]
    assert [s["id"] for s in p["sections"]][:3] == ["intro", "auth", "quickstart"]
    assert p["stats"] == {"written": 0, "total": 7, "words": 0}
    listed = client.get("/api/v1/services/projects?workspace_id=1").json()
    assert [x["id"] for x in listed] == [p["id"]]
    assert client.get("/api/v1/services/projects?workspace_id=1&kind=compliance").json() == []
    assert client.get("/api/v1/services/templates").json()[0]["key"] == "user_guide"


def test_create_validation(client):
    bad = lambda **kw: client.post("/api/v1/services/projects", json={"doc_type": "sop", "title": "Valid title", **kw})  # noqa: E731
    assert bad(doc_type="nope").status_code == 422
    assert bad(title="x").status_code == 422
    assert bad(client_email="not-an-email").status_code == 422
    assert bad(workspace_id=999).status_code == 404
    assert client.post("/api/v1/services/projects", json={"doc_type": "security_questionnaire", "title": "Sec Qs"}).status_code == 422


def test_questionnaire_auto_matches_library_and_never_overwrites_approved(client):
    p = create(client, "security_questionnaire", title="Acme security review", questions=QUESTIONS)
    assert p["questionnaire"] and p["stats"]["total"] == 4
    by_q = {i["question"]: i for i in p["items"]}
    iso = by_q["Do you hold ISO 27001 certification?"]
    assert iso["status"] in ("matched", "needs_review") and "ISO/IEC 27001" in iso["answer"]
    assert iso["source_answer_id"] and 0 < iso["confidence"] <= 1
    enc = by_q["How is data encrypted at rest and in transit?"]
    assert "AES-256" in enc["answer"]
    unicorn = by_q["Do you have a dedicated unicorn wrangler on staff?"]
    assert unicorn["status"] == "unanswered" and unicorn["answer"] == ""

    items = p["items"]
    items[0]["status"] = "approved"
    items[0]["answer"] = "Hand-written approved answer."
    items[3]["answer"] = "We do not employ one."  # a hand-written answer with no library source
    saved = client.put(url(p["id"]), json={"items": items}).json()
    again = client.post(url(p["id"], "/auto-match")).json()
    final = {i["id"]: i for i in again["project"]["items"]}
    assert final[items[0]["id"]]["answer"] == "Hand-written approved answer."
    assert final[items[3]["id"]]["answer"] == "We do not employ one."
    assert saved["stats"]["approved"] == 1

    more = client.post(url(p["id"], "/questions"), json={"questions": "Do you hold ISO 27001 certification?\nWhere is data hosted?"}).json()
    assert len(more["items"]) == 5 and more["items"][-1]["id"] == "Q5"  # the duplicate was skipped


def test_promote_only_approved_answers_to_library(client):
    p = create(client, "security_questionnaire", questions="Do you run a bug bounty programme?")
    item = p["items"][0]
    assert client.post(url(p["id"], "/promote-answer"), json={"item_id": item["id"]}).status_code == 409
    item.update(answer="Yes, via a private programme.", status="approved")
    client.put(url(p["id"]), json={"items": [item]})
    assert client.post(url(p["id"], "/promote-answer"), json={"item_id": item["id"]}).status_code == 201
    lib = client.get("/api/v1/answer-library?workspace_id=1").json()
    assert any("bug bounty" in a["question_pattern"] for a in lib)
    assert client.post(url(p["id"], "/promote-answer"), json={"item_id": "Q99"}).status_code == 404


def test_save_sections_validates_and_readiness_gates_submission(client):
    p = create(client, "sop", client_email="")
    pid = p["id"]
    r = p["readiness"]
    assert r["ready"] is False and "Not yet written" in r["blockers"][0]
    assert any("No client email" in w for w in r["warnings"])
    blocked = client.post(url(pid, "/submit-quality"))
    assert blocked.status_code == 422 and blocked.json()["detail"]["blockers"]

    secs = p["sections"]
    assert client.put(url(pid), json={"sections": secs[:-1]}).status_code == 422
    for s in secs:
        s["text"] = "Written content for this section."
    secs[1]["text"] = "Roles. [TO CONFIRM: approver]"
    saved = client.put(url(pid), json={"sections": secs}).json()
    assert saved["readiness"]["blockers"] == ["Contains [TO CONFIRM] placeholders"]
    secs[1]["text"] = "Roles are assigned."
    ok = client.put(url(pid), json={"sections": secs, "client_email": "ops@acme.test", "fixed_fee": 900}).json()
    assert ok["readiness"]["ready"] and ok["fixed_fee"] == 900


def test_quality_gate_delivery_and_changes_requested_flow(client):
    p = create(client, "release_notes")
    pid = p["id"]
    secs = p["sections"]
    for s in secs:
        s["text"] = "Done."
    client.put(url(pid), json={"sections": secs})
    sub = client.post(url(pid, "/submit-quality")).json()
    assert sub["status"] == "quality_review"
    assert client.put(url(pid), json={"title": "Changed"}).status_code == 409
    assert client.post(url(pid, "/submit-quality")).status_code == 409
    assert client.post(url(pid, "/deliver")).status_code == 409  # not approved yet

    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    item = next(q for q in queue if q["item_type"] == "doc_project" and q["reference_id"] == pid)
    client.post(f"/api/v1/quality-queue/{item['id']}/review",
                json={"assigned_reviewer": "QA", "status": "changes_requested", "review_notes": "Expand fixes"})
    back = client.get(url(pid)).json()
    assert back["status"] == "drafting" and back["reviewer_notes"] == "Expand fixes"
    assert client.put(url(pid), json={"title": "Release notes v2"}).status_code == 200

    client.post(url(pid, "/submit-quality"))
    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    item = max((q for q in queue if q["reference_id"] == pid and q["item_type"] == "doc_project"), key=lambda q: q["id"])
    client.post(f"/api/v1/quality-queue/{item['id']}/review",
                json={"assigned_reviewer": "QA", "status": "approved", "review_notes": "Good"})
    assert client.get(url(pid)).json()["status"] == "approved"

    done = client.post(url(pid, "/deliver")).json()
    assert done["status"] == "delivered" and done["emailed"] is True and done["delivered_at"]
    mail = [d for d in client.get("/api/v1/deliveries?workspace_id=1").json() if d["delivery_type"] == "doc_delivery"]
    assert mail and mail[0]["recipient_email"] == "docs@acme.test" and "Release notes v2" in mail[0]["body_preview"]
    assert client.post(url(pid, "/deliver")).status_code == 409
    stats = client.get("/api/v1/services/stats?workspace_id=1").json()
    assert stats["by_status"]["delivered"] == 1 and stats["fees_delivered"] == 1200


def test_export_markdown_for_documents_and_questionnaires(client):
    p = create(client, "user_guide")
    secs = p["sections"]
    secs[0]["text"] = "Welcome to Acme."
    client.put(url(p["id"]), json={"sections": secs})
    md = client.get(url(p["id"], "/export")).json()["markdown"]
    assert md.startswith("# Acme docs") and "_Prepared for Acme Ltd_" in md
    assert "## Overview and audience\n\nWelcome to Acme." in md and "_Not yet written._" in md

    q = create(client, "security_questionnaire", questions="Do you hold ISO 27001 certification?")
    table = client.get(url(q["id"], "/export")).json()["markdown"]
    assert "| Q1 | Do you hold ISO 27001 certification? |" in table and "ISO/IEC 27001" in table


def test_assistant_offline_and_claude_for_sections_and_questions(client, monkeypatch):
    p = create(client, "infosec_policy")
    draft = client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "access"}).json()
    assert draft["provider"] == "offline" and "[TO CONFIRM" in draft["text"]
    assert client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "zzz"}).status_code == 404

    q = create(client, "security_questionnaire", questions="Do you use multi-factor authentication for admins?")
    qid = q["items"][0]["id"]
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "Yes, for all admin accounts.")
    res = client.post(url(q["id"], "/assistant"), json={"action": "draft", "target_id": qid}).json()
    assert res["provider"] == "claude" and res["text"] == "Yes, for all admin accounts."
    assert "multi-factor authentication" in seen["p"] and "Never invent" not in seen["p"]
    assert client.post(url(q["id"], "/assistant"), json={"action": "draft", "target_id": "Q9"}).status_code == 404


def test_missing_project_404s(client):
    for method, tail in (("get", ""), ("get", "/export"), ("post", "/deliver"), ("post", "/submit-quality")):
        assert getattr(client, method)(url(999, tail)).status_code == 404


def test_editor_page_status_and_dashboard_tab(client):
    p = create(client, "user_guide")
    page = client.get(f"/app/docs/{p['id']}")
    assert page.status_code == 200 and "Documentation project" in page.text
    assert client.get("/app/docs/9999").status_code == 404
    assert client.get("/api/v1/services/assistant-status").json()["provider"] == "offline"
    assert "dsInit" in client.get("/app").text
