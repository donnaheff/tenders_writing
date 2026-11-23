import pytest

from bid_studio.services.domain_logic import BUSINESS_DOC_LABELS, BUSINESS_DOC_OUTLINES

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def doc(client, **over):
    body = {
        "workspace_id": 1, "doc_type": "business_plan", "title": "Growth plan",
        "client_email": "a@b.example", "fixed_fee": 1500,
    }
    return client.post("/api/v1/business-docs", json={**body, **over})


# --------------------------------------------------------------- business documents


def test_business_types_and_outlines_are_in_sync():
    assert set(BUSINESS_DOC_OUTLINES) == set(BUSINESS_DOC_LABELS)


@pytest.mark.parametrize("doc_type", sorted(BUSINESS_DOC_LABELS))
def test_every_business_type_starts_from_an_outline(client, doc_type):
    r = doc(client, doc_type=doc_type)
    assert r.status_code == 201
    assert r.json()["draft_content"].startswith("# Growth plan")
    assert "_To be written._" in r.json()["draft_content"]


def test_fee_is_required_and_never_assumed(client):
    no_fee = client.post(
        "/api/v1/business-docs",
        json={"workspace_id": 1, "doc_type": "quotation", "title": "Quote", "client_email": "a@b.example"},
    )
    assert no_fee.status_code == 422
    assert doc(client, fixed_fee=-5).status_code == 422


def test_contract_like_documents_point_to_the_legal_service(client):
    for t in ("statement_of_work", "quotation", "business_proposal"):
        assert "Legal Contracts" in doc(client, doc_type=t).json()["draft_content"]
    assert "Legal Contracts" not in doc(client, doc_type="business_plan").json()["draft_content"]


def test_business_pipeline_has_the_same_qa_gate(client):
    d = doc(client).json()
    assert client.post(f"/api/v1/business-docs/{d['id']}/deliver").status_code == 400
    assert client.post(f"/api/v1/business-docs/{d['id']}/submit-quality").status_code == 200
    assert client.post(f"/api/v1/business-docs/{d['id']}/submit-quality").status_code == 409
    ok = client.post(f"/api/v1/business-docs/{d['id']}/review", json={"approved": True})
    assert ok.json()["pipeline_stage"] == "approved"
    assert client.post(f"/api/v1/business-docs/{d['id']}/deliver").status_code == 200
    assert "Growth plan" in client.get(f"/api/v1/business-docs/{d['id']}/export").json()["markdown"]


def test_qa_queue_approval_syncs_to_business_docs(client):
    d = doc(client).json()
    q = client.post(f"/api/v1/business-docs/{d['id']}/submit-quality").json()["quality_queue_id"]
    client.post(
        f"/api/v1/quality-queue/{q}/review",
        json={"assigned_reviewer": "Sam", "status": "approved", "review_score": 90},
    )
    assert client.post(f"/api/v1/business-docs/{d['id']}/deliver").status_code == 200


def test_business_and_technical_lists_do_not_mix(client):
    d = doc(client).json()
    tech = client.post(
        "/api/v1/tech-docs",
        json={"workspace_id": 1, "doc_type": "runbook", "title": "R", "client_email": "a@b.example"},
    ).json()
    business_ids = {x["id"] for x in client.get("/api/v1/business-docs?workspace_id=1").json()}
    tech_ids = {x["id"] for x in client.get("/api/v1/tech-docs?workspace_id=1").json()}
    assert d["id"] in business_ids and tech["id"] not in business_ids
    assert tech["id"] in tech_ids and d["id"] not in tech_ids
    # and the technical type list rejects business types
    bad = client.post(
        "/api/v1/tech-docs",
        json={"workspace_id": 1, "doc_type": "business_plan", "title": "x", "client_email": "a@b.example"},
    )
    assert bad.status_code == 422
    assert client.get(f"/api/v1/business-docs/{tech['id']}/export").status_code == 404


# ------------------------------------------------------------------ legal contracts


def matter(client, **over):
    body = {
        "workspace_id": 1, "contract_type": "nda", "title": "Mutual NDA",
        "client_email": "c@d.example", "jurisdiction": "England and Wales",
        "instructions": "Two-way, 3 years.",
    }
    r = client.post("/api/v1/legal-contracts", json={**body, **over})
    assert r.status_code == 201, r.text
    return r.json()


def assign(client, mid, name="Ada Okafor"):
    return client.post(
        f"/api/v1/legal-contracts/{mid}/assign-lawyer",
        json={"lawyer_name": name, "registration_ref": "REG-123"},
    )


def test_no_contract_text_is_ever_generated(client):
    m = matter(client)
    assert m["draft_content"] == "" and m["status"] == "intake"
    assert m["assigned_lawyer_name"] == ""


def test_lawyer_must_be_assigned_before_any_drafting(client):
    m = matter(client)
    r = client.put(
        f"/api/v1/legal-contracts/{m['id']}/draft", json={"lawyer_name": "Ada Okafor", "draft_content": "x"}
    )
    assert r.status_code == 409


def test_full_lawyer_flow_and_locks(client):
    m = matter(client)
    mid = m["id"]
    # locked while unsigned
    assert client.get(f"/api/v1/legal-contracts/{mid}/export").status_code == 409
    assert client.post(f"/api/v1/legal-contracts/{mid}/deliver").status_code == 400

    assert assign(client, mid).json()["status"] == "lawyer_assigned"
    # someone else cannot write or sign
    other = {"lawyer_name": "Someone Else"}
    assert client.put(f"/api/v1/legal-contracts/{mid}/draft", json={**other, "draft_content": "x"}).status_code == 403
    assert client.post(
        f"/api/v1/legal-contracts/{mid}/sign-off", json={**other, "confirm_qualified_and_reviewed": True}
    ).status_code == 403

    # cannot sign off with no text, or without the confirmation
    me = {"lawyer_name": "ada okafor"}  # case-insensitive match
    assert client.post(
        f"/api/v1/legal-contracts/{mid}/sign-off", json={**me, "confirm_qualified_and_reviewed": True}
    ).status_code == 409
    saved = client.put(f"/api/v1/legal-contracts/{mid}/draft", json={**me, "draft_content": "1. Definitions"})
    assert saved.status_code == 200 and saved.json()["status"] == "in_progress"
    assert client.post(
        f"/api/v1/legal-contracts/{mid}/sign-off", json={**me, "confirm_qualified_and_reviewed": False}
    ).status_code == 400

    signed = client.post(
        f"/api/v1/legal-contracts/{mid}/sign-off", json={**me, "confirm_qualified_and_reviewed": True}
    )
    assert signed.status_code == 200
    assert signed.json()["status"] == "lawyer_signed_off" and signed.json()["signed_off_at"]

    exported = client.get(f"/api/v1/legal-contracts/{mid}/export").json()["markdown"]
    assert "Ada Okafor" in exported and "REG-123" in exported and "not legal advice" in exported
    delivered = client.post(f"/api/v1/legal-contracts/{mid}/deliver")
    assert delivered.status_code == 200
    # delivered contracts are frozen
    assert client.put(
        f"/api/v1/legal-contracts/{mid}/draft", json={**me, "draft_content": "changed"}
    ).status_code == 409


def test_editing_after_sign_off_voids_the_sign_off(client):
    mid = matter(client)["id"]
    assign(client, mid)
    me = {"lawyer_name": "Ada Okafor"}
    client.put(f"/api/v1/legal-contracts/{mid}/draft", json={**me, "draft_content": "v1"})
    client.post(f"/api/v1/legal-contracts/{mid}/sign-off", json={**me, "confirm_qualified_and_reviewed": True})
    edited = client.put(f"/api/v1/legal-contracts/{mid}/draft", json={**me, "draft_content": "v2 (changed)"})
    body = edited.json()
    assert body["status"] == "in_progress" and body["signed_off_at"] is None and body["signed_off_by"] == ""
    assert client.get(f"/api/v1/legal-contracts/{mid}/export").status_code == 409
    assert client.post(f"/api/v1/legal-contracts/{mid}/deliver").status_code == 400


def test_legal_list_carries_the_notice_and_requires_jurisdiction(client):
    matter(client)
    listing = client.get("/api/v1/legal-contracts?workspace_id=1").json()
    assert "does not draft legal contracts" in listing["notice"] and listing["items"]
    bad = client.post(
        "/api/v1/legal-contracts",
        json={"workspace_id": 1, "contract_type": "nda", "title": "N", "client_email": "a@b.example"},
    )
    assert bad.status_code == 422


def test_legal_work_is_never_exposed_to_ai_clients(client):
    tools = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCP_HEADERS
    ).json()["result"]["tools"]
    names = " ".join(t["name"] for t in tools).lower()
    assert "legal" not in names and "contract" not in names and "lawyer" not in names
    for provider in ("openai", "openai-chat", "anthropic", "gemini"):
        text = client.get(f"/api/v1/developers/tools/{provider}").text.lower()
        assert "legal-contracts" not in text and "legal_contract" not in text
    assert client.post("/api/v1/developers/tools/create_legal_matter/call", json={}).status_code == 404


# ------------------------------------------------------------------------- website


def test_new_services_have_pages_and_the_lawyer_notice(client):
    legal = client.get("/services/legal-contracts").text
    assert "Lawyer-only service" in legal and "does not draft legal contracts" in legal
    assert "Business Documents" in client.get("/services").text
    assert "Business &amp; Legal Documents" in client.get("/services").text
    app = client.get("/app/legal-contracts").text
    assert "Lawyer-only service." in app and "legalMatters" in app
    biz = client.get("/app/business-documents").text
    for label in BUSINESS_DOC_LABELS.values():
        assert f">{label}</option>" in biz, label
    assert "/services/legal-contracts" in client.get("/sitemap.xml").text
