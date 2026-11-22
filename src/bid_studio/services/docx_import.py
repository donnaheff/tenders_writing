"""Read a Word document and map its headings onto a project's sections."""

import io
import re
import zipfile
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from bid_studio.services.domain_logic import tokenize

MAX_BYTES = 5 * 1024 * 1024
MAX_UNZIPPED = 60 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_SECTION_CHARS = 60000


class DocxImportError(ValueError):
    pass


def _safe_open(data: bytes) -> Document:
    if len(data) > MAX_BYTES:
        raise DocxImportError("The file is larger than 5 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED:
                raise DocxImportError("The file is too large when unpacked")
            if "word/document.xml" not in z.namelist():
                raise DocxImportError("This is not a Word (.docx) document")
        return Document(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocxImportError("This is not a Word (.docx) document") from exc
    except DocxImportError:
        raise
    except Exception as exc:  # malformed package
        raise DocxImportError("The Word document could not be read") from exc


def _runs_md(p: Paragraph) -> str:
    out = []
    for r in p.runs:
        t = r.text
        if not t.strip():
            out.append(t)
        elif r.bold and r.italic:
            out.append(f"***{t.strip()}***")
        elif r.bold:
            out.append(f"**{t.strip()}** ")
        elif r.italic:
            out.append(f"_{t.strip()}_ ")
        else:
            out.append(t)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _heading_level(p: Paragraph) -> int | None:
    name = (p.style.name or "") if p.style is not None else ""
    if name == "Title":
        return 1
    if m := re.match(r"Heading (\d)", name):
        return int(m.group(1))
    return None


def _table_md(t: Table) -> str:
    rows = [[re.sub(r"\s+", " ", c.text).strip().replace("|", "\\|") for c in r.cells] for r in t.rows]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [(r + [""] * width)[:width] for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def outline(data: bytes) -> list[dict[str, Any]]:
    """Return [{'heading', 'level', 'text'}] in document order. Text before the first heading is dropped."""
    doc = _safe_open(data)
    blocks: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    numbered = 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            if not p.text.strip():
                continue
            level = _heading_level(p)
            if level:
                cur = {"heading": p.text.strip(), "level": level, "lines": []}
                blocks.append(cur)
                numbered = 0
                continue
            if cur is None:
                continue
            style = (p.style.name or "") if p.style is not None else ""
            text = _runs_md(p)
            if style.startswith("List Number"):
                numbered += 1
                text = f"{numbered}. {text}"
            elif style.startswith("List"):
                text = f"- {text}"
            else:
                numbered = 0
            cur["lines"].append(text)
        elif tag == "tbl" and cur is not None:
            cur["lines"].append(_table_md(Table(child, doc)))
    return [{"heading": b["heading"], "level": b["level"], "text": "\n\n".join(x for x in b["lines"] if x).strip()}
            for b in blocks]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _score(heading: str, title: str) -> float:
    a, b = _norm(heading), _norm(title)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 4 and short in long_:
        return 0.85
    ta, tb = tokenize(heading), tokenize(title)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def map_to_sections(blocks: list[dict[str, Any]], sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Assign each document heading to at most one section; deeper headings fold into their parent's text."""
    # Top-level headings: the lowest level used for headings that match something; fold the rest into them.
    best: dict[int, tuple[float, int]] = {}
    for bi, b in enumerate(blocks):
        for si, s in enumerate(sections):
            sc = _score(b["heading"], s["title"])
            if sc >= 0.6 and (si not in best or sc > best[si][0]):
                best[si] = (sc, bi)
    claimed = {bi: si for si, (_, bi) in best.items()}
    texts: dict[int, str] = {}
    unmatched: list[dict[str, Any]] = []
    parent: int | None = None
    parent_level = 0
    for bi, b in enumerate(blocks):
        if bi in claimed:
            parent, parent_level = bi, b["level"]
            texts[claimed[bi]] = b["text"]
            continue
        if parent is not None and b["level"] > parent_level:
            extra = f"**{b['heading']}**" + (f"\n\n{b['text']}" if b["text"] else "")
            si = claimed[parent]
            texts[si] = (texts[si] + "\n\n" + extra).strip()
            continue
        parent = None
        unmatched.append({"heading": b["heading"], "words": len(b["text"].split())})
    matched = [{"section_id": sections[si]["id"], "title": sections[si]["title"],
                "heading": blocks[best[si][1]]["heading"], "text": texts[si], "words": len(texts[si].split())}
               for si in sorted(texts)]
    return {"matched": matched, "unmatched": unmatched}
