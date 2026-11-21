import pytest
from tests.test_doc_services import create, url

from bid_studio.services import report_prefill
from bid_studio.services import service_templates as tpl

BATCH1 = ["logic_model", "evaluation_plan", "sustainability_plan", "funder_progress_report",
          "funder_final_report", "lay_summary", "safeguarding_policy", "gender_equality_plan"]
BATCH2 = ["method_statement", "mobilisation_plan", "exit_plan", "bcp_dr_plan", "rams",
          "service_description", "statement_of_work"]


@pytest.mark.parametrize("key", BATCH1 + BATCH2)
def test_each_template_is_well_formed(key):
    t = tpl.TYPES[key]
    ids = [s[0] for s in t["sections"]]
    assert t["kind"] == ("grantdoc" if key in BATCH1 else "tenderdoc")
    assert len(ids) >= 4 and len(ids) == len(set(ids))
    assert all(title and len(prompt) > 40 for _, title, prompt in t["sections"])


def test_catalogue_exposes_links_and_kinds():
    cat = {c["key"]: c for c in tpl.catalogue()}
    assert cat["funder_progress_report"]["link"] == "proposal" and cat["method_statement"]["link"] == "notice"
    assert cat["logic_model"]["link"] is None
    assert {c["kind"] for c in cat.values()} >= {"techdoc", "compliance", "bidasset", "grantdoc", "tenderdoc"}


@pytest.mark.parametrize("key", BATCH1 + BATCH2)
def test_every_new_type_can_be_created_and_exported(client, key):
    p = create(client, key)
    assert p["status"] == "drafting" and len(p["sections"]) == len(tpl.TYPES[key]["sections"])
    assert p["proposal_id"] is None and p["notice_id"] is None
    md = client.get(url(p["id"], "/export")).json()["markdown"]
    assert md.startswith("# Acme docs") and "_Not yet written._" in md


def make_proposal_with_plan(client):
    call = client.get("/api/v1/grants/calls").json()[0]
    prop = client.post("/api/v1/grants/proposals", json={
        "workspace_id": 1, "notice_id": call["id"], "applicant_org": "Civic Labs", "requested_amount": 50000,
        "currency": "GBP"}).json()
    plan = {
        "duration_months": 24,
        "work_packages": [
            {"id": "WP1", "title": "Management", "start_month": 1, "end_month": 24, "tasks": [],
             "deliverables": [{"id": "D1.1", "title": "Project handbook", "month": 3, "type": "report"}],
             "milestones": [{"id": "M1", "title": "Kick-off done", "month": 3}]},
            {"id": "WP2", "title": "Pilot", "start_month": 4, "end_month": 20, "tasks": [],
             "deliverables": [{"id": "D2.1", "title": "Pilot report", "month": 20}], "milestones": []},
        ],
        "budget": {"indirect_pct": 0, "match_funding": 0, "lines": [
            {"id": "B1", "wp": "WP1", "category": "personnel", "quantity": 10, "unit": "person-months", "unit_cost": 3000},
            {"id": "B2", "wp": "WP2", "category": "travel", "quantity": 4, "unit": "trips", "unit_cost": 5000}]},
        "documents": [],
    }
    assert client.put(f"/api/v1/grants/proposals/{prop['id']}/plan", json=plan).status_code == 200
    return prop["id"]


def test_progress_report_prefills_deliverables_budget_and_work_packages(client):
    pid = make_proposal_with_plan(client)
    p = create(client, "funder_progress_report", proposal_id=pid)
    assert p["proposal_id"] == pid
    secs = {s["id"]: s["text"] for s in p["sections"]}
    assert "| WP1 Management | D1.1 Project handbook | month 3 |" in secs["deliverables"]
    assert "Milestone M1 Kick-off done" in secs["deliverables"] and "D2.1 Pilot report" in secs["deliverables"]
    assert "| WP1 | 30,000.00 | [TO CONFIRM]" in secs["budget"] and "| WP2 | 20,000.00 |" in secs["budget"]
    assert "Total budget 50,000.00" in secs["budget"]
    assert "WP2 Pilot** (months 4-20)" in secs["progress"]
    assert "progress report" in secs["summary"] and "[TO CONFIRM" in secs["summary"]
    assert secs["risks"] == ""  # nothing to infer for these
    # placeholders block submission until a person completes them
    ready = p["readiness"]
    assert ready["ready"] is False and "Contains [TO CONFIRM] placeholders" in ready["blockers"]

    final = create(client, "funder_final_report", proposal_id=pid)
    assert "final report" in {s["id"]: s["text"] for s in final["sections"]}["summary"]


def test_progress_report_without_a_plan_still_creates_with_summary_only(client):
    call = client.get("/api/v1/grants/calls").json()[0]
    prop = client.post("/api/v1/grants/proposals", json={"workspace_id": 1, "notice_id": call["id"], "applicant_org": "O", "requested_amount": 1}).json()
    p = create(client, "funder_progress_report", proposal_id=prop["id"])
    secs = {s["id"]: s["text"] for s in p["sections"]}
    assert "progress report" in secs["summary"] and secs["deliverables"] == "" and secs["budget"] == ""


def test_method_statement_prefills_tender_criteria(client):
    tender = next(n for n in client.get("/api/v1/notices?workspace_id=1&notice_type=tender&limit=100").json() if n["structured_criteria"])
    p = create(client, "method_statement", notice_id=tender["id"])
    text = {s["id"]: s["text"] for s in p["sections"]}["criteria_map"]
    for c in tender["structured_criteria"]:
        assert f"**{c['title']}** ({c['weight']}%)" in text
    bare = client.post("/api/v1/notices", json={"notice_type": "tender", "funder_or_buyer": "X", "title": "No criteria tender", "sector": "S"}).json()
    assert {s["id"]: s["text"] for s in create(client, "method_statement", notice_id=bare["id"])["sections"]}["criteria_map"] == ""


def test_link_validation(client):
    pid = make_proposal_with_plan(client)
    tender = client.get("/api/v1/notices?workspace_id=1&notice_type=tender&limit=1").json()[0]
    post = lambda **kw: client.post("/api/v1/services/projects", json={"workspace_id": 1, "title": "Linked doc", **kw})  # noqa: E731
    assert post(doc_type="logic_model", proposal_id=pid).status_code == 422  # not linkable
    assert post(doc_type="funder_progress_report", notice_id=tender["id"]).status_code == 422  # wrong link kind
    assert post(doc_type="method_statement", proposal_id=pid).status_code == 422
    assert post(doc_type="funder_progress_report", proposal_id=9999).status_code == 404
    assert post(doc_type="method_statement", notice_id=9999).status_code == 404
    private = client.post("/api/v1/notices", json={"workspace_id": 2, "notice_type": "tender", "funder_or_buyer": "Z", "title": "Private tender", "sector": "S"}).json()
    assert post(doc_type="method_statement", notice_id=private["id"]).status_code == 404  # another workspace's
    assert post(doc_type="funder_progress_report", proposal_id=pid).status_code == 201


def test_prefill_helpers_are_pure_and_safe():
    class N:
        structured_criteria = [{"title": "Quality", "weight": 60}, {"title": "Price"}]

    out = report_prefill.method_statement(N())["criteria_map"]
    assert "**Quality** (60%)" in out and "**Price** (?%)" in out


def test_new_job_types_link_only_matching_kinds(client):
    from tests.test_marketplace import job_ws, new_client, register

    c = new_client(client)
    register(c, "mix@clients.test", "client", "Mia", "Mia Org")
    ws = job_ws({"client": c})
    mk = lambda t: client.post("/api/v1/services/projects", json={"workspace_id": ws, "doc_type": t, "title": "Doc for job"}).json()["id"]  # noqa: E731
    report, method, sop = mk("funder_final_report"), mk("method_statement"), mk("sop")
    post = lambda **kw: c.post("/api/v1/market/jobs", json={"title": "Write this please", **kw})  # noqa: E731
    assert post(job_type="grant_documents", doc_project_id=report).status_code == 201
    assert post(job_type="tender_documents", doc_project_id=method).status_code == 201
    assert post(job_type="grant_documents", doc_project_id=method).status_code == 422
    assert post(job_type="tender_documents", doc_project_id=sop).status_code == 422
    labels = {t["key"]: t["label"] for t in c.get("/api/v1/market/job-types").json()}
    assert labels["grant_documents"].startswith("Grant supporting") and labels["tender_documents"].startswith("Tender technical")
