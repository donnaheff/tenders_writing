from tests.test_marketplace import (  # noqa: F401
    PROFILE,
    approve_all,
    job_ws,
    new_client,
    open_job,
    people,
)

M = "/api/v1/market"


def make_doc_project(client, workspace_id, doc_type="api_reference", **extra):
    res = client.post("/api/v1/services/projects", json={
        "workspace_id": workspace_id, "doc_type": doc_type, "title": "Acme API docs",
        "client_name": "Carol Charity", "questions": "Do you hold ISO 27001?", **extra})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_job_type_catalogue_is_public(people):  # noqa: F811
    types = {t["key"]: t for t in people["anon"].get(f"{M}/job-types").json()}
    assert set(types) >= {"grant_proposal", "technical_docs", "compliance_policy", "security_questionnaire", "bid_assets", "grant_documents", "tender_documents", "other"}
    assert types["technical_docs"]["link"] == "doc" and types["other"]["link"] is None


def test_jobs_default_to_grant_proposal_and_validate_type(people):  # noqa: F811
    p = people
    assert open_job(p)["job_type"] == "grant_proposal"
    bad = p["client"].post(f"{M}/jobs", json={"title": "Doc job", "job_type": "nope"})
    assert bad.status_code == 422
    docs = p["client"].post(f"{M}/jobs", json={"title": "Write our API docs", "job_type": "technical_docs"}).json()
    assert docs["job_type"] == "technical_docs" and docs["job_type_label"] == "Technical documentation"


def test_linking_documentation_projects_validates_workspace_type_and_clash(people, client):  # noqa: F811
    p = people
    ws = job_ws(p)
    api_doc = make_doc_project(client, ws, "api_reference")
    policy = make_doc_project(client, ws, "infosec_policy")
    questionnaire = make_doc_project(client, ws, "security_questionnaire")
    foreign = make_doc_project(client, job_ws({"client": p["other_client"]}), "api_reference")

    def post(**kw):
        return p["client"].post(f"{M}/jobs", json={"title": "Linked doc job", **kw})

    assert post(job_type="technical_docs", doc_project_id=foreign).status_code == 404
    assert post(job_type="technical_docs", doc_project_id=9999).status_code == 404
    assert post(job_type="compliance_policy", doc_project_id=api_doc).status_code == 422  # wrong kind
    assert post(job_type="technical_docs", doc_project_id=policy).status_code == 422
    assert post(job_type="compliance_policy", doc_project_id=questionnaire).status_code == 422  # has own type
    assert post(job_type="security_questionnaire", doc_project_id=policy).status_code == 422
    assert post(job_type="grant_proposal", doc_project_id=api_doc).status_code == 422
    assert post(job_type="technical_docs", proposal_id=1).status_code == 422
    assert post(job_type="technical_docs", doc_project_id=api_doc, proposal_id=1).status_code == 422
    assert post(job_type="other", doc_project_id=api_doc).status_code == 422

    ok = post(job_type="technical_docs", doc_project_id=api_doc)
    assert ok.status_code == 201 and ok.json()["doc_project_id"] == api_doc
    assert post(job_type="technical_docs", doc_project_id=api_doc).status_code == 409  # already live
    assert post(job_type="compliance_policy", doc_project_id=policy).status_code == 201
    assert post(job_type="security_questionnaire", doc_project_id=questionnaire).status_code == 201


def test_documentation_project_access_follows_the_live_job(people, client):  # noqa: F811
    p = people
    approve_all(p)
    proj = make_doc_project(client, job_ws(p), "sop")
    job = p["client"].post(f"{M}/jobs", json={"title": "Write our SOP", "job_type": "technical_docs", "doc_project_id": proj}).json()
    base = f"/api/v1/services/projects/{proj}"

    assert p["anon"].get(base).status_code == 200  # open while only a brief exists
    bid = p["writer"].post(f"{M}/jobs/{job['id']}/bids", json={"price": 900}).json()
    p["client"].post(f"{M}/jobs/{job['id']}/bids/{bid['id']}/accept")

    for call in (lambda c: c.get(base), lambda c: c.get(base + "/export"),
                 lambda c: c.put(base, json={"title": "Hacked title"}),
                 lambda c: c.post(base + "/assistant", json={"action": "draft", "target_id": "purpose"}),
                 lambda c: c.post(base + "/submit-quality")):
        assert call(p["anon"]).status_code == 401
        assert call(p["other_writer"]).status_code == 403
        assert call(p["other_client"]).status_code == 403
    assert p["writer"].get(base).status_code == 200 and p["client"].get(base).status_code == 200 and p["admin"].get(base).status_code == 200

    secs = p["writer"].get(base).json()["sections"]
    secs[0]["text"] = "Written by the marketplace writer."
    assert p["writer"].put(base, json={"sections": secs}).status_code == 200
    assert p["anon"].get("/api/v1/services/templates").status_code == 200  # global routes stay open

    link = p["writer"].get(f"{M}/jobs/{job['id']}/studio-link").json()
    assert link == {"proposal_id": None, "doc_project_id": proj, "url": f"/app/docs/{proj}", "access_restricted": True}

    p["writer"].post(f"{M}/jobs/{job['id']}/deliver")
    assert p["anon"].get(base).status_code == 401
    p["client"].post(f"{M}/jobs/{job['id']}/approve")
    assert p["anon"].get(base).status_code == 200  # completed: guard lifts


def test_writers_declare_service_types_and_directory_filters_by_them(people):  # noqa: F811
    p = people
    bad = p["writer"].put(f"{M}/writers/me", json={**PROFILE, "service_types": ["nonsense"]})
    assert bad.status_code == 422
    p["writer"].put(f"{M}/writers/me", json={**PROFILE, "service_types": ["technical_docs", "grant_proposal", "technical_docs"]})
    p["other_writer"].put(f"{M}/writers/me", json={**PROFILE, "service_types": ["security_questionnaire"]})
    approve_all(p)
    names = lambda qs: sorted(w["name"] for w in p["anon"].get(f"{M}/writers?{qs}").json())  # noqa: E731
    assert names("service_type=technical_docs") == ["Ann Writer"]
    assert names("service_type=security_questionnaire") == ["Bob Writer"]
    assert names("service_type=compliance_policy") == []
    listing = p["anon"].get(f"{M}/writers").json()
    ann = next(w for w in listing if w["name"] == "Ann Writer")
    assert ann["service_types"] == ["grant_proposal", "technical_docs"]  # de-duplicated and sorted
    assert p["anon"].get(f"{M}/writers/{ann['id']}").json()["service_types"] == ann["service_types"]


def test_open_jobs_filter_by_type_and_by_what_the_writer_offers(people):  # noqa: F811
    p = people
    p["writer"].put(f"{M}/writers/me", json={**PROFILE, "service_types": ["technical_docs"]})
    p["other_writer"].put(f"{M}/writers/me", json=PROFILE)  # offers nothing declared
    approve_all(p)
    open_job(p)  # grant proposal
    p["client"].post(f"{M}/jobs", json={"title": "API docs please", "job_type": "technical_docs"})
    p["client"].post(f"{M}/jobs", json={"title": "Answer our security Qs", "job_type": "security_questionnaire"})

    titles = lambda who, qs="": sorted(j["title"] for j in p[who].get(f"{M}/jobs?scope=open&{qs}").json())  # noqa: E731
    assert len(titles("writer")) == 3
    assert titles("writer", "job_type=technical_docs") == ["API docs please"]
    assert titles("writer", "matching=true") == ["API docs please"]
    assert titles("other_writer", "matching=true") == []  # nothing declared, nothing matches
    assert len(titles("other_writer")) == 3
    assert titles("writer", "job_type=security_questionnaire&matching=true") == []


def test_job_type_blocked_by_licence_only_for_private_routes(people, monkeypatch):  # noqa: F811
    from bid_studio.config import settings
    from bid_studio.services import licensing

    _, public = licensing.generate_keypair()
    monkeypatch.setattr(settings, "license_public_key", public)
    monkeypatch.setattr(settings, "license_enforcement", "on")
    assert people["anon"].get(f"{M}/job-types").status_code == 200
    assert people["writer"].get(f"{M}/jobs").status_code == 402
