"""Render the Markdown subset this app produces into Word (.docx) and PDF files."""

import io
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt
from fpdf import FPDF

_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*])|(?<!\w)_[^_\s][^_]*?_(?!\w))")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts")


def clean(text: str) -> str:
    return _CTRL.sub("", text)


def runs(text: str) -> list[tuple[str, str]]:
    """Split inline Markdown into (text, style) runs; style is '', 'b', 'i' or 'c'."""
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], ""))
        tok = m.group(0)
        if tok.startswith("**"):
            out.append((tok[2:-2], "b"))
        elif tok.startswith("`"):
            out.append((tok[1:-1], "c"))
        else:
            out.append((tok[1:-1], "i"))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], ""))
    return out or [("", "")]


def plain(text: str) -> str:
    return "".join(t for t, _ in runs(text))


def _cells(line: str) -> list[str]:
    parts = re.split(r"(?<!\\)\|", line.strip())
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return [c.strip().replace("\\|", "|") for c in parts]


def parse(md: str) -> list[dict[str, Any]]:
    """Blocks: heading(level,text), para(text), ul/ol(items), table(rows, header), quote(text), rule."""
    blocks: list[dict[str, Any]] = []
    lines = clean(md).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if m := re.match(r"^(#{1,4})\s+(.*)$", s):
            blocks.append({"t": "heading", "level": len(m.group(1)), "text": m.group(2)})
        elif re.match(r"^(-{3,}|\*{3,})$", s):
            blocks.append({"t": "rule"})
        elif s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            header = _cells(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = _cells(lines[i])
                rows.append((row + [""] * len(header))[: len(header)])
                i += 1
            blocks.append({"t": "table", "header": header, "rows": rows})
            continue
        elif re.match(r"^([-*+])\s+", s) or re.match(r"^\d+[.)]\s+", s):
            ordered = bool(re.match(r"^\d+[.)]\s+", s))
            items = []
            while i < len(lines) and (m := re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", lines[i])):
                items.append(m.group(1))
                i += 1
            blocks.append({"t": "ol" if ordered else "ul", "items": items})
            continue
        elif s.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append({"t": "quote", "text": " ".join(quote)})
            continue
        else:
            para = [s]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|[-*+]\s|\d+[.)]\s|\||>)", lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            blocks.append({"t": "para", "text": " ".join(para)})
            continue
        i += 1
    return blocks


# ------------------------------------------------------------------ Word

def _add_runs(paragraph, text: str) -> None:
    for t, style in runs(text):
        r = paragraph.add_run(t)
        r.bold = style == "b"
        r.italic = style == "i"
        if style == "c":
            r.font.name = "Consolas"


def to_docx(md: str, title: str = "") -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    if title:
        doc.core_properties.title = title[:250]
    for b in parse(md):
        t = b["t"]
        if t == "heading":
            doc.add_heading(plain(b["text"]), level=min(b["level"], 4) if b["level"] > 1 else 0 if not doc.paragraphs else 1)
        elif t == "para":
            _add_runs(doc.add_paragraph(), b["text"])
        elif t in ("ul", "ol"):
            for item in b["items"]:
                _add_runs(doc.add_paragraph(style="List Bullet" if t == "ul" else "List Number"), item)
        elif t == "quote":
            p = doc.add_paragraph(style="Intense Quote")
            _add_runs(p, b["text"])
        elif t == "table":
            table = doc.add_table(rows=1, cols=len(b["header"]), style="Light Grid Accent 1")
            for c, h in zip(table.rows[0].cells, b["header"], strict=False):
                c.text = ""
                _add_runs(c.paragraphs[0], f"**{h}**" if h else "")
            for row in b["rows"]:
                cells = table.add_row().cells
                for c, v in zip(cells, row, strict=False):
                    c.text = ""
                    _add_runs(c.paragraphs[0], v)
            doc.add_paragraph()
        elif t == "rule":
            doc.add_paragraph("_" * 40)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ PDF

def _font_dir() -> Path | None:
    for d in _FONT_DIRS:
        if (Path(d) / "DejaVuSans.ttf").exists() and (Path(d) / "DejaVuSans-Bold.ttf").exists():
            return Path(d)
    return None


def to_pdf(md: str, title: str = "") -> bytes:
    blocks = parse(md)
    wide = any(b["t"] == "table" and len(b["header"]) >= 6 for b in blocks)
    pdf = FPDF(orientation="L" if wide else "P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    fonts = _font_dir()
    unicode_ok = fonts is not None
    italics: set[str] = set()
    if fonts:
        pdf.add_font("DV", "", str(fonts / "DejaVuSans.ttf"))
        pdf.add_font("DV", "B", str(fonts / "DejaVuSans-Bold.ttf"))
        for style, name in (("I", "DejaVuSans-Oblique.ttf"), ("BI", "DejaVuSans-BoldOblique.ttf")):
            if (fonts / name).exists():
                pdf.add_font("DV", style, str(fonts / name))
                italics.add(style)
        family = "DV"
    else:
        family = "Helvetica"
    if title:
        pdf.set_title(title[:250])

    def txt(s: str) -> str:
        return s if unicode_ok else s.encode("latin-1", "replace").decode("latin-1")

    def font(style: str = "", size: float = 10.5) -> None:
        if "I" in style and (family != "DV" or style not in italics):
            style = style.replace("I", "") if family == "DV" else style
        pdf.set_font(family, style, size)

    def write_runs(text: str, size: float = 10.5, h: float = 5.6) -> None:
        for t, style in runs(text):
            font({"b": "B", "i": "I", "c": ""}.get(style, ""), size)
            pdf.write(h, txt(t))
        pdf.ln(h)

    pdf.add_page()
    first = True
    sizes = {1: 20, 2: 15, 3: 12.5, 4: 11}
    for b in blocks:
        t = b["t"]
        if t == "heading":
            font("B", sizes[b["level"]])
            pdf.ln(0 if first else 3)
            pdf.multi_cell(0, sizes[b["level"]] * 0.5, txt(plain(b["text"])), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
            first = False
        elif t == "para":
            write_runs(b["text"])
            pdf.ln(2)
        elif t in ("ul", "ol"):
            for n, item in enumerate(b["items"], 1):
                font("", 10.5)
                pdf.set_x(pdf.l_margin + 4)
                pdf.write(5.6, txt("•  " if t == "ul" else f"{n}.  "))
                write_runs(item)
            pdf.ln(1.5)
        elif t == "quote":
            pdf.set_x(pdf.l_margin + 6)
            write_runs(b["text"])
            pdf.ln(2)
        elif t == "table":
            font("", 8.5)
            with pdf.table(first_row_as_headings=True, text_align="LEFT", line_height=4.4,
                           padding=1, repeat_headings=1) as table:
                head = table.row()
                for h in b["header"]:
                    head.cell(txt(plain(h)))
                for r in b["rows"]:
                    row = table.row()
                    for v in r:
                        row.cell(txt(plain(v)))
            pdf.ln(3)
        elif t == "rule":
            pdf.ln(1)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
    return bytes(pdf.output())


MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "document"


def file_response(fmt: str, md: str, title: str):
    from fastapi import Response

    data = to_docx(md, title) if fmt == "docx" else to_pdf(md, title)
    return Response(content=data, media_type=MEDIA[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{slug(title)}.{fmt}"'})
