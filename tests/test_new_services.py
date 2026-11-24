def test_tech_docs_pipeline_qa_and_email_delivery(client):
    create_res = client.post(
        "/api/v1/tech-docs",
        json={
            "workspace_id": 1,
            "doc_type": "api_reference",
            "title": "Payments OpenAPI v3 Guide",
            "client_email": "cto@fintech.example",
            "fixed_fee": 1200.0,
        },
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["id"]

    # Delivery before QA approval must fail
    early_deliver = client.post(f"/api/v1/tech-docs/{doc_id}/deliver")
    assert early_deliver.status_code == 400

    # Submit to quality stage (duplicate submit returns 409), approve, then deliver
    qa_sub = client.post(f"/api/v1/tech-docs/{doc_id}/submit-quality")
    assert qa_sub.status_code == 200
    assert qa_sub.json()["pipeline_stage"] == "quality_review"

    dup_qa = client.post(f"/api/v1/tech-docs/{doc_id}/submit-quality")
    assert dup_qa.status_code == 409

    review_res = client.post(
        f"/api/v1/tech-docs/{doc_id}/review",
        json={"approved": True, "reviewer_notes": "Verified all OpenAPI schemas."},
    )
    assert review_res.status_code == 200
    assert review_res.json()["pipeline_stage"] == "approved"

    deliver_res = client.post(f"/api/v1/tech-docs/{doc_id}/deliver")
    assert deliver_res.status_code == 200
    assert deliver_res.json()["pipeline_stage"] == "delivered"

    export_res = client.get(f"/api/v1/tech-docs/{doc_id}/export")
    assert export_res.status_code == 200
    assert "Payments OpenAPI v3 Guide" in export_res.json()["markdown"]

    logs = client.get("/api/v1/deliveries?workspace_id=1").json()
    assert any(
        log["delivery_type"] == "tech_doc_delivery" and log["recipient_email"] == "cto@fintech.example"
        for log in logs
    )


def test_compliance_security_questionnaire_auto_matches_answer_library(client):
    pack_res = client.post(
        "/api/v1/compliance/packs",
        json={
            "workspace_id": 1,
            "pack_type": "security_questionnaire",
            "title": "Public Cloud Security Assessment",
            "questions": [
                "Do you hold ISO 27001 certification for your ISMS?",
                "How is customer data encrypted at rest and in transit?",
                "What is your penetration testing cadence and incident response SLA?",
            ],
        },
    )
    assert pack_res.status_code == 201
    pack_id = pack_res.json()["id"]

    match_res = client.post(f"/api/v1/compliance/packs/{pack_id}/auto-match")
    assert match_res.status_code == 200
    body = match_res.json()
    assert body["matched_count"] == 3
    assert all(item["matched_answer_id"] is not None for item in body["questionnaire_items"])

    export_res = client.get(f"/api/v1/compliance/packs/{pack_id}/export")
    assert export_res.status_code == 200
    assert "Public Cloud Security Assessment" in export_res.json()["markdown"]


def test_bidder_asset_promotes_to_evidence_library(client):
    asset_res = client.post(
        "/api/v1/bidder-assets",
        json={
            "workspace_id": 1,
            "asset_type": "case_study",
            "title": "Zero-Downtime Core Banking Cutover",
            "subject_name": "Metro Treasury",
            "buyer_format": "Cabinet Office Case Study",
            "content": "Migrated 1.4M accounts with 0 minutes unplanned downtime.",
            "metrics": {"accounts_migrated": 1400000, "downtime_minutes": 0},
        },
    )
    assert asset_res.status_code == 201
    asset_id = asset_res.json()["id"]

    promo_res = client.post(f"/api/v1/bidder-assets/{asset_id}/promote-to-evidence")
    assert promo_res.status_code == 200
    evidence_id = promo_res.json()["evidence_id"]

    evidence = client.get("/api/v1/evidence-library?workspace_id=1").json()
    assert any(e["id"] == evidence_id and e["source_asset_id"] == asset_id for e in evidence)

    export_res = client.get(f"/api/v1/bidder-assets/{asset_id}/export")
    assert export_res.status_code == 200
    assert "Zero-Downtime Core Banking Cutover" in export_res.json()["markdown"]


def test_marketplace_reviewer_scoring_updates_quality_queue(client):
    reviewers = client.get("/api/v1/marketplace/reviewers").json()
    assert len(reviewers) >= 2

    req_res = client.post(
        "/api/v1/marketplace/reviews",
        json={
            "workspace_id": 1,
            "reviewer_id": reviewers[0]["id"],
            "target_title": "Riverbend Fleet Draft v1",
            "buyer_criteria": [{"name": "Technical", "weight": 60}, {"name": "Social Value", "weight": 40}],
            "draft_excerpt": "Electric refuse fleet mobilisation in 8 weeks.",
        },
    )
    assert req_res.status_code == 201
    review = req_res.json()

    score_res = client.post(
        f"/api/v1/marketplace/reviews/{review['id']}/score",
        json={
            "criterion_scores": [
                {"name": "Technical", "weight": 60, "score": 85, "max_score": 100},
                {"name": "Social Value", "weight": 40, "score": 75, "max_score": 100},
            ],
            "feedback_summary": "Strong mobilisation timeline; quantify apprenticeship hours.",
        },
    )
    assert score_res.status_code == 200
    scored = score_res.json()
    assert scored["overall_score"] == 81.0
    assert scored["status"] == "completed"

    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    linked = next(q for q in queue if q["id"] == scored["quality_queue_id"])
    assert linked["status"] == "approved"
    assert linked["review_score"] == 81.0

    export_res = client.get(f"/api/v1/marketplace/reviews/{review['id']}/export")
    assert export_res.status_code == 200
    assert "Riverbend Fleet Draft v1" in export_res.json()["markdown"]


import pytest  # noqa: E402


@pytest.mark.parametrize(
    ("doc_type", "heading"),
    [
        ("whitepaper", "## Executive summary"),
        ("runbook", "## Rollback"),
        ("architecture_doc", "## Alternatives considered"),
    ],
)
def test_long_form_tech_doc_types_start_from_an_outline(client, doc_type, heading):
    res = client.post(
        "/api/v1/tech-docs",
        json={
            "workspace_id": 1,
            "doc_type": doc_type,
            "title": "Payments platform",
            "client_email": "cto@fintech.example",
        },
    )
    assert res.status_code == 201
    doc = res.json()
    assert doc["doc_type"] == doc_type
    assert heading in doc["draft_content"]
    assert doc["pipeline_stage"] == "intake"
    export = client.get(f"/api/v1/tech-docs/{doc['id']}/export").json()["markdown"]
    assert doc_type in export and heading in export


def test_unknown_tech_doc_type_is_rejected(client):
    res = client.post(
        "/api/v1/tech-docs",
        json={"workspace_id": 1, "doc_type": "poem", "title": "x", "client_email": "a@b.example"},
    )
    assert res.status_code == 422


def test_existing_tech_doc_types_keep_the_original_placeholder(client):
    res = client.post(
        "/api/v1/tech-docs",
        json={"workspace_id": 1, "doc_type": "sop", "title": "Onboarding", "client_email": "a@b.example"},
    )
    assert "Structured sop draft ready for staff pipeline." in res.json()["draft_content"]


def test_service_page_lists_the_new_packages(client):
    page = client.get("/services/tech-docs").text
    assert "whitepaper" in page and "runbook" in page and "architecture document" in page
    assert "Architecture Document" in client.get("/app/tech-docs").text


def test_every_tech_doc_type_is_wired_end_to_end():
    """Schema, outlines, labels and the app form must all list the same document types."""
    import typing
    from pathlib import Path

    from bid_studio.schemas import TechDocCreate
    from bid_studio.services.domain_logic import TECH_DOC_LABELS, TECH_DOC_OUTLINES

    literal = set(typing.get_args(TechDocCreate.model_fields["doc_type"].annotation))
    assert literal == set(TECH_DOC_LABELS)
    original = {"user_guide", "api_reference", "sop", "release_notes"}
    assert set(TECH_DOC_OUTLINES) == literal - original
    form = (
        Path(__file__).resolve().parent.parent
        / "src/bid_studio/templates/app/sections/techdocs.html"
    ).read_text()
    for key, label in TECH_DOC_LABELS.items():
        assert f'<option value="{key}">{label}</option>' in form, key


@pytest.mark.parametrize(
    ("doc_type", "heading"),
    [
        ("tutorial", "## Check that it works"),
        ("knowledge_base_article", "## Common problems"),
        ("migration_guide", "## Deprecation timeline"),
        ("postmortem", "## Root cause"),
        ("datasheet", "## Technical specifications"),
    ],
)
def test_second_batch_of_tech_doc_types(client, doc_type, heading):
    res = client.post(
        "/api/v1/tech-docs",
        json={"workspace_id": 1, "doc_type": doc_type, "title": "Billing API", "client_email": "a@b.example"},
    )
    assert res.status_code == 201
    assert heading in res.json()["draft_content"]
    # runs through the same QA gate as every other type
    doc_id = res.json()["id"]
    assert client.post(f"/api/v1/tech-docs/{doc_id}/deliver").status_code == 400
