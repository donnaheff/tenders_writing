import httpx
import pytest
from tests.test_doc_services import create, url

from bid_studio.config import settings
from bid_studio.services import assistant as ai
from bid_studio.services import checklists, reviews
from bid_studio.services import references as refs
from bid_studio.services import service_templates as tpl

RESEARCH = ["research_manuscript", "literature_review", "research_protocol", "thesis_proposal",
            "conference_abstract", "systematic_review_protocol", "policy_brief",
            "research_impact_case_study", "journal_cover_letter"]

ARTICLE = {"id": "R1", "kind": "article", "authors": ["LeCun, Y.", "Bengio, Y.", "Hinton, G."], "year": 2015,
           "title": "Deep learning", "container": "Nature", "volume": "521", "issue": "7553", "pages": "436-444",
           "doi": "10.1038/nature14539", "verified": True}


# ---------------------------------------------------------------- templates

@pytest.mark.parametrize("key", RESEARCH)
def test_research_templates_are_well_formed(key):
    t = tpl.TYPES[key]
    ids = [s[0] for s in t["sections"]]
    assert t["kind"] == "research" and len(ids) == len(set(ids)) and len(ids) >= 4 - (key == "conference_abstract")
    assert all(title and len(prompt) > 40 for _, title, prompt in t["sections"])


def test_manuscript_prompts_forbid_unsourced_claims_and_mention_ai_disclosure():
    ms = " ".join(p for _, _, p in tpl.TYPES["research_manuscript"]["sections"]).lower()
    assert "[r#]" in ms and "disclose any ai" in ms
    assert tpl.TYPES["research_manuscript"]["references"] and tpl.TYPES["white_paper"]["references"]
    assert not tpl.TYPES["sop"].get("references")


@pytest.mark.parametrize("key", [k for k in RESEARCH if k != "journal_cover_letter"])
def test_research_documents_create_with_an_empty_reference_list(client, key):
    p = create(client, key)
    assert p["research"] and p["references_enabled"] and p["refs"] == {"style": "apa", "items": []}
    assert not p["reviews"] and not p["checklist"]


# ---------------------------------------------------------------- reference library

def test_apa_and_vancouver_formatting():
    ref = refs.Ref(**ARTICLE)
    assert refs.format_reference(ref, "apa") == "LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436-444. https://doi.org/10.1038/nature14539"
    assert refs.format_reference(ref, "vancouver") == "LeCun Y, Bengio Y, Hinton G. Deep learning. Nature. 2015;521(7553):436-444. Available from: https://doi.org/10.1038/nature14539"
    many = refs.Ref(id="R2", authors=[f"Author{i}, A." for i in range(8)], year=2020, title="Big team", container="J", pages="1-2")
    assert refs.format_reference(many, "vancouver").startswith("Author0 A, Author1 A, Author2 A, Author3 A, Author4 A, Author5 A, et al.")
    book = refs.Ref(id="R3", kind="book", authors=["Smith, J."], year=None, title="A book", publisher="Press")
    assert refs.format_reference(book, "apa") == "Smith, J. (n.d.). A book. Press."


def test_normalise_doi_and_author_names():
    for raw in ("https://doi.org/10.1/abc", "doi:10.1/abc", " 10.1/abc ", "http://dx.doi.org/10.1/abc"):
        assert refs.normalise_doi(raw) == "10.1/abc"
    assert refs.author_name("Jean-Paul", "Sartre") == "Sartre, J. P."
    assert refs.author_name("", "OpenAI") == "OpenAI"


def test_check_finds_format_and_citation_problems():
    lst = refs.RefList(items=[
        refs.Ref(id="R1", title="", authors=[], doi="10.12/ok"),
        refs.Ref(id="R2", title="Same", authors=["A, B."], year=2020, container="J", doi="not-a-doi", checked=True),
        refs.Ref(id="R3", title="Dup doi", authors=["A, B."], year=2020, container="J", doi="10.12/ok", checked=True),
        refs.Ref(id="R4", kind="web", title="Web page", authors=["A, B."], year=2021, checked=True),
    ])
    msgs = " | ".join(f"{c['id']}:{c['message']}" for c in refs.check(lst, ["As shown [R2] and [R9]. See [R3]."]))
    assert "R1:Missing title." in msgs and "R1:No authors listed." in msgs
    assert "R2:The DOI is not in a valid format" in msgs
    assert "R3:Same DOI as R1." in msgs
    assert "R4:Web sources need a URL." in msgs and "R4:In the list but never cited" in msgs
    assert "R9:Cited as [R9] in the text but not in the reference list." in msgs
    assert refs.cited_ids(["[R1] and [R12]", "none"]) == {"R1", "R12"}


def test_lookup_doi_parses_crossref(monkeypatch):
    payload = {"message": {"title": ["Deep learning"], "author": [{"given": "Yann", "family": "LeCun"}, {"name": "Some Consortium"}],
                           "issued": {"date-parts": [[2015, 5]]}, "container-title": ["Nature"], "volume": "521",
                           "issue": "7553", "page": "436-444", "publisher": "Springer", "type": "journal-article",
                           "DOI": "10.1038/nature14539", "URL": "http://dx.doi.org/10.1038/nature14539"}}
    calls = {}

    def fake_get(u, headers, timeout):
        calls.update(url=u, headers=headers)
        return httpx.Response(200, json=payload, request=httpx.Request("GET", u))

    monkeypatch.setattr(httpx, "get", fake_get)
    out = refs.lookup_doi("https://doi.org/10.1038/nature14539")
    assert calls["url"] == refs.CROSSREF_URL + "10.1038/nature14539"
    assert out["authors"] == ["LeCun, Y.", "Some Consortium"] and out["year"] == 2015 and out["kind"] == "article"
    assert out["verified"] is True and out["container"] == "Nature"
    with pytest.raises(ValueError):
        refs.lookup_doi("not a doi")
    monkeypatch.setattr(httpx, "get", lambda u, headers, timeout: httpx.Response(404, request=httpx.Request("GET", u)))
    with pytest.raises(LookupError):
        refs.lookup_doi("10.9999/nope")


# ---------------------------------------------------------------- reference endpoints and readiness

def fill(client, pid, **texts):
    secs = client.get(url(pid)).json()["sections"]
    for s in secs:
        s["text"] = texts.get(s["id"], f"Written content for {s['title']}.")
    return client.put(url(pid), json={"sections": secs}).json()


def test_reference_list_saves_formats_checks_and_gates_readiness(client):
    p = create(client, "research_manuscript")
    pid = p["id"]
    fill(client, pid, introduction="Deep learning has transformed the field [R1], as others show [R2].")
    state = client.get(url(pid)).json()
    assert "Cited but missing from the reference list: R1, R2" in state["readiness"]["blockers"]

    saved = client.put(url(pid, "/references"), json={"style": "vancouver", "items": [ARTICLE]}).json()
    assert saved["refs"]["style"] == "vancouver" and saved["refs"]["items"][0]["doi"] == "10.1038/nature14539"
    ready = saved["readiness"]
    assert "Cited but missing from the reference list: R2" in ready["blockers"]

    second = {**ARTICLE, "id": "R2", "title": "Other work", "doi": "https://doi.org/10.1000/other", "verified": False, "checked": True}
    out = client.put(url(pid, "/references"), json={"style": "apa", "items": [ARTICLE, second]}).json()
    assert out["refs"]["items"][1]["doi"] == "10.1000/other"  # URL form is normalised
    assert out["readiness"]["ready"] is True
    assert not any("missing" in b for b in out["readiness"]["blockers"])

    md = client.get(url(pid, "/export")).json()["markdown"]
    assert "## References" in md and "- **[R1]** LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436-444." in md

    bad = {**ARTICLE, "id": "R3", "doi": "garbage"}
    res = client.put(url(pid, "/references"), json={"style": "apa", "items": [ARTICLE, second, bad]}).json()
    assert "The reference list has errors to fix" in res["readiness"]["blockers"]
    assert client.put(url(pid, "/references"), json={"style": "chicago", "items": []}).status_code == 422
    assert client.put(url(pid, "/references"), json={"style": "apa", "items": [{**ARTICLE, "year": 5}]}).status_code == 422
    assert client.put(url(create(client, "sop")["id"], "/references"), json={"style": "apa", "items": []}).status_code == 409


def test_unverified_references_warn_but_do_not_block(client):
    p = create(client, "literature_review")
    fill(client, p["id"], themes="Evidence agrees [R1].")
    unverified = {**ARTICLE, "verified": False, "checked": False}
    res = client.put(url(p["id"], "/references"), json={"style": "apa", "items": [unverified]}).json()
    assert res["readiness"]["ready"] is True
    assert any("not verified or checked" in w for w in res["readiness"]["warnings"])


def test_citation_needed_placeholders_block_submission(client):
    p = create(client, "policy_brief")
    res = fill(client, p["id"], evidence="Rates doubled [CITATION NEEDED].")
    assert "Contains [CITATION NEEDED] placeholders" in res["readiness"]["blockers"]
    res = fill(client, p["id"])
    assert "Contains [CITATION NEEDED] placeholders" not in res["readiness"]["blockers"]


def test_doi_lookup_endpoint_handles_every_outcome(client, monkeypatch):
    pid = create(client, "research_manuscript")["id"]
    from bid_studio.services import references as r

    monkeypatch.setattr(r, "lookup_doi", lambda doi: {"title": "Found", "doi": doi, "verified": True})
    ok = client.post(url(pid, "/references/lookup"), json={"doi": "10.1/abc"})
    assert ok.status_code == 200 and ok.json()["title"] == "Found"
    # lookup never saves anything
    assert client.get(url(pid)).json()["refs"]["items"] == []

    def boom(exc):
        def f(doi):
            raise exc
        return f

    monkeypatch.setattr(r, "lookup_doi", boom(ValueError("That does not look like a DOI")))
    assert client.post(url(pid, "/references/lookup"), json={"doi": "xyz"}).status_code == 422
    monkeypatch.setattr(r, "lookup_doi", boom(LookupError("Crossref has no record")))
    assert client.post(url(pid, "/references/lookup"), json={"doi": "10.1/x"}).status_code == 404
    monkeypatch.setattr(r, "lookup_doi", boom(httpx.ConnectError("down")))
    bad = client.post(url(pid, "/references/lookup"), json={"doi": "10.1/x"})
    assert bad.status_code == 502 and "by hand" in bad.json()["detail"]
    assert client.post(url(create(client, "sop")["id"], "/references/lookup"), json={"doi": "10.1/x"}).status_code == 409


def test_assistant_only_cites_listed_references_and_is_told_never_to_invent(client, monkeypatch):
    p = create(client, "research_manuscript")
    client.put(url(p["id"], "/references"), json={"style": "apa", "items": [ARTICLE]})
    offline = client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "introduction"}).json()
    assert offline["provider"] == "offline" and "[CITATION NEEDED" in offline["text"]

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "Text [R1].")
    client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "introduction"})
    assert "[R1] LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning." in seen["p"]
    assert "do not cite anything else" in seen["p"]
    assert "Never write, invent or complete a citation" in ai.SYSTEM_PROMPT and "[CITATION NEEDED]" in ai.SYSTEM_PROMPT


# ---------------------------------------------------------------- response to reviewers

PASTED = """Editor: Please shorten the discussion.
Reviewer 1: 1. The sample size is not justified.
- Figure 2 is hard to read.
R2: The statistics need a correction for multiple testing.
Reviewer B) Please cite the earlier trial.
"""


def test_parse_comments_prefixes_and_numbering():
    items = reviews.parse_comments(PASTED)
    assert [(i["reviewer"], i["comment"]) for i in items] == [
        ("Editor", "Please shorten the discussion."),
        ("Reviewer 1", "The sample size is not justified."),
        ("Reviewer 1", "Figure 2 is hard to read."),
        ("Reviewer 2", "The statistics need a correction for multiple testing."),
        ("Reviewer B", "Please cite the earlier trial."),
    ]
    assert reviews.parse_comments("") == [] and reviews.parse_comments("a\n  \n") == []


def make_response(client, **kw):
    return create(client, "reviewer_response", questions=PASTED, **kw)


def test_reviewer_response_flow_readiness_and_export(client):
    p = make_response(client)
    pid = p["id"]
    assert p["reviews"] and [i["id"] for i in p["items"]] == ["C1", "C2", "C3", "C4", "C5"]
    assert p["stats"] == {"total": 5, "answered": 0, "resolved": 0}
    assert p["readiness"]["blockers"][0].startswith("No response yet to: C1, C2, C3, C4, C5")
    assert client.post("/api/v1/services/projects", json={"workspace_id": 1, "doc_type": "reviewer_response", "title": "No comments"}).status_code == 422

    items = p["items"]
    for it in items:
        it.update(response=f"Thank you. We addressed {it['id']}.", status="addressed", change="Methods, para 2")
    items[2].update(status="disagree", change="")
    secs = p["sections"]
    secs[0]["text"] = "Dear Editor, thank you for the careful reviews."
    done = client.put(url(pid), json={"items": items, "sections": secs}).json()
    assert done["readiness"]["ready"] is True and done["stats"]["resolved"] == 5

    items[0]["change"] = ""
    warn = client.put(url(pid), json={"items": items}).json()["readiness"]
    assert any("where the change was made" in w for w in warn["warnings"])
    items[1]["status"] = "pending"
    assert client.put(url(pid), json={"items": items}).json()["readiness"]["ready"] is False

    more = client.post(url(pid, "/questions"), json={"questions": "Reviewer 3: Please add a limitations paragraph."}).json()
    assert more["items"][-1]["id"] == "C6" and more["items"][-1]["reviewer"] == "Reviewer 3"

    md = client.get(url(pid, "/export")).json()["markdown"]
    assert "## Reviewer 1" in md and "**Comment C2:** The sample size is not justified." in md
    assert "**Response:** Thank you. We addressed C2." in md and "**Change made:** Methods, para 2" in md
    assert md.index("## Editor") < md.index("## Reviewer 1") < md.index("## Reviewer 2")

    bad = [{**items[0], "status": "maybe"}]
    assert client.put(url(pid), json={"items": bad}).status_code == 422


def test_reviewer_assistant_gets_the_comment_and_is_told_not_to_invent_changes(client, monkeypatch):
    p = make_response(client)
    items = p["items"]
    items[1]["change"] = "Added a power calculation to Methods"
    client.put(url(p["id"]), json={"items": items})
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}
    monkeypatch.setattr(ai, "call_claude", lambda prompt: seen.setdefault("p", prompt) and "We thank the reviewer.")
    res = client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "C2"}).json()
    assert res["text"] == "We thank the reviewer."
    for must in ("The sample size is not justified.", "Do not claim a change was made unless the notes say so",
                 "Change made: Added a power calculation to Methods", "Reviewer 1, comment C2"):
        assert must in seen["p"], must
    assert client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "C99"}).status_code == 404
    assert client.post(url(p["id"], "/assistant"), json={"action": "draft", "target_id": "letter"}).status_code == 200


# ---------------------------------------------------------------- reporting checklists

@pytest.mark.parametrize("key,expected", [("consort_checklist", 37), ("prisma_checklist", 42), ("strobe_checklist", 33)])
def test_checklists_have_the_expected_items(client, key, expected):
    items = checklists.new_items(key)
    assert len(items) == expected and len({i["id"] for i in items}) == expected
    assert all(i["reported"] == "unchecked" and i["text"] and i["section"] for i in items)
    p = create(client, key)
    assert p["checklist"] and len(p["items"]) == expected and p["stats"]["unchecked"] == expected
    assert p["readiness"]["blockers"] == [f"{expected} item(s) not yet answered"]


def test_checklist_progress_validation_and_export(client):
    p = create(client, "consort_checklist")
    pid = p["id"]
    items = p["items"]
    for it in items:
        it["reported"] = "yes"
        it["location"] = "Methods"
    items[0]["reported"] = "no"
    items[1]["reported"] = "na"
    items[2]["location"] = ""
    res = client.put(url(pid), json={"items": items}).json()
    assert res["readiness"]["ready"] is True and res["stats"] == {"total": 37, "unchecked": 0, "yes": 35, "no": 1, "na": 1}
    w = res["readiness"]["warnings"]
    assert any("marked 'no' have no explanation" in x for x in w) and any("do not say where" in x for x in w)

    assert client.put(url(pid), json={"items": items[:-1]}).status_code == 422
    assert client.put(url(pid), json={"items": [{**items[0], "reported": "maybe"}] + items[1:]}).status_code == 422
    reordered = list(reversed(items))
    assert client.put(url(pid), json={"items": reordered}).status_code == 422

    md = client.get(url(pid, "/export")).json()["markdown"]
    assert "Paraphrased summary" in md and "official checklist" in md
    assert "| 12a Statistical methods for primary and secondary outcomes | Methods | yes | Methods |" in md
    assert client.post(url(pid, "/assistant"), json={"action": "draft", "target_id": "I1a"}).status_code == 422


def test_research_job_type_links_only_research_documents(client):
    from tests.test_marketplace import job_ws, new_client, register

    c = new_client(client)
    register(c, "res@clients.test", "client", "Ray", "Ray Lab")
    ws = job_ws({"client": c})
    mk = lambda t: client.post("/api/v1/services/projects", json={"workspace_id": ws, "doc_type": t, "title": "Research doc", "questions": "Reviewer 1: A comment here"}).json()["id"]  # noqa: E731
    paper, resp, report = mk("research_manuscript"), mk("reviewer_response"), mk("technical_report")
    post = lambda **kw: c.post("/api/v1/market/jobs", json={"title": "Edit my paper please", **kw})  # noqa: E731
    assert post(job_type="research_writing", doc_project_id=paper).status_code == 201
    assert post(job_type="research_writing", doc_project_id=resp).status_code == 201
    assert post(job_type="research_writing", doc_project_id=report).status_code == 422
    assert post(job_type="expert_docs", doc_project_id=paper).status_code == 422
