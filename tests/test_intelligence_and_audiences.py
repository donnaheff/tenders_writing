def test_tender_alerts_and_weekly_digest(client):
    sub_res = client.post(
        "/api/v1/alerts/subscriptions",
        json={
            "workspace_id": 1,
            "subscriber_email": "growth@bidstudio.example",
            "cadence": "weekly",
            "sectors": ["CleanTech & Transport"],
            "notice_types": ["tender", "grant_call"],
            "min_value": 100000.0,
        },
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    digest_res = client.post(f"/api/v1/alerts/subscriptions/{sub_id}/generate-digest")
    assert digest_res.status_code == 200
    digest = digest_res.json()
    assert digest["matched_count"] >= 2
    assert all("ai_summary" in item for item in digest["items"])

    orders = client.get("/api/v1/orders?workspace_id=1&source=subscription").json()
    assert any(o["customer_email"] == "growth@bidstudio.example" for o in orders)


def test_buyer_and_competitor_intelligence_report(client):
    res = client.post(
        "/api/v1/intelligence/buyer-report",
        json={"workspace_id": 1, "buyer_name": "Riverbend Borough Council"},
    )
    assert res.status_code == 201
    report = res.json()
    assert report["awards_analyzed"] == 3
    assert report["total_spend"] == 2770000.0
    assert report["top_winners"][0]["supplier"] == "GreenGrid Systems Ltd"
    assert report["top_winners"][0]["wins"] == 2


def test_framework_and_dps_onboarding_checklist(client):
    res = client.post(
        "/api/v1/frameworks",
        json={
            "workspace_id": 1,
            "vehicle_type": "dps",
            "vehicle_name": "CCS Automation DPS",
            "authority_name": "Crown Commercial Service",
            "lots": ["Lot 1: Process Automation"],
        },
    )
    assert res.status_code == 201
    fw = res.json()
    assert len(fw["checklist"]) == 7

    for item in fw["checklist"]:
        toggle = client.patch(
            f"/api/v1/frameworks/{fw['id']}/checklist",
            json={"item_id": item["item_id"], "completed": True, "notes": "Uploaded"},
        )
        assert toggle.status_code == 200

    final = client.get("/api/v1/frameworks?workspace_id=1").json()[0]
    assert final["completion_pct"] == 100.0
    assert final["readiness_status"] == "ready_to_submit"


def test_training_cohort_riverbend_enrolment_creates_training_order(client):
    cohorts = client.get("/api/v1/training/cohorts").json()
    assert len(cohorts) >= 1
    riverbend = next(c for c in cohorts if "Riverbend" in c["pack_name"])

    enrol_res = client.post(
        f"/api/v1/training/cohorts/{riverbend['id']}/enrol",
        json={
            "workspace_id": 1,
            "learner_name": "Priya Patel",
            "learner_email": "priya@bidacademy.example",
        },
    )
    assert enrol_res.status_code == 201
    body = enrol_res.json()
    assert body["order_source"] == "training_enrolment"

    orders = client.get("/api/v1/orders?workspace_id=1&source=training_enrolment").json()
    assert any(o["id"] == body["order_id"] and o["source"] == "training_enrolment" for o in orders)


def test_public_sector_draft_validates_weights_and_ambiguity(client):
    # Invalid draft: weights sum to 80% and text has TBD
    bad_res = client.post(
        "/api/v1/public-sector/drafts",
        json={
            "workspace_id": 1,
            "authority_name": "Riverbend Borough Council",
            "title": "Draft Waste Contract",
            "budget_value": 500000,
            "specification_text": "Supplier shall provide reasonable support and reporting, etc. Go-live TBD.",
            "evaluation_criteria": [
                {"name": "Quality", "weight_pct": 50, "max_score": 5, "scoring_guidance": "0-5"},
                {"name": "Price", "weight_pct": 30, "max_score": 5, "scoring_guidance": "Lowest price"},
            ],
        },
    )
    assert bad_res.status_code == 201
    bad = bad_res.json()
    assert bad["status"] == "draft"
    assert bad["clarity_score"] < 100.0
    assert len(bad["validation_issues"]) >= 2

    # Valid draft: weights sum to 100% and clear measurable specification
    good_res = client.post(
        "/api/v1/public-sector/drafts",
        json={
            "workspace_id": 1,
            "authority_name": "Riverbend Borough Council",
            "title": "Clear Civic Energy Tender",
            "budget_value": 750000,
            "specification_text": (
                "The appointed contractor shall install 14 air-source heat pumps across named civic depots "
                "between 1 February 2027 and 31 July 2027, maintaining a 4-hour P1 fault response SLA."
            ),
            "evaluation_criteria": [
                {"name": "Technical Delivery", "weight_pct": 50, "max_score": 5, "scoring_guidance": "0-5 rubric"},
                {"name": "Social Value", "weight_pct": 20, "max_score": 5, "scoring_guidance": "PPN 06/20"},
                {"name": "Price", "weight_pct": 30, "max_score": 5, "scoring_guidance": "Lowest price formula"},
            ],
        },
    )
    assert good_res.status_code == 201
    good = good_res.json()
    assert good["status"] == "validated"
    assert good["clarity_score"] == 100.0
    assert good["validation_issues"] == []

    scorecard_res = client.post(f"/api/v1/public-sector/drafts/{good['id']}/validate")
    assert scorecard_res.status_code == 200
    scorecard = scorecard_res.json()["scorecard"]
    assert len(scorecard) == 3
    assert sum(c["weight_pct"] for c in scorecard) == 100

