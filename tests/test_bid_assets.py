from tests.test_doc_services import create, url

from bid_studio.services import service_templates as tpl


def finish(client, pid, texts=None):
    """Write every section, then take the project through QA to approved."""
    secs = client.get(url(pid)).json()["sections"]
    for s in secs:
        s["text"] = (texts or {}).get(s["id"], f"Written content for {s['title']}.")
    client.put(url(pid), json={"sections": secs})
    assert client.post(url(pid, "/submit-quality")).status_code == 200
    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    item = max((q for q in queue if q["item_type"] == "doc_project" and q["reference_id"] == pid), key=lambda q: q["id"])
    client.post(f"/api/v1/quality-queue/{item['id']}/review",
                json={"assigned_reviewer": "QA", "status": "approved", "review_notes": "ok"})


def test_templates_exist_with_unique_ids_and_valid_promotion_config():
    for key in ("team_cv", "capability_statement", "case_study"):
        t = tpl.TYPES[key]
        ids = [s[0] for s in t["sections"]]
        assert t["kind"] == "bidasset" and len(ids) == len(set(ids)) and all(s[2] for s in t["sections"])
        assert t["evidence_type"] and set(t["summary_sections"]) <= set(ids)
    assert "metrics" in [s[0] for s in tpl.TYPES["case_study"]["sections"]]
    cat = {c["key"]: c for c in tpl.catalogue()}
    assert cat["case_study"]["promotable"] and not cat["sop"]["promotable"]


def test_parse_metrics_handles_bullets_blanks_and_noise():
    text = "Mileage reduction: 24%\n- Collection SLA: 99.4%\n\n* No colon here\nTrailing:\n: no label\nCO2 saved: 310 tonnes: per year"
    assert tpl.parse_metrics(text) == {"Mileage reduction": "24%", "Collection SLA": "99.4%", "CO2 saved": "310 tonnes: per year"}
    assert len(tpl.parse_metrics("\n".join(f"m{i}: {i}" for i in range(40)))) == 12


def test_case_study_flow_creates_evidence_with_summary_and_metrics(client):
    p = create(client, "case_study", title="Camden fleet routing rollout", client_name="Camden Council")
    pid = p["id"]
    assert p["promotable"] is True and p["can_promote"] is False and p["evidence_item_id"] is None
    early = client.post(url(pid, "/promote-evidence"))
    assert early.status_code == 409 and "quality-approved" in early.json()["detail"]

    finish(client, pid, {
        "challenge": "Routes were inefficient across 42 depots.",
        "results": "Mileage fell and collections became reliable.",
        "metrics": "Mileage reduction: 24%\nCollection SLA: 99.4%",
    })
    assert client.get(url(pid)).json()["can_promote"] is True
    res = client.post(url(pid, "/promote-evidence"))
    assert res.status_code == 201
    assert res.json()["metrics"] == {"Mileage reduction": "24%", "Collection SLA": "99.4%"}

    evidence = client.get("/api/v1/evidence-library?workspace_id=1").json()
    item = next(e for e in evidence if e["id"] == res.json()["evidence_item_id"])
    assert item["evidence_type"] == "case_study" and item["title"] == "Camden fleet routing rollout"
    assert item["buyer_format"] == "Camden Council"
    assert item["summary"].startswith("Routes were inefficient") and "Mileage fell" in item["summary"]
    assert item["metrics"]["Collection SLA"] == "99.4%"

    again = client.post(url(pid, "/promote-evidence"))
    assert again.status_code == 409 and "Already in the evidence library" in again.json()["detail"]
    done = client.get(url(pid)).json()
    assert done["evidence_item_id"] == item["id"] and done["can_promote"] is False


def test_promoted_evidence_is_offered_in_the_grant_studio(client):
    p = create(client, "case_study", title="Heat network retrofit case study")
    finish(client, p["id"], {"challenge": "Ageing heat networks leaked energy across social housing estates.",
                             "results": "Heat network efficiency improved and bills fell for tenants."})
    client.post(url(p["id"], "/promote-evidence"))

    prop = client.post("/api/v1/notices", json={
        "notice_type": "grant_call", "funder_or_buyer": "Climate Fund", "title": "Heat network fund",
        "sector": "Energy", "raw_pack_text": "Impact (100%)."}).json()
    proposal = client.post("/api/v1/grants/proposals", json={
        "workspace_id": 1, "notice_id": prop["id"], "applicant_org": "Org", "requested_amount": 1000}).json()
    sugg = client.get(f"/api/v1/grants/proposals/{proposal['id']}/studio/suggestions?q=heat+network+efficiency").json()
    assert any("Heat network retrofit" in e["title"] for e in sugg["evidence"])


def test_cv_and_capability_statement_promote_with_their_own_types(client):
    cv = create(client, "team_cv", title="CV: Jane Doe, Technical Director")
    finish(client, cv["id"], {"profile": "Jane leads delivery of municipal fleet programmes."})
    cv_id = client.post(url(cv["id"], "/promote-evidence")).json()["evidence_item_id"]
    cap = create(client, "capability_statement", title="Capability statement 2026")
    finish(client, cap["id"], {"overview": "We deliver sustainable fleet software.", "competencies": "Routing, telematics."})
    cap_id = client.post(url(cap["id"], "/promote-evidence")).json()["evidence_item_id"]
    by_id = {e["id"]: e for e in client.get("/api/v1/evidence-library?workspace_id=1").json()}
    assert by_id[cv_id]["evidence_type"] == "cv" and by_id[cv_id]["summary"].startswith("Jane leads")
    assert by_id[cap_id]["evidence_type"] == "capability_statement"
    assert "sustainable fleet software" in by_id[cap_id]["summary"] and "Routing, telematics" in by_id[cap_id]["summary"]
    assert by_id[cap_id]["metrics"] == {}


def test_other_document_types_cannot_be_promoted(client):
    for doc_type in ("sop", "infosec_policy", "security_questionnaire"):
        p = create(client, doc_type, questions="Do you hold ISO 27001?")
        assert client.post(url(p["id"], "/promote-evidence")).status_code == 422
        assert client.get(url(p["id"])).json()["promotable"] is False
    assert client.post(url(9999, "/promote-evidence")).status_code == 404


def test_bid_asset_jobs_link_only_to_bid_asset_projects(client):
    from tests.test_marketplace import job_ws, new_client, register

    c = new_client(client)
    register(c, "bid@clients.test", "client", "Bea", "Bea Bids")
    ws = job_ws({"client": c})
    case = client.post("/api/v1/services/projects", json={"workspace_id": ws, "doc_type": "case_study", "title": "Case study"}).json()["id"]
    sop = client.post("/api/v1/services/projects", json={"workspace_id": ws, "doc_type": "sop", "title": "An SOP doc"}).json()["id"]
    post = lambda **kw: c.post("/api/v1/market/jobs", json={"title": "Write our case studies", **kw})  # noqa: E731
    assert post(job_type="bid_assets", doc_project_id=sop).status_code == 422
    assert post(job_type="technical_docs", doc_project_id=case).status_code == 422
    ok = post(job_type="bid_assets", doc_project_id=case)
    assert ok.status_code == 201 and ok.json()["job_type_label"] == "CVs, capability statements and case studies"
