import pytest
from fastapi.testclient import TestClient

from bid_studio.config import settings
from bid_studio.services import auth, licensing

PW = "correct-horse-battery"


def new_client(client) -> TestClient:
    """A separate browser: same app, own cookie jar."""
    return TestClient(client.app)


def register(c, email, role, name=None, org=""):
    res = c.post(
        "/api/v1/market/auth/register",
        json={"email": email, "password": PW, "name": name or email.split("@")[0], "role": role, "organisation": org},
    )
    assert res.status_code == 201, res.text
    return res.json()


PROFILE = {
    "headline": "Horizon Europe specialist",
    "bio": "Ten years writing winning RIA proposals.",
    "specialisms": ["Horizon Europe", "Climate"],
    "funders": ["European Commission"],
    "day_rate": 450,
    "currency": "GBP",
    "samples": [{"title": "Sample", "url": "https://example.org/sample"}],
}


@pytest.fixture()
def people(client, monkeypatch):
    monkeypatch.setattr(settings, "marketplace_admin_emails", "boss@platform.test")
    p = {"admin": new_client(client), "writer": new_client(client), "client": new_client(client),
         "other_writer": new_client(client), "other_client": new_client(client), "anon": new_client(client)}
    register(p["admin"], "boss@platform.test", "writer")  # role is overridden to admin
    register(p["writer"], "ann@writers.test", "writer", "Ann Writer")
    register(p["other_writer"], "bob@writers.test", "writer", "Bob Writer")
    register(p["client"], "carol@clients.test", "client", "Carol", "Carol Charity")
    register(p["other_client"], "dan@clients.test", "client", "Dan", "Dan Trust")
    for who in ("writer", "other_writer"):
        assert p[who].put("/api/v1/market/writers/me", json=PROFILE).status_code == 200
    return p


def approve_all(p):
    pending = p["admin"].get("/api/v1/market/admin/writers").json()
    for w in pending:
        assert p["admin"].post(f"/api/v1/market/admin/writers/{w['id']}/approve").status_code == 200


def open_job(p, **extra):
    body = {"title": "Horizon proposal writer", "description": "Need RIA draft", "funder": "European Commission",
            "budget_min": 2000, "budget_max": 5000, **extra}
    res = p["client"].post("/api/v1/market/jobs", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_register_login_logout_and_validation(client):
    c = new_client(client)
    me = register(c, "eve@x.test", "client", "Eve", "Eve Org")
    assert me["role"] == "client" and me["workspace_id"]
    cookie = c.cookies.get("bs_session")
    assert cookie and "HttpOnly" in c.post("/api/v1/market/auth/login", json={"email": "eve@x.test", "password": PW}).headers["set-cookie"]
    assert c.get("/api/v1/market/auth/me").json()["email"] == "eve@x.test"
    assert c.post("/api/v1/market/auth/logout").status_code == 200
    assert c.get("/api/v1/market/auth/me").status_code == 401

    other = new_client(client)
    dup = other.post("/api/v1/market/auth/register", json={"email": "EVE@x.test", "password": PW, "name": "E", "role": "writer"})
    assert dup.status_code == 409
    weak = other.post("/api/v1/market/auth/register", json={"email": "z@x.test", "password": "short", "name": "Z", "role": "writer"})
    assert weak.status_code == 422
    bad_role = other.post("/api/v1/market/auth/register", json={"email": "z@x.test", "password": PW, "name": "Z", "role": "admin"})
    assert bad_role.status_code == 422


def test_passwords_are_hashed_and_wrong_password_and_brute_force_blocked(client):
    c = new_client(client)
    register(c, "frank@x.test", "writer")
    from bid_studio.database import get_db
    db = next(client.app.dependency_overrides[get_db]())
    stored = db.query(auth.MarketAccount).filter_by(email="frank@x.test").one().password_hash
    assert stored.startswith("scrypt$") and PW not in stored
    auth._failures.clear()
    for _ in range(5):
        assert c.post("/api/v1/market/auth/login", json={"email": "frank@x.test", "password": "nope-nope-nope"}).status_code == 401
    blocked = c.post("/api/v1/market/auth/login", json={"email": "frank@x.test", "password": PW})
    assert blocked.status_code == 429
    auth._failures.clear()
    assert c.post("/api/v1/market/auth/login", json={"email": "ghost@x.test", "password": PW}).status_code == 401


def test_cross_site_post_is_blocked(client):
    c = new_client(client)
    res = c.post("/api/v1/market/auth/logout", headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_writer_directory_only_shows_approved_and_hides_email(people):
    p = people
    assert p["anon"].get("/api/v1/market/writers").json() == []
    assert p["writer"].post("/api/v1/market/admin/writers/1/approve").status_code == 403
    assert p["anon"].get("/api/v1/market/admin/writers").status_code == 401

    pending = p["admin"].get("/api/v1/market/admin/writers").json()
    assert {w["name"] for w in pending} == {"Ann Writer", "Bob Writer"}
    ann = next(w for w in pending if w["name"] == "Ann Writer")
    p["admin"].post(f"/api/v1/market/admin/writers/{ann['id']}/approve")

    listing = p["anon"].get("/api/v1/market/writers")
    assert [w["name"] for w in listing.json()] == ["Ann Writer"]
    assert listing.headers["X-Total-Count"] == "1"
    assert "email" not in listing.json()[0]
    assert p["anon"].get(f"/api/v1/market/writers/{ann['id']}").status_code == 200
    bob = next(w for w in pending if w["name"] == "Bob Writer")
    assert p["anon"].get(f"/api/v1/market/writers/{bob['id']}").status_code == 404

    p["admin"].post(f"/api/v1/market/admin/writers/{ann['id']}/suspend")
    assert p["anon"].get("/api/v1/market/writers").json() == []
    assert p["writer"].put("/api/v1/market/writers/me", json=PROFILE).status_code == 403


def test_directory_filters_and_sorting(people):
    p = people
    approve_all(p)
    p["other_writer"].put("/api/v1/market/writers/me", json={**PROFILE, "specialisms": ["Health"], "funders": ["UKRI"], "day_rate": 300})
    api = lambda qs: [w["name"] for w in p["anon"].get(f"/api/v1/market/writers?{qs}").json()]  # noqa: E731
    assert api("specialism=Health") == ["Bob Writer"]
    assert api("funder=European+Commission") == ["Ann Writer"]
    assert api("q=RIA") == ["Ann Writer", "Bob Writer"]
    assert api("q=Health") == ["Bob Writer"]
    assert api("max_rate=350") == ["Bob Writer"]
    assert api("sort=rate") == ["Bob Writer", "Ann Writer"]
    assert api("min_rating=4") == []
    assert api("limit=1&offset=1") in (["Ann Writer"], ["Bob Writer"])


def test_unapproved_writer_cannot_see_or_bid_on_jobs(people):
    p = people
    job = open_job(p)
    assert p["writer"].get("/api/v1/market/jobs").status_code == 403
    assert p["writer"].post(f"/api/v1/market/jobs/{job['id']}/bids", json={"price": 1000}).status_code == 403
    assert p["writer"].post("/api/v1/market/jobs", json={"title": "Nope nope"}).status_code == 403  # writers can't post
    assert p["anon"].get("/api/v1/market/jobs").status_code == 401


def test_bidding_and_accepting_flow(people, client):
    p = people
    approve_all(p)
    job = open_job(p)
    jid = job["id"]
    assert [j["id"] for j in p["writer"].get("/api/v1/market/jobs").json()] == [jid]
    assert p["client"].get("/api/v1/market/jobs").status_code == 403
    assert [j["id"] for j in p["client"].get("/api/v1/market/jobs?scope=mine").json()] == [jid]

    b1 = p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 3000, "timeline_days": 21, "message": "Hi"}).json()
    b2 = p["other_writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 2500}).json()
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 100}).status_code == 409
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 0}).status_code == 422

    seen_by_client = p["client"].get(f"/api/v1/market/jobs/{jid}/bids").json()
    assert [b["price"] for b in seen_by_client] == [2500, 3000]
    assert [b["writer_name"] for b in p["writer"].get(f"/api/v1/market/jobs/{jid}/bids").json()] == ["Ann Writer"]
    assert p["other_client"].get(f"/api/v1/market/jobs/{jid}").status_code == 404

    assert p["other_client"].post(f"/api/v1/market/jobs/{jid}/bids/{b1['id']}/accept").status_code == 404
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/bids/{b1['id']}/accept").status_code == 403

    accepted = p["client"].post(f"/api/v1/market/jobs/{jid}/bids/{b1['id']}/accept").json()
    assert accepted["status"] == "in_progress" and accepted["agreed_price"] == 3000
    assert accepted["platform_fee"] == round(3000 * settings.marketplace_fee_pct / 100, 2)
    assert accepted["writer_name"] == "Ann Writer"
    loser = p["other_writer"].get(f"/api/v1/market/jobs/{jid}/bids").json()[0]
    assert loser["status"] == "rejected" and b2["id"] == loser["id"]
    assert p["client"].post(f"/api/v1/market/jobs/{jid}/bids/{b2['id']}/accept").status_code == 409

    members = client.get(f"/api/v1/workspaces/{job_ws(p)}/members").json()
    assert any(m["email"] == "ann@writers.test" and m["role"] == "writer" for m in members)
    assert p["other_writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 1}).status_code == 409


def job_ws(p):
    return p["client"].get("/api/v1/market/auth/me").json()["workspace_id"]


def test_withdraw_bid(people):
    p = people
    approve_all(p)
    jid = open_job(p)["id"]
    bid = p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 900}).json()
    assert p["other_writer"].post(f"/api/v1/market/jobs/{jid}/bids/{bid['id']}/withdraw").status_code == 404
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/bids/{bid['id']}/withdraw").json()["status"] == "withdrawn"
    assert p["client"].post(f"/api/v1/market/jobs/{jid}/bids/{bid['id']}/accept").status_code == 404


def accepted_job(p, **extra):
    approve_all(p)
    job = open_job(p, **extra)
    bid = p["writer"].post(f"/api/v1/market/jobs/{job['id']}/bids", json={"price": 2000}).json()
    p["client"].post(f"/api/v1/market/jobs/{job['id']}/bids/{bid['id']}/accept")
    return job["id"]


def test_delivery_changes_approval_review_and_rating(people):
    p = people
    jid = accepted_job(p)
    base = f"/api/v1/market/jobs/{jid}"
    assert p["client"].post(f"{base}/deliver").status_code == 403
    assert p["other_writer"].post(f"{base}/deliver").status_code == 404
    assert p["client"].post(f"{base}/approve").status_code == 409  # nothing delivered yet
    assert p["writer"].post(f"{base}/deliver").json()["status"] == "delivered"

    assert p["client"].post(f"{base}/request-changes", json={"note": ""}).status_code == 422
    assert p["client"].post(f"{base}/request-changes", json={"note": "Tighten impact"}).json()["status"] == "in_progress"
    assert any("Tighten impact" in m["body"] for m in p["writer"].get(f"{base}/messages").json())
    p["writer"].post(f"{base}/deliver")

    assert p["client"].post(f"{base}/review", json={"rating": 5}).status_code == 409  # not completed
    assert p["client"].post(f"{base}/approve").json()["status"] == "completed"
    assert p["other_client"].post(f"{base}/review", json={"rating": 5}).status_code == 404
    assert p["client"].post(f"{base}/review", json={"rating": 6}).status_code == 422
    rev = p["client"].post(f"{base}/review", json={"rating": 4, "comment": "Great"}).json()
    assert rev == {"rating_avg": 4.0, "rating_count": 1}
    assert p["client"].post(f"{base}/review", json={"rating": 5}).status_code == 409

    ann = p["anon"].get("/api/v1/market/writers").json()[0]
    assert ann["completed_jobs"] == 1 and ann["rating_avg"] == 4.0
    reviews = p["anon"].get(f"/api/v1/market/writers/{ann['id']}/reviews").json()
    assert reviews[0]["comment"] == "Great" and reviews[0]["job_title"] == "Horizon proposal writer"


def test_messages_are_private_to_participants(people):
    p = people
    approve_all(p)
    job = open_job(p)
    assert p["client"].post(f"/api/v1/market/jobs/{job['id']}/messages", json={"body": "hello"}).status_code == 409  # before accept
    jid = job["id"]
    bid = p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 1500}).json()
    p["client"].post(f"/api/v1/market/jobs/{jid}/bids/{bid['id']}/accept")
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/messages", json={"body": "Kick-off call?"}).status_code == 201
    msgs = p["client"].get(f"/api/v1/market/jobs/{jid}/messages").json()
    assert [(m["sender"], m["mine"]) for m in msgs] == [("Ann Writer", False)]
    for outsider in ("other_writer", "other_client", ):
        assert p[outsider].get(f"/api/v1/market/jobs/{jid}/messages").status_code == 404
        assert p[outsider].post(f"/api/v1/market/jobs/{jid}/messages", json={"body": "x"}).status_code == 404
    assert p["admin"].get(f"/api/v1/market/jobs/{jid}/messages").status_code == 200


def test_payment_tracking_two_step(people):
    p = people
    jid = accepted_job(p)
    base = f"/api/v1/market/jobs/{jid}/payment"
    assert p["writer"].post(f"{base}/confirm").status_code == 409
    assert p["client"].post(f"{base}/mark-paid").json()["payment_status"] == "client_marked_paid"
    assert p["client"].post(f"{base}/mark-paid").status_code == 409
    assert p["client"].post(f"{base}/confirm").status_code == 403
    assert p["writer"].post(f"{base}/confirm").json()["payment_status"] == "writer_confirmed"


def test_cancel_open_job_rejects_bids(people):
    p = people
    approve_all(p)
    jid = open_job(p)["id"]
    p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 800})
    assert p["client"].post(f"/api/v1/market/jobs/{jid}/cancel").json()["status"] == "cancelled"
    assert p["writer"].get(f"/api/v1/market/jobs/{jid}/bids").json()[0]["status"] == "rejected"
    assert p["writer"].post(f"/api/v1/market/jobs/{jid}/bids", json={"price": 700}).status_code == 409


def test_job_hides_private_fields_from_non_participants(people):
    p = people
    approve_all(p)
    jid = open_job(p)["id"]
    seen = p["writer"].get(f"/api/v1/market/jobs/{jid}").json()
    assert "proposal_id" not in seen and "agreed_price" not in seen and seen["is_client"] is False
    mine = p["client"].get(f"/api/v1/market/jobs/{jid}").json()
    assert "agreed_price" in mine and mine["is_client"] is True


def make_proposal(client, workspace_id):
    call = client.get("/api/v1/grants/calls").json()[0]
    res = client.post("/api/v1/grants/proposals", json={"workspace_id": workspace_id, "notice_id": call["id"], "applicant_org": "Carol Charity", "requested_amount": 1000})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_studio_access_is_restricted_while_a_job_is_live(people, client):
    p = people
    approve_all(p)
    pid = make_proposal(client, job_ws(p))
    assert p["other_client"].post("/api/v1/market/jobs", json={"title": "Steal it", "proposal_id": pid}).status_code == 404
    job = open_job(p, proposal_id=pid)
    assert p["client"].post("/api/v1/market/jobs", json={"title": "Dup job", "proposal_id": pid}).status_code == 409

    studio = f"/api/v1/grants/proposals/{pid}/studio"
    assert p["anon"].get(studio).status_code == 200  # still open while only a brief exists
    bid = p["writer"].post(f"/api/v1/market/jobs/{job['id']}/bids", json={"price": 1800}).json()
    p["client"].post(f"/api/v1/market/jobs/{job['id']}/bids/{bid['id']}/accept")

    assert p["anon"].get(studio).status_code == 401
    assert p["anon"].put(f"{studio}/save", json={"sections": []}).status_code == 401
    assert p["anon"].get(f"/api/v1/grants/proposals/{pid}/export").status_code == 401
    assert p["anon"].post(f"/api/v1/grants/proposals/{pid}/submit-review").status_code == 401
    assert p["other_writer"].get(studio).status_code == 403
    assert p["other_client"].get(studio).status_code == 403
    for who in ("writer", "client", "admin"):
        assert p[who].get(studio).status_code == 200
    link = p["writer"].get(f"/api/v1/market/jobs/{job['id']}/studio-link").json()
    assert link["url"] == f"/app/studio/{pid}" and link["access_restricted"] is True

    sections = p["writer"].get(studio).json()["sections"]
    sections[0]["draft_text"] = "Written by the marketplace writer."
    saved = p["writer"].put(f"{studio}/save", json={"sections": sections})
    assert saved.status_code == 200

    p["writer"].post(f"/api/v1/market/jobs/{job['id']}/deliver")
    assert p["anon"].get(studio).status_code == 401  # delivered is still protected
    p["client"].post(f"/api/v1/market/jobs/{job['id']}/approve")
    assert p["anon"].get(studio).status_code == 200  # completed: back to normal


def test_licence_blocks_marketplace_but_not_public_directory(people, monkeypatch):
    p = people
    _, public = licensing.generate_keypair()
    monkeypatch.setattr(settings, "license_public_key", public)
    monkeypatch.setattr(settings, "license_enforcement", "on")
    assert p["anon"].get("/api/v1/market/writers").status_code == 200
    assert p["client"].get("/api/v1/market/jobs?scope=mine").status_code == 402
    assert p["anon"].post("/api/v1/market/auth/login", json={"email": "a@b.co", "password": PW}).status_code == 402


def test_client_registration_respects_workspace_licence_limit(client, monkeypatch):
    private, public = licensing.generate_keypair()
    monkeypatch.setattr(settings, "license_public_key", public)
    monkeypatch.setattr(settings, "license_enforcement", "on")
    from datetime import date
    key = licensing.issue(private, licensee="L", plan="team", today=date.today())
    monkeypatch.setattr(settings, "license_key", key)  # team = 1 workspace; seed already has 2
    res = new_client(client).post(
        "/api/v1/market/auth/register",
        json={"email": "gina@x.test", "password": PW, "name": "Gina", "role": "client"},
    )
    assert res.status_code == 402
