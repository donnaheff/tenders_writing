import json
from datetime import UTC, datetime, timedelta

from bid_studio.config import settings
from bid_studio.services import feed_sources
from bid_studio.services.feed_sources import parse_eu_funding, parse_grants_gov

GRANTS_GOV_PAYLOAD = {
    "data": {
        "oppHits": [
            {
                "id": "364160",
                "number": "NOAA-OAR-CPO-2027-33392",
                "title": "Climate Program Office FY 2027",
                "agencyCode": "DOC-NOAA",
                "agency": "DOC NOAA - ERA Production",
                "openDate": "10/27/2026",
                "closeDate": "02/09/2027",
                "oppStatus": "posted",
                "cfdaList": ["11.431"],
            },
            {
                "id": "1",
                "number": "ROLLING-1",
                "title": "Rolling Community Grant",
                "agency": "Dept of Example",
                "closeDate": "",
                "oppStatus": "posted",
                "cfdaList": [],
            },
            {"id": "", "title": "no id is skipped"},
        ]
    }
}

EU_PAYLOAD = {
    "results": [
        {
            "summary": "Space critical equipment",
            "url": "https://ec.europa.eu/topic-details/HORIZON-X-1",
            "metadata": {
                "identifier": ["HORIZON-X-1"],
                "title": ["Space critical equipment"],
                "callTitle": ["SPACE"],
                "deadlineDate": ["2028-01-20T00:00:00.000+0000"],
                "url": ["https://ec.europa.eu/topic-details/HORIZON-X-1"],
                "budgetOverview": [
                    json.dumps(
                        {
                            "budgetTopicActionMap": {
                                "1": [{"expectedGrants": 2, "maxContribution": 4000000}]
                            }
                        }
                    )
                ],
            },
        },
        {"metadata": {}, "summary": ""},
    ]
}


def test_parse_grants_gov_normalises_dates_and_skips_bad_rows():
    items = parse_grants_gov(GRANTS_GOV_PAYLOAD)
    assert [i.external_id for i in items] == ["364160", "1"]
    first, rolling = items
    assert first.deadline == "2027-02-09"
    assert first.currency == "USD" and first.region == "US"
    assert first.url.endswith("/364160")
    assert rolling.deadline == ""


def test_parse_eu_funding_extracts_deadline_value_and_url():
    (item,) = parse_eu_funding(EU_PAYLOAD)
    assert item.external_id == "HORIZON-X-1"
    assert item.deadline == "2028-01-20"
    assert item.value == 8000000.0
    assert item.currency == "EUR"
    assert item.sector == "SPACE"


def _fake_sources(monkeypatch, gg=None, eu=None):
    monkeypatch.setitem(
        feed_sources.SOURCES,
        "grants_gov",
        lambda limit=50, keyword="": parse_grants_gov(gg or GRANTS_GOV_PAYLOAD),
    )
    monkeypatch.setitem(
        feed_sources.SOURCES,
        "eu_funding",
        lambda limit=50, keyword="": parse_eu_funding(eu or EU_PAYLOAD),
    )


def test_sync_ingests_dedupes_and_updates(client, monkeypatch):
    _fake_sources(monkeypatch)
    first = client.post("/api/v1/grants/feed/sync?source=all").json()
    assert [(r["source"], r["status"], r["created"]) for r in first] == [
        ("grants_gov", "ok", 2),
        ("eu_funding", "ok", 1),
    ]

    again = client.post("/api/v1/grants/feed/sync?source=all").json()
    assert all(r["created"] == 0 and r["updated"] == 0 for r in again)

    changed = json.loads(json.dumps(GRANTS_GOV_PAYLOAD))
    changed["data"]["oppHits"][0]["closeDate"] = "03/01/2027"
    _fake_sources(monkeypatch, gg=changed)
    third = client.post("/api/v1/grants/feed/sync?source=grants_gov").json()
    assert third[0]["created"] == 0 and third[0]["updated"] == 1

    feed = client.get("/api/v1/grants/feed?q=Climate+Program").json()
    assert len(feed) == 1
    assert feed[0]["deadline"] == "2027-03-01"
    assert feed[0]["url"].startswith("https://www.grants.gov/")


def test_sync_records_error_without_breaking(client, monkeypatch):
    def boom(limit=50, keyword=""):
        raise RuntimeError("upstream down")

    monkeypatch.setitem(feed_sources.SOURCES, "grants_gov", boom)
    res = client.post("/api/v1/grants/feed/sync?source=grants_gov")
    assert res.status_code == 200
    assert res.json()[0]["status"] == "error"
    assert "upstream down" in res.json()[0]["error"]
    runs = client.get("/api/v1/grants/feed/sync/runs").json()
    assert runs[0]["status"] == "error"
    assert client.post("/api/v1/grants/feed/sync?source=nope").status_code == 422


def test_feed_filters_sorting_and_pagination(client, monkeypatch):
    _fake_sources(monkeypatch)
    client.post("/api/v1/grants/feed/sync?source=all")

    res = client.get("/api/v1/grants/feed?limit=2&offset=0")
    total = int(res.headers["X-Total-Count"])
    assert total >= 7 and len(res.json()) == 2

    by_deadline = client.get("/api/v1/grants/feed?limit=100").json()
    dated = [i["deadline"] for i in by_deadline if i["deadline"]]
    assert dated == sorted(dated)
    assert by_deadline[-1]["deadline"] is None  # rolling opportunities sort last

    by_value = client.get("/api/v1/grants/feed?sort=value&limit=1").json()
    assert by_value[0]["value"] == 8000000.0

    only_eu = client.get("/api/v1/grants/feed?region=EU").json()
    assert only_eu and all(i["region"] == "EU" for i in only_eu)
    big = client.get("/api/v1/grants/feed?min_value=1000000&max_value=3000000").json()
    assert all(1000000 <= i["value"] <= 3000000 for i in big)
    assert client.get("/api/v1/grants/feed?source=Grants.gov").headers["X-Total-Count"] == "2"


def test_feed_hides_expired_unless_requested_and_closing_soon(client):
    today = datetime.now(UTC).date()
    for title, deadline in [
        ("Expired Fund", (today - timedelta(days=3)).isoformat()),
        ("Closing Soon Fund", (today + timedelta(days=4)).isoformat()),
    ]:
        client.post(
            "/api/v1/notices",
            json={
                "notice_type": "grant_call",
                "funder_or_buyer": "F",
                "title": title,
                "sector": "S",
                "deadline": deadline,
            },
        )
    titles = lambda qs: {i["title"] for i in client.get(f"/api/v1/grants/feed?{qs}").json()}  # noqa: E731
    # notices created through the API belong to a workspace, so ask for workspace 1
    assert "Expired Fund" not in titles("workspace_id=1&limit=100")
    assert "Expired Fund" in titles("workspace_id=1&include_expired=true&limit=100")
    assert titles("workspace_id=1&closing_within_days=5") == {"Closing Soon Fund"}
    soon = client.get("/api/v1/grants/feed?workspace_id=1&closing_within_days=5").json()[0]
    assert soon["days_left"] == 4


def test_workspace_scoping_save_and_facets(client, monkeypatch):
    _fake_sources(monkeypatch)
    client.post("/api/v1/grants/feed/sync?source=eu_funding")
    private = client.post(
        "/api/v1/notices",
        json={
            "workspace_id": 2,
            "notice_type": "grant_call",
            "funder_or_buyer": "Private Funder",
            "title": "Private Call",
            "sector": "X",
            "deadline": "2099-01-01",
        },
    ).json()

    public = {i["title"] for i in client.get("/api/v1/grants/feed?limit=100").json()}
    assert "Private Call" not in public
    ws2 = {i["title"] for i in client.get("/api/v1/grants/feed?workspace_id=2&limit=100").json()}
    assert "Private Call" in ws2
    ws1 = {i["title"] for i in client.get("/api/v1/grants/feed?workspace_id=1&limit=100").json()}
    assert "Private Call" not in ws1

    nid = client.get("/api/v1/grants/feed?q=Space+critical").json()[0]["id"]
    assert client.post(f"/api/v1/grants/feed/{nid}/save?workspace_id=1").json()["saved"] is True
    client.post(f"/api/v1/grants/feed/{nid}/save?workspace_id=1")  # idempotent
    saved = client.get("/api/v1/grants/feed?workspace_id=1&saved_only=true").json()
    assert [i["id"] for i in saved] == [nid] and saved[0]["saved"] is True
    assert client.get("/api/v1/grants/feed?saved_only=true").status_code == 422
    client.delete(f"/api/v1/grants/feed/{nid}/save?workspace_id=1")
    assert client.get("/api/v1/grants/feed?workspace_id=1&saved_only=true").json() == []
    assert client.post(f"/api/v1/grants/feed/{private['id'] + 999}/save").status_code == 404

    client.post(f"/api/v1/grants/calls/{nid}/auto-process?workspace_id=1")
    flagged = client.get("/api/v1/grants/feed?q=Space+critical&workspace_id=1").json()[0]
    assert flagged["has_proposal"] is True

    facets = client.get("/api/v1/grants/feed/facets").json()
    assert {"value": "EU", "count": 2} in facets["regions"]
    assert any(s["value"] == "EU Funding & Tenders Portal" for s in facets["sources"])


def test_scheduled_run_syncs_configured_feeds(client, monkeypatch):
    _fake_sources(monkeypatch)
    assert client.post("/api/v1/automation/run").json()["feed_sync"] == {}
    monkeypatch.setattr(settings, "feed_sources", "grants_gov, eu_funding, bogus")
    out = client.post("/api/v1/automation/run").json()["feed_sync"]
    assert out["grants_gov"]["created"] == 2 and out["eu_funding"]["created"] == 1
    assert "bogus" not in out
    assert client.post("/api/v1/automation/run").json()["feed_sync"]["grants_gov"]["created"] == 0
