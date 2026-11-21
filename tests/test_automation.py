from datetime import UTC, datetime, timedelta

from bid_studio.config import settings


def _grant_call(client, deadline):
    res = client.post(
        "/api/v1/notices",
        json={
            "notice_type": "grant_call",
            "funder_or_buyer": "Civic Climate & Community Foundation",
            "title": "Rapid Response Fund",
            "sector": "CleanTech & Transport",
            "contract_value": 50000,
            "deadline": deadline,
            "raw_pack_text": "Impact (60%), Delivery (40%).",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_auto_process_call_creates_scored_proposal_in_qa_and_is_idempotent(client):
    call_id = _grant_call(client, "2027-06-01")
    first = client.post(f"/api/v1/grants/calls/{call_id}/auto-process?workspace_id=1").json()
    assert first["created"] is True
    proposal = first["proposal"]
    assert proposal["status"] == "in_review"
    assert len(proposal["sections"]) == 2
    assert proposal["total_weighted_score"] == 75.0
    assert proposal["quality_queue_id"]

    second = client.post(f"/api/v1/grants/calls/{call_id}/auto-process?workspace_id=1").json()
    assert second["created"] is False
    assert second["proposal"]["id"] == proposal["id"]

    queue = client.get("/api/v1/quality-queue?workspace_id=1").json()
    assert sum(1 for q in queue if q["reference_id"] == proposal["id"]) == 1


def test_auto_process_all_open_calls(client):
    res = client.post("/api/v1/grants/auto-process?workspace_id=1").json()
    assert res["processed"] >= 4
    assert len(res["created_proposal_ids"]) == res["processed"]
    again = client.post("/api/v1/grants/auto-process?workspace_id=1").json()
    assert again["created_proposal_ids"] == []


def test_auto_process_rejects_non_grant_notice(client):
    notices = client.get("/api/v1/notices?workspace_id=1&notice_type=tender").json()
    res = client.post(f"/api/v1/grants/calls/{notices[0]['id']}/auto-process")
    assert res.status_code == 404


def test_scheduled_run_sends_digest_and_deadline_reminder_once(client):
    soon = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    call_id = _grant_call(client, soon)
    client.post(f"/api/v1/grants/calls/{call_id}/auto-process?workspace_id=1")
    client.post(
        "/api/v1/alerts/subscriptions",
        json={"workspace_id": 1, "subscriber_email": "ops@example.org", "cadence": "weekly"},
    )

    first = client.post("/api/v1/automation/run").json()
    assert first["digests_sent"] == 1
    assert first["deadline_reminders_sent"] == 1

    second = client.post("/api/v1/automation/run").json()
    assert second["digests_sent"] == 0
    assert second["deadline_reminders_sent"] == 0

    types = {d["delivery_type"] for d in client.get("/api/v1/deliveries?workspace_id=1").json()}
    assert {"digest", "deadline_reminder"} <= types


def test_scheduled_run_requires_secret_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    assert client.get("/api/v1/automation/run").status_code == 401
    assert (
        client.get("/api/v1/automation/run", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    ok = client.get("/api/v1/automation/run", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_scheduled_run_can_auto_process_default_workspace(client, monkeypatch):
    monkeypatch.setattr(settings, "auto_process_grants", True)
    res = client.post("/api/v1/automation/run").json()
    assert res["proposals_auto_created"] >= 4
    assert client.post("/api/v1/automation/run").json()["proposals_auto_created"] == 0


def test_contact_request_creates_notification(client):
    client.post(
        "/api/v1/contact",
        json={"name": "Sam", "email": "sam@example.org", "plan": "team", "message": "Hello"},
    )
    logs = client.get("/api/v1/deliveries?workspace_id=1").json()
    note = next(d for d in logs if d["delivery_type"] == "contact_notification")
    assert "Sam" in note["subject"]
    assert note["status"] == "logged"
