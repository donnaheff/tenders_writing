"""A reference list the author controls: format checks, citation cross-checks and DOI lookup.

Nothing here ever invents a reference. Entries come from the author or from Crossref (looked up by a
DOI the author supplies), and every entry is flagged until it is verified or the author attests they
have checked the source.
"""

import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from bid_studio.config import settings

CROSSREF_URL = "https://api.crossref.org/works/"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
CITE_RE = re.compile(r"\[R(\d+)\]")
STYLES = ("apa", "vancouver")
KINDS = ("article", "book", "chapter", "report", "web", "dataset", "other")


class Ref(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    kind: Literal["article", "book", "chapter", "report", "web", "dataset", "other"] = "article"
    authors: list[str] = Field(default_factory=list, max_length=60)  # "Surname, G." each
    year: int | None = Field(default=None, ge=1000, le=2100)
    title: str = Field(default="", max_length=500)
    container: str = Field(default="", max_length=300)  # journal, book or site
    volume: str = Field(default="", max_length=40)
    issue: str = Field(default="", max_length=40)
    pages: str = Field(default="", max_length=40)
    publisher: str = Field(default="", max_length=200)
    doi: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=500)
    verified: bool = False  # DOI resolved at Crossref and the record matches
    checked: bool = False  # the author attests they have read or checked the source


class RefList(BaseModel):
    style: Literal["apa", "vancouver"] = "apa"
    items: list[Ref] = Field(default_factory=list, max_length=500)


def empty() -> dict[str, Any]:
    return RefList().model_dump()


def normalise_doi(raw: str) -> str:
    d = (raw or "").strip()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d, flags=re.I)
    return d.removeprefix("doi:").strip()


def _initials(given: str) -> str:
    return " ".join(f"{p[0]}." for p in re.split(r"[\s.\-]+", given.strip()) if p)


def author_name(given: str, family: str) -> str:
    return f"{family.strip()}, {_initials(given)}".strip().rstrip(",")


def _apa_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 20:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]
    return ", ".join(authors[:19]) + ", ... " + authors[-1]


def _vancouver_authors(authors: list[str]) -> str:
    out = []
    for a in authors[:6]:
        fam, _, ini = a.partition(",")
        out.append(f"{fam.strip()} {ini.replace('.', '').replace(' ', '').strip()}".strip())
    return ", ".join(out) + (", et al" if len(authors) > 6 else "")


def format_reference(r: Ref | dict[str, Any], style: str) -> str:
    ref = r if isinstance(r, Ref) else Ref(**r)
    doi = f"https://doi.org/{ref.doi}" if ref.doi else ref.url
    year = str(ref.year) if ref.year else "n.d."
    if style == "vancouver":
        parts = [f"{_vancouver_authors(ref.authors) or '[Author unknown]'}.", f"{ref.title.rstrip('.')}."]
        if ref.container:
            vol = f"{year};{ref.volume}" if ref.volume else year
            vol += f"({ref.issue})" if ref.issue else ""
            vol += f":{ref.pages}" if ref.pages else ""
            parts.append(f"{ref.container}. {vol}.")
        elif ref.publisher:
            parts.append(f"{ref.publisher}; {year}.")
        else:
            parts.append(f"{year}.")
        if doi:
            parts.append(f"Available from: {doi}")
        return " ".join(parts)
    authors = _apa_authors(ref.authors) or "[Author unknown]"
    text = f"{authors} ({year}). {ref.title.rstrip('.')}."
    if ref.container:
        text += f" {ref.container}"
        if ref.volume:
            text += f", {ref.volume}"
            text += f"({ref.issue})" if ref.issue else ""
        text += f", {ref.pages}." if ref.pages else "."
    elif ref.publisher:
        text += f" {ref.publisher}."
    if doi:
        text += f" {doi}"
    return text


def cited_ids(texts: list[str]) -> set[str]:
    return {f"R{n}" for t in texts for n in CITE_RE.findall(t or "")}


def check(refs: RefList, texts: list[str]) -> list[dict[str, str]]:
    """Format and consistency problems, each with a severity."""
    out: list[dict[str, str]] = []

    def add(level: str, ref_id: str, message: str) -> None:
        out.append({"level": level, "id": ref_id, "message": message})

    ids = [r.id for r in refs.items]
    if len(ids) != len(set(ids)):
        add("error", "", "Reference ids must be unique.")
    seen_doi: dict[str, str] = {}
    seen_title: dict[str, str] = {}
    for r in refs.items:
        if not r.title.strip():
            add("error", r.id, "Missing title.")
        if not r.authors:
            add("warning", r.id, "No authors listed.")
        if r.year is None:
            add("warning", r.id, "No year.")
        if r.kind == "article" and not r.container.strip():
            add("warning", r.id, "Journal articles need the journal name.")
        if r.doi and not DOI_RE.match(normalise_doi(r.doi)):
            add("error", r.id, "The DOI is not in a valid format (it should start with 10.).")
        if r.kind == "web" and not r.url:
            add("warning", r.id, "Web sources need a URL.")
        if not r.verified and not r.checked:
            add("warning", r.id, "Not yet verified: look up its DOI or confirm you have checked the source.")
        d = normalise_doi(r.doi).lower()
        if d:
            if d in seen_doi:
                add("warning", r.id, f"Same DOI as {seen_doi[d]}.")
            seen_doi[d] = r.id
        t = re.sub(r"\W+", " ", r.title.lower()).strip()
        if t:
            if t in seen_title and not d:
                add("warning", r.id, f"Same title as {seen_title[t]}.")
            seen_title[t] = r.id
    cited = cited_ids(texts)
    known = set(ids)
    for missing in sorted(cited - known, key=lambda x: int(x[1:])):
        add("error", missing, f"Cited as [{missing}] in the text but not in the reference list.")
    for r in refs.items:
        if r.id not in cited:
            add("warning", r.id, "In the list but never cited in the text.")
    return out


def lookup_doi(doi: str) -> dict[str, Any]:
    """Fetch metadata for a DOI from Crossref. Raises LookupError if the DOI does not resolve."""
    d = normalise_doi(doi)
    if not DOI_RE.match(d):
        raise ValueError("That does not look like a DOI (it should start with 10.).")
    resp = httpx.get(
        CROSSREF_URL + d,
        headers={"User-Agent": f"{settings.app_name}/1.0"},
        timeout=20,
    )
    if resp.status_code == 404:
        raise LookupError("Crossref has no record of that DOI. Check it for typing mistakes.")
    resp.raise_for_status()
    m = resp.json().get("message", {})
    year = None
    for key in ("issued", "published-print", "published-online"):
        parts = (m.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    kind = {"journal-article": "article", "book": "book", "book-chapter": "chapter",
            "report": "report", "dataset": "dataset"}.get(m.get("type", ""), "other")
    return {
        "kind": kind,
        "authors": [author_name(a.get("given", ""), a.get("family", a.get("name", "")))
                    for a in m.get("author", []) if a.get("family") or a.get("name")],
        "year": year,
        "title": (m.get("title") or [""])[0],
        "container": (m.get("container-title") or [""])[0],
        "volume": m.get("volume", ""), "issue": m.get("issue", ""), "pages": m.get("page", ""),
        "publisher": m.get("publisher", ""), "doi": m.get("DOI", d), "url": m.get("URL", ""),
        "verified": True,
    }


def export_markdown(refs: RefList) -> str:
    if not refs.items:
        return ""
    lines = [f"- **[{r.id}]** {format_reference(r, refs.style)}" for r in refs.items]
    return "## References\n\n" + "\n".join(lines) + "\n"
