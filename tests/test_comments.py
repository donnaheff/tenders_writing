from tests.test_doc_services import create, url
from tests.test_job_types import M, approve_all, job_ws, make_doc_project, people  # noqa: F401


def test_comment_lifecycle_and_readiness_warning(client):
    d = create(client, "runbook")
    pid = d["id"]
    sec = d["sections"][0]["id"]
    assert client.post(url(pid, "/comments"), json={"body": "hi"}).status_code == 422  # no name
    assert client.post(url(pid, "/comments"), json={"body": "x", "author_name": "Sam", "target": "nope"}).status_code == 422
    r = client.post(url(pid, "/comments"), json={"body": "Add the on-call rota", "author_name": "Sam", "target": sec})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.post(url(pid, "/comments"), json={"body": "   ", "author_name": "Sam"}).status_code == 422
    client.post(url(pid, "/comments"), json={"body": "General note", "author_name": "Sam"})
    got = client.get(url(pid))
    assert got.json()["open_comments"] == 2
    assert any("2 unresolved" in w for w in got.json()["readiness"]["warnings"])
    res = client.patch(url(pid, f"/comments/{cid}"), json={"resolved": True}).json()
    assert res["resolved"] and res["resolved_at"]
    assert client.get(url(pid)).json()["open_comments"] == 1
    assert len(client.get(url(pid, "/comments")).json()) == 2
    assert client.delete(url(pid, f"/comments/{cid}")).status_code == 204
    assert client.delete(url(pid, f"/comments/{cid}")).status_code == 404
    # a reviewer can still comment once the project is locked for quality review
    secs = [{**x, "text": "Complete text for this section."} for x in d["sections"]]
    assert client.put(url(pid), json={"sections": secs}).status_code == 200
    for c in client.get(url(pid, "/comments")).json():
        client.patch(url(pid, f"/comments/{c['id']}"), json={"resolved": True})
    assert client.post(url(pid, "/submit-quality")).status_code == 200
    assert client.put(url(pid), json={"title": "Changed"}).status_code == 409
    assert client.post(url(pid, "/comments"), json={"body": "Reviewer note", "author_name": "QA"}).status_code == 201
    other = create(client, "runbook")
    assert client.patch(url(other["id"], "/comments/999"), json={"resolved": True}).status_code == 404


def test_comments_allowed_while_locked_and_follow_job_access(people, client):  # noqa: F811
    p = people
    approve_all(p)
    proj = make_doc_project(client, job_ws(p), "sop")
    job = p["client"].post(f"{M}/jobs", json={"title": "SOP", "job_type": "technical_docs", "doc_project_id": proj}).json()
    bid = p["writer"].post(f"{M}/jobs/{job['id']}/bids", json={"price": 900}).json()
    p["client"].post(f"{M}/jobs/{job['id']}/bids/{bid['id']}/accept")
    base = f"/api/v1/services/projects/{proj}/comments"
    assert p["anon"].get(base).status_code == 401
    assert p["other_writer"].post(base, json={"body": "spy"}).status_code == 403
    mine = p["client"].post(base, json={"body": "Please expand the scope"})
    assert mine.status_code == 201 and mine.json()["author_name"]
    cid = mine.json()["id"]
    assert p["writer"].delete(f"{base}/{cid}").status_code == 403  # not the author
    assert p["writer"].patch(f"{base}/{cid}", json={"resolved": True}).json()["resolved_by"]
    assert p["admin"].delete(f"{base}/{cid}").status_code == 204
