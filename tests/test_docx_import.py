import io
import zipfile

from docx import Document

from bid_studio.services import docx_import
from tests.test_doc_services import create, url


def make_docx(build) -> bytes:
    doc = Document()
    build(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def sample() -> bytes:
    def build(doc):
        doc.add_paragraph("Preamble before any heading is ignored.")
        doc.add_heading("Context", level=1)
        p = doc.add_paragraph("We run ")
        p.add_run("two").bold = True
        p.add_run(" regions.")
        doc.add_heading("Options considered", level=1)
        doc.add_paragraph("Option A", style="List Bullet")
        doc.add_paragraph("Option B", style="List Bullet")
        doc.add_heading("Option detail", level=2)
        doc.add_paragraph("Cost comparison below.")
        t = doc.add_table(rows=2, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "Option", "Cost"
        t.cell(1, 0).text, t.cell(1, 1).text = "A", "10"
        doc.add_heading("Decision", level=1)
        doc.add_paragraph("We will use option A.")
        doc.add_heading("Appendix", level=1)
        doc.add_paragraph("Something else.")
    return make_docx(build)


def post(client, pid, data, **params):
    q = "&".join(f"{k}={str(v).lower()}" for k, v in params.items())
    return client.post(url(pid, f"/import?{q}"), content=data, headers={"Content-Type": "application/octet-stream"})


def test_outline_and_mapping():
    blocks = docx_import.outline(sample())
    assert [b["heading"] for b in blocks] == ["Context", "Options considered", "Option detail", "Decision", "Appendix"]
    assert "**two**" in blocks[0]["text"] and "- Option A" in blocks[1]["text"]
    assert "| Option | Cost |" in blocks[2]["text"]


def test_dry_run_then_apply_skips_existing_text(client):
    d = create(client, "adr")
    pid = d["id"]
    r = post(client, pid, sample(), dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    titles = {s["title"]: s for s in body["sections"]}
    assert set(titles) == {"Context", "Options considered", "Decision"} and not any(s["skipped"] for s in body["sections"])
    assert [u["heading"] for u in body["unmatched"]] == ["Appendix"] and body["applied"] == 0
    assert all(not s["text"] for s in client.get(url(pid)).json()["sections"])  # dry run changed nothing

    applied = post(client, pid, sample(), dry_run=False).json()
    assert applied["applied"] == 3
    secs = {s["title"]: s["text"] for s in client.get(url(pid)).json()["sections"]}
    assert "**two**" in secs["Context"] and "**Option detail**" in secs["Options considered"]
    assert "| A | 10 |" in secs["Options considered"] and secs["Decision"] == "We will use option A."

    again = post(client, pid, sample(), dry_run=False).json()
    assert again["applied"] == 0 and all("already has text" in s["skipped"] for s in again["sections"])
    forced = post(client, pid, sample(), dry_run=False, overwrite=True).json()
    assert forced["applied"] == 3


def test_import_rejects_bad_input(client):
    d = create(client, "adr")
    pid = d["id"]
    assert post(client, pid, b"not a zip").status_code == 422
    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as z:
        z.writestr("hello.txt", "x")
    assert post(client, pid, plain.getvalue()).status_code == 422
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"0" * (docx_import.MAX_UNZIPPED + 1))
    assert len(bomb.getvalue()) < docx_import.MAX_BYTES
    assert "too large" in post(client, pid, bomb.getvalue()).json()["detail"]
    assert post(client, pid, b"0" * (docx_import.MAX_BYTES + 1)).status_code in (413, 422)
    assert post(client, create(client, "soa")["id"], sample()).status_code == 422  # table document
    assert post(client, create(client, "faq", questions="How?")["id"], sample()).status_code == 422
    assert post(client, 99999, sample()).status_code == 404


def test_import_is_blocked_when_locked_but_dry_run_works(client):
    d = create(client, "adr")
    pid = d["id"]
    secs = [{**s, "text": "Complete section text."} for s in d["sections"]]
    client.put(url(pid), json={"sections": secs})
    assert client.post(url(pid, "/submit-quality")).status_code == 200
    assert post(client, pid, sample(), dry_run=True).status_code == 200
    assert post(client, pid, sample(), dry_run=False, overwrite=True).status_code == 409
