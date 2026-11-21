import copy

from tests.test_studio import _proposal

from bid_studio.config import settings
from bid_studio.services import assistant as ai
from bid_studio.services import plan as planlib


def base(pid):
    return f"/api/v1/grants/proposals/{pid}/plan"


GOOD_PLAN = {
    "duration_months": 24,
    "work_packages": [
        {
            "id": "WP1", "title": "Management", "lead": "Civic Labs", "start_month": 1, "end_month": 24,
            "objectives": "Run the project.",
            "tasks": [{"id": "T1.1", "title": "Kick-off", "start_month": 1, "end_month": 3}],
            "deliverables": [{"id": "D1.1", "title": "Project handbook", "month": 3, "type": "report"}],
            "milestones": [{"id": "M1", "title": "Kick-off done", "month": 3}],
        },
        {
            "id": "WP2", "title": "Pilot", "lead": "Univ", "start_month": 4, "end_month": 20,
            "tasks": [], "deliverables": [{"id": "D2.1", "title": "Pilot report", "month": 20}], "milestones": [],
        },
    ],
    "budget": {
        "indirect_pct": 25, "indirect_base": "excl_subcontracting", "match_funding": 5000,
        "lines": [
            {"id": "B1", "wp": "WP1", "category": "personnel", "description": "PM", "quantity": 10, "unit": "person-months", "unit_cost": 4000},
            {"id": "B2", "wp": "WP2", "category": "subcontracting", "description": "Trial", "quantity": 1, "unit": "contract", "unit_cost": 20000},
            {"id": "B3", "wp": "WP2", "category": "travel", "description": "Trips", "quantity": 5, "unit": "trips", "unit_cost": 1000},
        ],
    },
    "documents": [],
}


def test_budget_math_indirect_base_match_and_variance():
    plan = planlib.Plan.model_validate(GOOD_PLAN)
    a = planlib.analyze(plan, proposal_requested=50000)
    b = a["budget"]
    assert b["direct"] == 65000 and b["by_category"]["subcontracting"] == 20000
    assert b["indirect"] == round((65000 - 20000) * 0.25, 2) == 11250
    assert b["total"] == 76250 and b["requested"] == 71250 and b["variance"] == 21250
    assert b["by_wp"] == {"WP1": 40000, "WP2": 25000}
    assert any("Budget requests 71,250.00" in c["message"] for c in a["checks"])
    plan.budget.indirect_base = "all"
    assert planlib.analyze(plan, 0)["budget"]["indirect"] == 16250


def test_consistency_checks_catch_real_mistakes():
    bad = copy.deepcopy(GOOD_PLAN)
    bad["duration_months"] = 12
    bad["work_packages"][0]["tasks"][0]["start_month"] = 2  # fine
    bad["work_packages"][0]["tasks"].append({"id": "T1.2", "title": "x", "start_month": 30, "end_month": 31})
    bad["work_packages"].append({"id": "WP1", "title": "Dup", "start_month": 5, "end_month": 3, "tasks": [], "deliverables": [], "milestones": []})
    bad["budget"]["lines"].append({"id": "B9", "wp": "WP9", "category": "other", "quantity": 1, "unit_cost": 10})
    bad["budget"]["lines"].append({"id": "B10", "wp": "", "category": "other", "quantity": 1, "unit_cost": 10})
    msgs = " | ".join(c["message"] for c in planlib.analyze(planlib.Plan.model_validate(bad), 0)["checks"])
    assert "ids must be unique" in msgs
    assert "after the 12-month project" in msgs  # WP1 ends month 24 > 12
    assert "before it starts" in msgs
    assert "task T1.2" in msgs and "outside the work package" in msgs
    assert "unknown work package 'WP9'" in msgs
    assert "B10 is not assigned" in msgs
    assert "has no deliverables" in msgs


def test_plan_api_roundtrip_and_validation(client):
    p = _proposal(client)
    pid = p["id"]
    empty = client.get(base(pid)).json()
    assert empty["plan"]["work_packages"] == [] and empty["analysis"]["budget"]["total"] == 0
    assert {t["key"] for t in empty["templates"]} == {"dmp", "ethics", "impact", "risk_register"}

    saved = client.put(base(pid), json=GOOD_PLAN)
    assert saved.status_code == 200
    assert saved.json()["analysis"]["budget"]["total"] == 76250
    assert client.get(base(pid)).json()["plan"]["work_packages"][1]["id"] == "WP2"

    bad = copy.deepcopy(GOOD_PLAN)
    bad["work_packages"][0]["start_month"] = 0
    assert client.put(base(pid), json=bad).status_code == 422
    neg = copy.deepcopy(GOOD_PLAN)
    neg["budget"]["lines"][0]["unit_cost"] = -5
    assert client.put(base(pid), json=neg).status_code == 422
    assert client.get("/api/v1/grants/proposals/9999/plan").status_code == 404


def test_documents_from_templates_and_risk_register(client):
    pid = _proposal(client)["id"]
    dmp = client.post(base(pid) + "/documents/dmp").json()
    doc = dmp["plan"]["documents"][0]
    assert doc["title"] == "Data Management Plan" and len(doc["sections"]) == 8
    assert doc["sections"][1]["id"] == "findable" and doc["sections"][1]["prompt"]
    assert client.post(base(pid) + "/documents/dmp").status_code == 409
    assert client.post(base(pid) + "/documents/nope").status_code == 404

    plan = client.get(base(pid)).json()["plan"]
    client.post(base(pid) + "/documents/risk_register")
    plan = client.get(base(pid)).json()["plan"]
    risk = next(d for d in plan["documents"] if d["key"] == "risk_register")
    risk["rows"] = [
        {"id": "R1", "description": "Partner drops out", "category": "partnership", "likelihood": 4, "impact": 5, "mitigation": "", "owner": "PM"},
        {"id": "R2", "description": "Minor delay", "category": "delivery", "likelihood": 2, "impact": 2, "mitigation": "", "owner": ""},
    ]
    res = client.put(base(pid), json=plan).json()
    assert res["analysis"]["risk"]["high"] == 1
    assert res["analysis"]["risk"]["rows"][0] == {"id": "R1", "score": 20, "band": "high"}
    assert any("Risk R1 scores 20 but has no mitigation" in c["message"] for c in res["analysis"]["checks"])
    assert not any("R2" in c["message"] for c in res["analysis"]["checks"])

    removed = client.delete(base(pid) + "/documents/dmp").json()
    assert [d["key"] for d in removed["plan"]["documents"]] == ["risk_register"]


def test_document_assistant_offline_and_claude(client, monkeypatch):
    pid = _proposal(client)["id"]
    client.post(base(pid) + "/documents/dmp")
    url = base(pid) + "/documents/dmp/assistant"
    draft = client.post(url, json={"action": "draft", "section_id": "findable"}).json()
    assert draft["provider"] == "offline" and "[TO CONFIRM" in draft["text"]
    assert "proposes to address" not in draft["text"]  # document drafts skip the criterion intro
    crit = client.post(url, json={"action": "critique", "section_id": "findable", "text": "We use DOIs."}).json()
    assert crit["suggested_score"] is None and crit["gaps"]
    assert client.post(url, json={"action": "draft", "section_id": "nope"}).status_code == 404
    assert client.post(base(pid) + "/documents/ethics/assistant", json={"action": "draft", "section_id": "ai"}).status_code == 404

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "Polished.")
    res = client.post(url, json={"action": "improve", "section_id": "accessible", "text": "Open data."}).json()
    assert res["provider"] == "claude" and res["text"] == "Polished."
    assert "Document: Data Management Plan; section: Accessible" in seen["p"]
    assert "Open data." in seen["p"]


def test_plan_in_readiness_versions_restore_and_lock(client):
    p = _proposal(client)
    pid = p["id"]
    studio = f"/api/v1/grants/proposals/{pid}/studio"
    checks = {c["id"]: c for c in client.get(studio).json()["readiness"]["checks"]}
    assert checks["plan_wp"]["ok"] is False and checks["plan_budget"]["ok"] is False
    assert checks["plan_wp"]["severity"] == "warning"  # plan gaps never block submission

    plan = copy.deepcopy(GOOD_PLAN)
    plan["budget"]["match_funding"] = 26250  # makes requested 50,000 = proposal's requested amount
    client.put(base(pid) + "", json=plan)
    client.put(f"/api/v1/grants/proposals/{pid}/studio/save",
               json={"sections": p["sections"], "meta": {"requested_amount": 50000}})
    checks = {c["id"]: c for c in client.get(studio).json()["readiness"]["checks"]}
    assert checks["plan_wp"]["ok"] and checks["plan_budget"]["ok"] and checks["plan_consistent"]["ok"]

    client.post(f"/api/v1/grants/proposals/{pid}/versions", json={"label": "With plan"})
    v = client.get(f"/api/v1/grants/proposals/{pid}/versions").json()[0]["version_no"]
    snap = client.get(f"/api/v1/grants/proposals/{pid}/versions/{v}").json()["snapshot"]
    assert snap["plan"]["work_packages"][0]["id"] == "WP1"

    client.put(base(pid), json={"duration_months": 6, "work_packages": [], "budget": {"lines": []}, "documents": []})
    assert client.get(base(pid)).json()["plan"]["work_packages"] == []
    client.post(f"/api/v1/grants/proposals/{pid}/versions/{v}/restore")
    assert len(client.get(base(pid)).json()["plan"]["work_packages"]) == 2


def test_plan_export_and_locking_after_submit(client):
    p = _proposal(client)
    pid = p["id"]
    client.put(base(pid), json=GOOD_PLAN)
    client.post(base(pid) + "/documents/risk_register")
    md = client.get(base(pid) + "/export").json()["markdown"]
    assert "### WP1: Management" in md and "| D2.1 | Pilot report | report | 20 |" in md
    assert "**Total cost:** 76,250.00" in md and "## Risk Register" in md

    secs = copy.deepcopy(p["sections"])
    for s in secs:
        s["draft_text"] = "Written text for this section with detail."
        s["self_score"] = s["max_score"]
    client.put(f"/api/v1/grants/proposals/{pid}/studio/save", json={"sections": secs})
    assert client.post(f"/api/v1/grants/proposals/{pid}/studio/submit").status_code == 200
    assert client.put(base(pid), json=GOOD_PLAN).status_code == 409
    assert client.post(base(pid) + "/documents/dmp").status_code == 409
    assert client.get(base(pid)).json()["locked"] is True
