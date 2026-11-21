import copy
from datetime import UTC, datetime, timedelta


def _proposal(client, deadline="2099-01-01", applicant="Civic Labs"):
    nid = client.post(
        "/api/v1/notices",
        json={
            "notice_type": "grant_call",
            "funder_or_buyer": "Civic Climate & Community Foundation",
            "title": "Studio Test Fund",
            "sector": "Climate",
            "contract_value": 100000,
            "deadline": deadline,
            "raw_pack_text": "Impact (60%), Delivery (40%).",
        },
    ).json()["id"]
    res = client.post(
        "/api/v1/grants/proposals",
        json={"workspace_id": 1, "notice_id": nid, "applicant_org": applicant,
              "requested_amount": 50000, "currency": "GBP"},
    )
    return res.json()


def _studio(client, pid):
    return client.get(f"/api/v1/grants/proposals/{pid}/studio").json()


def _written(sections):
    out = copy.deepcopy(sections)
    for s in out:
        s["draft_text"] = "We will deliver measurable climate outcomes with named partners."
        s["evidence_refs"] = ["1"]
    return out


def test_studio_payload_has_counts_call_context_and_readiness(client):
    p = _proposal(client)
    data = _studio(client, p["id"])
    assert data["proposal"]["id"] == p["id"] and data["locked"] is False
    assert data["call"]["title"] == "Studio Test Fund" and data["call"]["days_left"] > 1000
    assert all(s["unwritten"] for s in data["sections"])
    checks = {c["id"]: c for c in data["readiness"]["checks"]}
    assert checks["drafted"]["ok"] is False and data["readiness"]["ready"] is False
    assert "Impact" in checks["drafted"]["detail"]
    assert data["branding"]["brand_name"]


def test_save_recomputes_score_counts_words_and_snapshots(client):
    p = _proposal(client)
    secs = _written(p["sections"])
    secs[0]["self_score"] = secs[0]["max_score"]
    secs[0]["word_limit"] = 5
    res = client.put(
        f"/api/v1/grants/proposals/{p['id']}/studio/save",
        json={"sections": secs, "meta": {"title": "Renamed", "requested_amount": 75000}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["proposal"]["title"] == "Renamed"
    assert data["proposal"]["requested_amount"] == 75000
    assert data["sections"][0]["word_count"] == 9 and data["sections"][0]["over_limit"] is True
    assert data["version_created"] == 1  # first save always snapshots
    assert data["proposal"]["total_weighted_score"] == round(60 + 0.75 * 40, 2)
    checks = {c["id"]: c for c in data["readiness"]["checks"]}
    assert checks["limits"]["ok"] is False and "Impact" in checks["limits"]["detail"]

    again = client.put(
        f"/api/v1/grants/proposals/{p['id']}/studio/save", json={"sections": secs}
    ).json()
    assert again["version_created"] is None  # within autosnapshot window, nothing new

    assert client.put(
        f"/api/v1/grants/proposals/{p['id']}/studio/save", json={"sections": secs[:1]}
    ).status_code == 422


def test_versions_label_list_view_and_restore(client):
    p = _proposal(client)
    pid = p["id"]
    first = _written(p["sections"])
    client.put(f"/api/v1/grants/proposals/{pid}/studio/save", json={"sections": first, "label": "First draft"})
    edited = copy.deepcopy(first)
    edited[0]["draft_text"] = "Completely rewritten text."
    client.put(f"/api/v1/grants/proposals/{pid}/studio/save", json={"sections": edited, "label": "Rewrite"})

    versions = client.get(f"/api/v1/grants/proposals/{pid}/versions").json()
    assert [v["label"] for v in versions] == ["Rewrite", "First draft"]
    v1 = client.get(f"/api/v1/grants/proposals/{pid}/versions/1").json()
    assert v1["snapshot"]["sections"][0]["draft_text"].startswith("We will deliver")
    assert client.get(f"/api/v1/grants/proposals/{pid}/versions/99").status_code == 404

    restored = client.post(f"/api/v1/grants/proposals/{pid}/versions/1/restore").json()
    assert restored["sections"][0]["draft_text"].startswith("We will deliver")
    labels = [v["label"] for v in client.get(f"/api/v1/grants/proposals/{pid}/versions").json()]
    assert "Before restoring v1" in labels

    manual = client.post(f"/api/v1/grants/proposals/{pid}/versions", json={"label": "Checkpoint"})
    assert manual.status_code == 201


def test_suggestions_rank_library_by_section_and_query(client):
    p = _proposal(client)
    sugg = client.get(f"/api/v1/grants/proposals/{p['id']}/studio/suggestions?q=ISO+27001+certification").json()
    assert sugg["answers"] and "ISO" in sugg["answers"][0]["title"]
    assert sugg["answers"][0]["match"] >= 1
    nothing = client.get(
        f"/api/v1/grants/proposals/{p['id']}/studio/suggestions?q=zzzqqq"
    ).json()
    assert nothing == {"answers": [], "evidence": []}
    by_section = client.get(f"/api/v1/grants/proposals/{p['id']}/studio/suggestions?section=0")
    assert by_section.status_code == 200


def test_submit_requires_readiness_then_locks_editing(client):
    p = _proposal(client)
    pid = p["id"]
    blocked = client.post(f"/api/v1/grants/proposals/{pid}/studio/submit")
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["failing"][0]["id"] == "drafted"

    secs = _written(p["sections"])
    for s in secs:
        s["self_score"] = s["max_score"]
    client.put(f"/api/v1/grants/proposals/{pid}/studio/save", json={"sections": secs})
    ok = client.post(f"/api/v1/grants/proposals/{pid}/studio/submit")
    assert ok.status_code == 200 and ok.json()["status"] == "in_review"

    assert client.post(f"/api/v1/grants/proposals/{pid}/studio/submit").status_code == 409
    locked = client.put(f"/api/v1/grants/proposals/{pid}/studio/save", json={"sections": secs})
    assert locked.status_code == 409
    assert _studio(client, pid)["locked"] is True
    assert client.post(f"/api/v1/grants/proposals/{pid}/versions/1/restore").status_code == 409

    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    item = next(q for q in queue if q["reference_id"] == pid)
    client.post(
        f"/api/v1/quality-queue/{item['id']}/review",
        json={"assigned_reviewer": "QA", "status": "changes_requested", "review_notes": "Tighten impact"},
    )
    assert _studio(client, pid)["locked"] is False  # changes requested reopens the draft


def test_readiness_blocks_missing_applicant_amount_and_closed_call(client):
    soon = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    p = _proposal(client, deadline=soon, applicant="   ")
    checks = {c["id"]: c for c in _studio(client, p["id"])["readiness"]["checks"]}
    assert checks["applicant"]["ok"] is False
    assert checks["deadline"]["ok"] is False and checks["deadline"]["severity"] == "warning"

    past = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
    q = _proposal(client, deadline=past)
    qc = {c["id"]: c for c in _studio(client, q["id"])["readiness"]["checks"]}
    assert qc["deadline"]["ok"] is False and qc["deadline"]["severity"] == "blocker"


def test_studio_page_and_feed_proposal_link(client):
    p = _proposal(client)
    page = client.get(f"/app/studio/{p['id']}")
    assert page.status_code == 200 and "Grant Studio" in page.text
    assert client.get("/app/studio/99999").status_code == 404
    assert client.get("/api/v1/grants/proposals/99999/studio").status_code == 404

    call = client.post(f"/api/v1/grants/calls/{p['notice_id']}/auto-process?workspace_id=1").json()
    feed = client.get("/api/v1/grants/feed?workspace_id=1&q=Studio+Test&limit=5").json()
    item = next(i for i in feed if i["id"] == p["notice_id"])
    assert item["has_proposal"] is True and item["proposal_id"] == call["proposal"]["id"]
