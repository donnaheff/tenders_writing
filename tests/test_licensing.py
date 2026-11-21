import base64
import json
from datetime import date, timedelta

import pytest

from bid_studio.config import settings
from bid_studio.services import licensing as lic
from bid_studio.tools import license_admin

TODAY = date(2026, 6, 1)


@pytest.fixture()
def keys():
    private, public = lic.generate_keypair()
    return private, public


def _key(private, **kw):
    kw.setdefault("licensee", "Acme Ltd")
    kw.setdefault("plan", "team")
    kw.setdefault("today", TODAY)
    return lic.issue(private, **kw)


def _configure(monkeypatch, public, mode="on", **extra):
    monkeypatch.setattr(settings, "license_public_key", public)
    monkeypatch.setattr(settings, "license_enforcement", mode)
    for k, v in extra.items():
        monkeypatch.setattr(settings, k, v)


def test_issue_and_parse_roundtrip_with_plan_defaults(keys):
    private, public = keys
    parsed = lic.parse(_key(private, days=30), public)
    assert (parsed.licensee, parsed.plan) == ("Acme Ltd", "team")
    assert (parsed.max_workspaces, parsed.max_members) == (1, 15)
    assert parsed.expires_at == (TODAY + timedelta(days=30)).isoformat()
    overridden = lic.parse(_key(private, max_workspaces=5, max_members=40), public)
    assert (overridden.max_workspaces, overridden.max_members) == (5, 40)
    assert lic.parse(_key(private, plan="consultancy", days=None), public).expires_at is None
    with pytest.raises(lic.LicenseError):
        lic.issue(private, licensee="x", plan="gold")


def test_forged_tampered_and_foreign_keys_are_rejected(keys):
    private, public = keys
    key = _key(private)
    head, body, sig = key.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=="))
    payload["plan"] = "consultancy"
    forged_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    for bad in (f"{head}.{forged_body}.{sig}", f"{head}.{body}.{sig[:-3]}AAA", "garbage", "BS1.a", ""):
        with pytest.raises(lic.LicenseError):
            lic.parse(bad, public)
    other_private, _ = lic.generate_keypair()
    with pytest.raises(lic.LicenseError, match="signature"):
        lic.parse(_key(other_private), public)  # signed by someone else
    with pytest.raises(lic.LicenseError, match="LICENSE_PUBLIC_KEY"):
        lic.parse(key, "")


def test_evaluate_states_and_modes(keys, monkeypatch):
    private, public = keys
    key = _key(private, days=30)
    _configure(monkeypatch, public)

    assert lic.evaluate(key, TODAY).state == "valid"
    assert lic.evaluate(key, TODAY).days_left == 30
    assert lic.evaluate(key, TODAY + timedelta(days=35)).state == "grace"
    assert lic.evaluate(key, TODAY + timedelta(days=35)).allowed is True
    late = lic.evaluate(key, TODAY + timedelta(days=60))
    assert late.state == "expired" and late.allowed is False
    assert lic.evaluate("", TODAY).state == "missing"
    assert lic.evaluate("nope", TODAY).state == "invalid"

    key_id = lic.parse(key, public).key_id
    monkeypatch.setattr(settings, "license_revoked_ids", f"x, {key_id}")
    assert lic.evaluate(key, TODAY).state == "revoked"
    monkeypatch.setattr(settings, "license_revoked_ids", "")

    monkeypatch.setattr(settings, "license_enforcement", "warn")
    warn = lic.evaluate("", TODAY)
    assert warn.state == "missing" and warn.allowed is True  # reported, never blocked
    monkeypatch.setattr(settings, "license_enforcement", "off")
    assert lic.evaluate("", TODAY).state == "disabled"
    monkeypatch.setattr(settings, "license_enforcement", "bogus")
    assert lic.evaluate("", TODAY).allowed is False  # unknown mode fails closed


def test_enforcement_off_by_default_leaves_everything_open(client):
    assert client.get("/api/v1/license").json()["state"] == "disabled"
    assert client.get("/app").status_code == 200
    assert client.get("/api/v1/workspaces").status_code == 200


def test_unlicensed_install_blocks_app_and_api_but_not_public_site(client, keys, monkeypatch):
    _, public = keys
    _configure(monkeypatch, public)
    assert client.get("/app", follow_redirects=False).status_code == 307
    assert client.get("/app", follow_redirects=False).headers["location"] == "/app/license"
    assert client.get("/app/studio/1", follow_redirects=False).status_code == 307
    blocked = client.get("/api/v1/workspaces")
    assert blocked.status_code == 402 and blocked.json()["state"] == "missing"
    assert client.post("/api/v1/automation/run").status_code == 402

    for open_path in ("/", "/features", "/pricing", "/grants", "/app/license", "/static/site.css",
                      "/api/v1/health", "/api/v1/license", "/api/v1/grants/feed",
                      "/api/v1/grants/feed/facets", "/docs"):
        assert client.get(open_path, follow_redirects=False).status_code == 200, open_path
    contact = client.post(
        "/api/v1/contact", json={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert contact.status_code == 201
    assert client.post("/api/v1/grants/feed/sync?source=nope").status_code == 402  # not public


def test_activation_installs_key_and_unlocks(client, keys, monkeypatch):
    private, public = keys
    _configure(monkeypatch, public)
    assert client.get("/api/v1/workspaces").status_code == 402

    bad = client.post("/api/v1/license", json={"key": "BS1.not.valid-key"})
    assert bad.status_code == 422
    other_private, _ = lic.generate_keypair()
    foreign = client.post("/api/v1/license", json={"key": _key(other_private, today=date.today())})
    assert foreign.status_code == 422 and "signature" in foreign.json()["detail"]
    expired = client.post("/api/v1/license", json={"key": _key(private, days=1, today=TODAY)})
    assert expired.status_code == 422

    good = client.post("/api/v1/license", json={"key": _key(private, today=date.today())})
    assert good.status_code == 201
    body = good.json()
    assert body["state"] == "valid" and body["licensee"] == "Acme Ltd" and body["source"] == "database"
    assert body["usage"]["workspaces"] >= 2
    assert client.get("/api/v1/workspaces").status_code == 200
    assert client.get("/app").status_code == 200
    assert "key" not in body  # the key itself is never echoed back


def test_env_key_takes_precedence_over_activated_key(client, keys, monkeypatch):
    private, public = keys
    _configure(monkeypatch, public)
    client.post("/api/v1/license", json={"key": _key(private, licensee="From DB", today=date.today())})
    monkeypatch.setattr(settings, "license_key", _key(private, licensee="From Env", today=date.today()))
    s = client.get("/api/v1/license").json()
    assert s["licensee"] == "From Env" and s["source"] == "environment"


def test_plan_limits_cap_workspaces_and_members(client, keys, monkeypatch):
    private, public = keys
    _configure(monkeypatch, public)
    # seed already has 2 workspaces, so a 2-workspace plan is full
    client.post("/api/v1/license", json={"key": _key(private, max_workspaces=2, max_members=3, today=date.today())})
    full = client.post("/api/v1/workspaces", json={"slug": "third", "name": "Third", "brand_name": "T"})
    assert full.status_code == 402 and "2 workspace" in full.json()["detail"]

    members = client.get("/api/v1/workspaces/2/members").json()
    for i in range(3 - len(members)):
        ok = client.post("/api/v1/workspaces/2/members",
                         json={"email": f"m{i}@x.co", "full_name": f"M{i}", "role": "writer"})
        assert ok.status_code == 201
    over = client.post("/api/v1/workspaces/2/members",
                       json={"email": "extra@x.co", "full_name": "Extra", "role": "writer"})
    assert over.status_code == 402 and "3 member" in over.json()["detail"]

    client.post("/api/v1/license", json={"key": _key(private, plan="consultancy", days=None, today=date.today())})
    assert client.post("/api/v1/workspaces",
                       json={"slug": "third", "name": "Third", "brand_name": "T"}).status_code == 201


def test_limits_not_applied_when_enforcement_is_off(client):
    for i in range(3):
        assert client.post(
            "/api/v1/workspaces", json={"slug": f"w{i}", "name": f"W{i}", "brand_name": "B"}
        ).status_code == 201


def test_license_page_renders(client):
    page = client.get("/app/license")
    assert page.status_code == 200 and "Activate a licence key" in page.text
    assert "licBanner" in client.get("/app").text


def test_admin_cli_keygen_issue_inspect_roundtrip(tmp_path, capsys, monkeypatch):
    out = tmp_path / "private.pem"
    assert license_admin.main(["keygen", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    public = next(line.split("=", 1)[1] for line in printed.splitlines() if line.startswith("LICENSE_PUBLIC_KEY="))
    assert oct(out.stat().st_mode)[-3:] == "600"
    assert license_admin.main(["keygen", "--out", str(out)]) == 1  # refuses to overwrite

    assert license_admin.main(
        ["issue", "--private-key", str(out), "--licensee", "Zed Co", "--plan", "starter", "--days", "10"]
    ) == 0
    key = capsys.readouterr().out.strip()
    assert license_admin.main(["inspect", key, "--public-key", public]) == 0
    shown = capsys.readouterr().out
    assert "licensee: Zed Co" in shown and "max_workspaces: 1" in shown
    _, other_public = lic.generate_keypair()
    assert license_admin.main(["inspect", key, "--public-key", other_public]) == 1
