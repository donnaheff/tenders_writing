def test_grant_calls_criteria_extraction_and_weighted_proposal(client):
    calls = client.get("/api/v1/grants/calls").json()
    assert len(calls) >= 4
    portals = " ".join(c["funder_or_buyer"] for c in calls)
    assert "European Commission" in portals
    assert "UKRI" in portals
    assert "World Bank" in portals
    assert "Foundation" in portals

    # Pick Foundation call which initially has empty structured_criteria
    foundation_call = next(c for c in calls if "Foundation" in c["funder_or_buyer"])
    ext_res = client.post(f"/api/v1/grants/calls/{foundation_call['id']}/extract-criteria")
    assert ext_res.status_code == 200
    extracted = ext_res.json()["criteria"]
    assert len(extracted) == 3
    assert sum(c["weight"] for c in extracted) == 100.0

    # Create a grant proposal with custom section scores
    eu_call = next(c for c in calls if "European Commission" in c["funder_or_buyer"])
    prop_res = client.post(
        "/api/v1/grants/proposals",
        json={
            "workspace_id": 1,
            "notice_id": eu_call["id"],
            "applicant_org": "OpenCivic Labs",
            "requested_amount": 1800000,
            "currency": "EUR",
            "sections": [
                {
                    "criterion_id": "EU-1",
                    "title": "Excellence & Novelty",
                    "weight": 40,
                    "max_score": 5,
                    "draft_text": "Novel civic procurement LLM verification.",
                    "self_score": 4.5,
                },
                {
                    "criterion_id": "EU-2",
                    "title": "Impact & Exploitation",
                    "weight": 35,
                    "max_score": 5,
                    "draft_text": "Adopted across 12 EU municipalities.",
                    "self_score": 4.0,
                },
                {
                    "criterion_id": "EU-3",
                    "title": "Implementation",
                    "weight": 25,
                    "max_score": 5,
                    "draft_text": "6 work packages with quarterly milestones.",
                    "self_score": 4.0,
                },
            ],
        },
    )
    assert prop_res.status_code == 201
    proposal = prop_res.json()
    # Weighted: (0.9*40 + 0.8*35 + 0.8*25) = 36 + 28 + 20 = 84.0%
    assert proposal["total_weighted_score"] == 84.0

    # Submit to quality review queue
    sub_res = client.post(f"/api/v1/grants/proposals/{proposal['id']}/submit-review")
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "in_review"
    queue_id = sub_res.json()["quality_queue_id"]

    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    assert any(q["id"] == queue_id and q["item_type"] == "grant_proposal" for q in queue)

    # Update sections and recalculate weighted score
    upd_res = client.put(
        f"/api/v1/grants/proposals/{proposal['id']}/sections",
        json={
            "sections": [
                {
                    "criterion_id": "EU-1",
                    "title": "Excellence & Novelty",
                    "weight": 40,
                    "max_score": 5,
                    "draft_text": "Expanded state-of-the-art benchmark.",
                    "self_score": 5.0,
                },
                {
                    "criterion_id": "EU-2",
                    "title": "Impact & Exploitation",
                    "weight": 35,
                    "max_score": 5,
                    "draft_text": "Adopted across 12 EU municipalities.",
                    "self_score": 5.0,
                },
                {
                    "criterion_id": "EU-3",
                    "title": "Implementation",
                    "weight": 25,
                    "max_score": 5,
                    "draft_text": "6 work packages with quarterly milestones.",
                    "self_score": 4.0,
                },
            ]
        },
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["total_weighted_score"] == 95.0

    # Approving the quality queue item syncs approval back to the grant proposal
    qa_res = client.post(
        f"/api/v1/quality-queue/{queue_id}/review",
        json={
            "assigned_reviewer": "Dr. Shaw",
            "status": "approved",
            "review_score": 94.0,
            "review_notes": "Ready for EU portal submission.",
        },
    )
    assert qa_res.status_code == 200
    proposals = client.get("/api/v1/grants/proposals?workspace_id=1").json()
    synced = next(p for p in proposals if p["id"] == proposal["id"])
    assert synced["status"] == "approved"

    export_res = client.get(f"/api/v1/grants/proposals/{proposal['id']}/export")
    assert export_res.status_code == 200
    assert "OpenCivic Labs" in export_res.json()["markdown"]
    assert "95.00%" in export_res.json()["markdown"]

