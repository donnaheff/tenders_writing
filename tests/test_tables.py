from bid_studio.services import service_templates as tpl

BASE = "/api/v1/services"


def make(client, doc_type, **kw):
    r = client.post(f"{BASE}/projects", json={"doc_type": doc_type, "title": "Table doc", "workspace_id": 1, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_catalogue_flags_tables_and_notice(client):
    cat = {t["key"]: t for t in client.get(f"{BASE}/templates").json()}
    assert cat["soa"]["table"] and cat["soa"]["notice"]
    assert cat["runbook"]["table"] is False and cat["ropa"]["table"]


def test_soa_has_93_fixed_rows_and_conditional_rule(client):
    d = make(client, "soa")
    assert len(d["items"]) == 93 and d["table"]
    pid = d["id"]
    assert client.post(f"{BASE}/projects/{pid}/rows").status_code == 422  # fixed
    rows = d["items"]
    rows[0].update(applicable="no", status="not applicable")
    r = client.put(f"{BASE}/projects/{pid}", json={"items": rows})
    assert r.status_code == 200
    blockers = r.json()["readiness"]["blockers"]
    assert any("Justification is needed" in b for b in blockers)
    rows[0]["justification"] = "Out of scope per risk assessment"
    r = client.put(f"{BASE}/projects/{pid}", json={"items": rows})
    assert r.json()["items"][0]["justification"]


def test_soa_rejects_structure_changes_and_readonly_edits(client):
    d = make(client, "soa")
    pid, rows = d["id"], d["items"]
    assert client.put(f"{BASE}/projects/{pid}", json={"items": rows[:-1]}).status_code == 422
    original = rows[0]["control"]
    rows[0]["control"] = "tampered"
    r = client.put(f"{BASE}/projects/{pid}", json={"items": rows})
    assert r.json()["items"][0]["control"] == original
    rows[1]["applicable"] = "maybe"
    assert client.put(f"{BASE}/projects/{pid}", json={"items": rows}).status_code == 422


def test_ropa_add_rows_readiness_export(client):
    d = make(client, "ropa")
    pid = d["id"]
    assert d["items"] == [] and any("No" in b for b in d["readiness"]["blockers"])
    d = client.post(f"{BASE}/projects/{pid}/rows").json()
    assert d["items"][0]["id"] == "R1"
    d = client.post(f"{BASE}/projects/{pid}/rows").json()
    assert [r["id"] for r in d["items"]] == ["R1", "R2"]
    assert not d["readiness"]["ready"]
    row = d["items"][0]
    row.update(activity="Payroll", purpose="Pay staff", role="controller", subjects="Employees",
               data="Name, bank details", basis="contract", retention="6 years")
    r = client.put(f"{BASE}/projects/{pid}", json={"items": [row, d["items"][1]]}).json()
    assert r["stats"]["complete"] == 1
    r = client.put(f"{BASE}/projects/{pid}", json={"items": [row]}).json()
    assert r["readiness"]["ready"]
    md = client.get(f"{BASE}/projects/{pid}/export").json()["markdown"]
    assert "| Payroll |" in md and "Processing activity" in md


def test_table_assistant_on_free_text_column_only(client):
    d = make(client, "ropa")
    pid = d["id"]
    d = client.post(f"{BASE}/projects/{pid}/rows").json()
    rid = d["items"][0]["id"]
    ok = client.post(f"{BASE}/projects/{pid}/assistant", json={"action": "draft", "target_id": rid, "field": "purpose"})
    assert ok.status_code == 200
    bad = client.post(f"{BASE}/projects/{pid}/assistant", json={"action": "draft", "target_id": rid, "field": "role"})
    assert bad.status_code == 404


def test_section_templates_with_notices_and_kinds(client):
    for key in ("runbook", "dpia", "prd", "model_card", "capa_8d", "installation_manual"):
        assert tpl.TYPES[key]["sections"]
    assert tpl.TYPES["competitive_analysis"]["references"]
    d = make(client, "dpia")
    assert d["notice"] and len(d["sections"]) == 7
