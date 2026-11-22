"""Generic table documents: a list of rows with typed columns (RoPA, statement of applicability, ...)."""

from typing import Any

from fastapi import HTTPException

TYPES = ("text", "longtext", "select", "number")


def col(key: str, label: str, kind: str = "text", *, options: list[str] | None = None,
        required: bool = False, readonly: bool = False, prompt: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "type": kind, "options": options or [], "required": required,
            "readonly": readonly, "prompt": prompt}


def new_row(spec: dict[str, Any], row_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {"id": row_id}
    for c in spec["columns"]:
        row[c["key"]] = 0 if c["type"] == "number" else ""
    return row


def initial_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for fixed in spec.get("fixed_rows", ()):
        row = new_row(spec, fixed["id"])
        row.update({k: v for k, v in fixed.items() if k != "id"})
        rows.append(row)
    return rows


def validate_rows(spec: dict[str, Any], rows: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean user-submitted rows against the column spec, or raise a 422."""
    cols = {c["key"]: c for c in spec["columns"]}
    fixed = bool(spec.get("fixed_rows"))
    if fixed and [r.get("id") for r in rows] != [r["id"] for r in existing]:
        raise HTTPException(status_code=422, detail="Rows cannot be added, removed or reordered in this document")
    old = {r["id"]: r for r in existing}
    clean, seen = [], set()
    for r in rows:
        rid = r.get("id")
        if not isinstance(rid, str) or not rid.strip() or len(rid) > 40:
            raise HTTPException(status_code=422, detail="Every row needs an id")
        if rid in seen:
            raise HTTPException(status_code=422, detail=f"Duplicate row id {rid}")
        seen.add(rid)
        extra = set(r) - set(cols) - {"id"}
        if extra:
            raise HTTPException(status_code=422, detail=f"Unknown column {sorted(extra)[0]!r}")
        out: dict[str, Any] = {"id": rid}
        for key, c in cols.items():
            value = r.get(key, 0 if c["type"] == "number" else "")
            if c["readonly"] and rid in old:
                value = old[rid].get(key, value)
            if c["type"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise HTTPException(status_code=422, detail=f"{c['label']} must be a number")
            else:
                if not isinstance(value, str):
                    raise HTTPException(status_code=422, detail=f"{c['label']} must be text")
                limit = 4000 if c["type"] == "longtext" else 400
                if len(value) > limit:
                    raise HTTPException(status_code=422, detail=f"{c['label']} is too long")
                if c["type"] == "select" and value and value not in c["options"]:
                    raise HTTPException(status_code=422, detail=f"{c['label']}: {value!r} is not an allowed value")
            out[key] = value
        clean.append(out)
    if len(clean) > 600:
        raise HTTPException(status_code=422, detail="A table holds at most 600 rows")
    return clean


def row_issues(spec: dict[str, Any], row: dict[str, Any]) -> list[str]:
    issues = []
    for c in spec["columns"]:
        if c["required"] and not str(row.get(c["key"], "")).strip():
            issues.append(f"{c['label']} is empty")
    for rule in spec.get("conditional", ()):
        if all(row.get(k) == v for k, v in rule["when"].items()) and not str(row.get(rule["require"], "")).strip():
            label = next(c["label"] for c in spec["columns"] if c["key"] == rule["require"])
            issues.append(f"{label} is needed when {', '.join(f'{k} is {v}' for k, v in rule['when'].items())}")
    return issues


def export_markdown(title: str, spec: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    cols = spec["columns"]
    head = "| ID | " + " | ".join(c["label"] for c in cols) + " |"
    out = [f"# {title}", "", head, "|" + " --- |" * (len(cols) + 1)]
    for r in rows:
        cells = [str(r.get(c["key"], "")).replace("\n", " ").replace("|", "\\|") for c in cols]
        out.append(f"| {r['id']} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
