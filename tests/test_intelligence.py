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

    # Private notice in workspace 2 must not leak into workspace 1 digest
    priv = client.post(
        "/api/v1/notices",
        json={
            "workspace_id": 2,
            "notice_type": "tender",
            "funder_or_buyer": "Secret Buyer",
            "title": "Workspace 2 Private CleanTech Tender",
            "sector": "CleanTech & Transport",
            "contract_value": 500000.0,
        },
    )
    assert priv.status_code == 201
    digest2 = client.post(f"/api/v1/alerts/subscriptions/{sub_id}/generate-digest").json()
    assert all(item["notice_id"] != priv.json()["id"] for item in digest2["items"])


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

    # Private awarded notice in workspace 2 must not leak into workspace 1 intelligence report
    priv_award = client.post(
        "/api/v1/notices",
        json={
            "workspace_id": 2,
            "notice_type": "awarded_tender",
            "status": "awarded",
            "funder_or_buyer": "Riverbend Borough Council",
            "title": "Workspace 2 Private Award",
            "sector": "CleanTech & Transport",
            "contract_value": 999999.0,
            "awarded_supplier": "Shadow Corp",
        },
    )
    assert priv_award.status_code == 201
    report2 = client.post(
        "/api/v1/intelligence/buyer-report",
        json={"workspace_id": 1, "buyer_name": "Riverbend Borough Council"},
    ).json()
    assert report2["awards_analyzed"] == 3

    export_res = client.get(f"/api/v1/intelligence/reports/{report2['id']}/export")
    assert export_res.status_code == 200
    assert "GreenGrid Systems Ltd" in export_res.json()["markdown"]


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

    export_res = client.get(f"/api/v1/frameworks/{fw['id']}/export")
    assert export_res.status_code == 200
    assert "CCS Automation DPS" in export_res.json()["markdown"]
