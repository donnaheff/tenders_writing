import io

from docx import Document
from tests.test_doc_services import create, url

from bid_studio.services import render

MD = """# Title

_Prepared for Acme_ with **bold**, `code` and snake_case_word.

## Part

- one
- two **b**

1. a
2. b

| ID | Name |
| --- | --- |
| R1 | Café ✓ \\| pipe |

> quote
"""


def test_parse_blocks_and_inline_runs():
    assert [b["t"] for b in render.parse(MD)] == ["heading", "para", "heading", "ul", "ol", "table", "quote"]
    assert render.runs("a **b** `c` _d_ snake_case_word") == [
        ("a ", ""), ("b", "b"), (" ", ""), ("c", "c"), (" ", ""), ("d", "i"), (" snake_case_word", "")]
    table = render.parse(MD)[5]
    assert table["rows"] == [["R1", "Café ✓ | pipe"]]


def test_docx_and_pdf_are_valid_and_strip_control_chars():
    data = render.to_docx(MD + "\nbad\x00char\x0b here", "T")
    doc = Document(io.BytesIO(data))
    assert doc.tables[0].rows[1].cells[1].text == "Café ✓ | pipe"
    assert any("badchar here" in p.text for p in doc.paragraphs)
    pdf = render.to_pdf(MD, "T")
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def test_project_exports_for_sections_and_tables(client):
    d = create(client, "user_guide")
    r = client.get(url(d["id"], "/export.docx"))
    assert r.status_code == 200 and r.headers["content-type"] == render.MEDIA["docx"]
    assert "acme-docs.docx" in r.headers["content-disposition"]
    assert Document(io.BytesIO(r.content)).paragraphs
    r = client.get(url(d["id"], "/export.pdf"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    soa = create(client, "soa")
    r = client.get(url(soa["id"], "/export.pdf"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get(url(99999, "/export.pdf")).status_code == 404


def test_proposal_exports(client):
    from tests.test_studio import _proposal

    pid = _proposal(client)["id"]
    for fmt in ("docx", "pdf"):
        r = client.get(f"/api/v1/grants/proposals/{pid}/export.{fmt}")
        assert r.status_code == 200 and r.headers["content-type"] == render.MEDIA[fmt]
