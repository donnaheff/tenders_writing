from bid_studio.services import packs
from bid_studio.services import service_templates as tpl

BASE = "/api/v1/services"


def test_every_pack_document_exists_and_needs_no_pasted_input():
    for key, pack in packs.PACKS.items():
        assert pack["types"] == list(dict.fromkeys(pack["types"])), key
        for t in pack["types"]:
            assert t in tpl.TYPES, (key, t)
            assert tpl.TYPES[t].get("items") not in ("questions", "reviews", "copy"), (key, t)


def test_list_and_create_pack(client):
    cat = client.get(f"{BASE}/packs").json()
    assert {p["key"] for p in cat} == set(packs.PACKS)
    r = client.post(f"{BASE}/packs/iso27001_starter/create", json={"name": "Acme ISMS", "client_name": "Acme"})
    assert r.status_code == 201, r.text
    made = r.json()["projects"]
    assert len(made) == 7 and made[0]["title"].startswith("Acme ISMS: ")
    soa = next(m for m in made if m["doc_type"] == "soa")
    assert len(client.get(f"{BASE}/projects/{soa['id']}").json()["items"]) == 93
    listed = client.get(f"{BASE}/projects").json()
    assert len(listed) >= 7


def test_pack_links_only_to_types_that_accept_them(client):
    from tests.test_studio import _proposal

    pid = _proposal(client)["id"]
    r = client.post(f"{BASE}/packs/funder_reporting/create", json={"name": "Report set", "proposal_id": pid})
    assert r.status_code == 201, r.text
    by_type = {m["doc_type"]: client.get(f"{BASE}/projects/{m['id']}").json() for m in r.json()["projects"]}
    assert by_type["funder_final_report"]["proposal_id"] == pid
    assert by_type["lay_summary"]["proposal_id"] is None


def test_pack_errors_create_nothing(client):
    assert client.post(f"{BASE}/packs/nope/create", json={"name": "Whatever"}).status_code == 404
    before = len(client.get(f"{BASE}/projects").json())
    assert client.post(f"{BASE}/packs/funder_reporting/create", json={"name": "Set", "proposal_id": 9999}).status_code == 404
    assert client.post(f"{BASE}/packs/privacy_pack/create", json={"name": "Set", "workspace_id": 77}).status_code == 404
    assert len(client.get(f"{BASE}/projects").json()) == before
