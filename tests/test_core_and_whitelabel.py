def test_health_and_dashboard(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "Bid Studio" in home.text


def test_white_label_and_access_review_and_isolation(client):
    # Create a new white-label consultancy workspace
    create_res = client.post(
        "/api/v1/workspaces",
        json={
            "slug": "apex-consult",
            "name": "Apex Bid Consultancy",
            "is_white_label": True,
            "brand_name": "Apex Bid Portal",
            "primary_color": "#1e293b",
            "accent_color": "#0ea5e9",
            "custom_domain": "portal.apexbids.example",
        },
    )
    assert create_res.status_code == 201
    ws_id = create_res.json()["id"]

    # Add member and verify duplicate member returns 409
    member_res = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "writer@apex.example", "full_name": "Sam Writer", "role": "writer"},
    )
    assert member_res.status_code == 201
    dup_res = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "writer@apex.example", "full_name": "Sam Writer", "role": "writer"},
    )
    assert dup_res.status_code == 409

    review_res = client.get(f"/api/v1/workspaces/{ws_id}/access-review")
    assert review_res.status_code == 200
    data = review_res.json()
    assert data["brand_name"] == "Apex Bid Portal"
    assert data["client_isolation_enforced"] is True
    assert data["member_count"] == 1

    # Verify strict isolation: answer library items in workspace 1 do not leak into ws_id
    ws_answers = client.get(f"/api/v1/answer-library?workspace_id={ws_id}").json()
    assert ws_answers == []

    # Update white-label settings
    wl_res = client.put(
        f"/api/v1/workspaces/{ws_id}/white-label",
        json={
            "is_white_label": True,
            "brand_name": "Apex Enterprise Bids",
            "primary_color": "#000000",
            "accent_color": "#10b981",
            "custom_domain": "bids.apex.example",
            "support_email": "help@apex.example",
            "client_isolation_enforced": True,
        },
    )
    assert wl_res.status_code == 200
    assert wl_res.json()["brand_name"] == "Apex Enterprise Bids"

    consultancies = client.get("/api/v1/white-label/consultancies").json()
    assert any(c["brand_name"] == "Apex Enterprise Bids" for c in consultancies)


def test_private_workspace_notices_are_isolated(client):
    private_notice = client.post(
        "/api/v1/notices",
        json={
            "workspace_id": 2,
            "notice_type": "tender",
            "source_portal": "Private Client Portal",
            "funder_or_buyer": "NorthStar Private Buyer",
            "title": "NorthStar Confidential Tender",
            "sector": "Digital & Cloud",
            "contract_value": 150000,
        },
    )
    assert private_notice.status_code == 201
    notice_id = private_notice.json()["id"]

    ws1_notices = client.get("/api/v1/notices?workspace_id=1").json()
    assert all(n["id"] != notice_id for n in ws1_notices)

    ws2_notices = client.get("/api/v1/notices?workspace_id=2").json()
    assert any(n["id"] == notice_id for n in ws2_notices)

    # Search and pagination on notices
    searched = client.get("/api/v1/notices?workspace_id=2&q=Confidential").json()
    assert len(searched) == 1
    assert searched[0]["id"] == notice_id

    page = client.get("/api/v1/notices?workspace_id=1&limit=2&offset=1").json()
    assert len(page) == 2


def test_workspace_summary_kpis(client):
    res = client.get("/api/v1/workspaces/1/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["workspace_id"] == 1
    assert "win_rate_pct" in data
    assert "total_order_revenue" in data

