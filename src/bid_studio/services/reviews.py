"""Response-to-reviewers: parsing pasted reviewer comments and exporting the response letter."""

import re
from typing import Any

STATUSES = ("pending", "addressed", "partly", "disagree", "noted")
PREFIX = re.compile(r"^\s*(?:(?:reviewer|referee|editor|r)\s*#?\s*(\d+|[a-c])|(editor))\s*[:.)\-]\s*", re.I)


def parse_comments(text: str) -> list[dict[str, Any]]:
    """One comment per line. An optional 'Reviewer 2:' or 'R2:' prefix names who made it."""
    out: list[dict[str, Any]] = []
    reviewer = "Reviewer 1"
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = PREFIX.match(line)
        if m:
            who = m.group(2) or m.group(1)
            reviewer = "Editor" if m.group(2) else f"Reviewer {who.upper() if who.isalpha() else who}"
            line = line[m.end():].strip()
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if len(line) >= 3:
            out.append({"id": "", "reviewer": reviewer, "comment": line[:3000], "response": "",
                        "change": "", "status": "pending"})
    return out[:300]


def assign_ids(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used = {i["id"] for i in existing}
    n = len(existing)
    for it in fresh:
        n += 1
        while f"C{n}" in used:
            n += 1
        it["id"] = f"C{n}"
        used.add(it["id"])
    return fresh


def export_markdown(title: str, sections: list[dict[str, Any]], items: list[dict[str, Any]]) -> str:
    out = [f"# {title}", ""]
    for s in sections:
        if s["text"].strip():
            out += [f"## {s['title']}", "", s["text"].strip(), ""]
    by_reviewer: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_reviewer.setdefault(it["reviewer"], []).append(it)
    for reviewer, rows in by_reviewer.items():
        out += [f"## {reviewer}", ""]
        for it in rows:
            out += [f"**Comment {it['id']}:** {it['comment']}", "",
                    f"**Response:** {it['response'].strip() or '_No response yet._'}"]
            if it["change"].strip():
                out.append(f"**Change made:** {it['change'].strip()}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
