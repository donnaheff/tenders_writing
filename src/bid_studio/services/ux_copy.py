"""UX copy deck: parsing, terminology rules and automatic style checks."""

import re
from typing import Any

ELEMENTS: dict[str, str] = {
    "button": "One to four words, verb first, no end punctuation, and name the result ('Save changes', not 'Submit').",
    "label": "A short noun phrase in sentence case, no colon, matching the term used everywhere else.",
    "placeholder": "An example of what to type, not an instruction, and never a replacement for a label.",
    "error": "Say what happened, why if known, and what to do next. No blame, no jokes, no 'Oops'.",
    "empty_state": "Say what belongs here, why it is empty, and offer one clear next action.",
    "tooltip": "One short sentence that adds information the label does not. Do not repeat the label.",
    "confirmation": "State the consequence plainly and make the confirm button name the action ('Delete project').",
    "notification": "Lead with what changed or what is needed, then the detail, in one or two sentences.",
    "onboarding": "One idea per step, in the order the user needs it, with the benefit first.",
}
STATUSES = ("draft", "approved")
FIX_WORDS = ("try", "check", "enter", "use", "select", "contact", "retry", "choose", "add", "change",
             "enable", "update", "sign in", "refresh", "open", "go to", "confirm", "remove")
VAGUE_ERRORS = ("oops", "whoops", "uh-oh", "uh oh", "something went wrong")
TERM_RE = re.compile(r"use\s+[\"“']([^\"”']+)[\"”']\s*,?\s*(?:not|rather than|instead of)\s+[\"“']([^\"”']+)[\"”']", re.I)


def parse_strings(text: str) -> list[dict[str, Any]]:
    """Lines of 'screen | element | copy' (or just copy). Returns new items without ids."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) == 3:
            screen, element, copy = parts[0], parts[1].lower().replace(" ", "_"), parts[2]
        else:
            screen, element, copy = "", "label", line
        if element not in ELEMENTS:
            element = "label"
        if copy:
            out.append(new_item("", screen[:120], element, copy[:500]))
    return out[:500]


def new_item(item_id: str, screen: str = "", element: str = "label", text: str = "") -> dict[str, Any]:
    return {"id": item_id, "screen": screen, "element": element, "text": text, "notes": "",
            "max_chars": None, "status": "draft"}


def assign_ids(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used = {i["id"] for i in existing}
    n = len(existing)
    for it in fresh:
        n += 1
        while f"S{n}" in used:
            n += 1
        it["id"] = f"S{n}"
        used.add(it["id"])
    return fresh


def terminology_rules(sections: list[dict[str, Any]]) -> list[tuple[str, str]]:
    text = next((s["text"] for s in sections if s["id"] == "terminology"), "")
    return [(m.group(1).strip(), m.group(2).strip()) for m in TERM_RE.finditer(text)]


def lint_item(it: dict[str, Any], rules: list[tuple[str, str]]) -> list[str]:
    text, element = it["text"], it["element"]
    low = text.lower()
    words = len(text.split())
    notes: list[str] = []
    if not text.strip():
        return notes
    if it.get("max_chars") and len(text) > it["max_chars"]:
        notes.append(f"{len(text)} characters; the limit is {it['max_chars']}.")
    if text != text.strip():
        notes.append("Remove leading or trailing spaces.")
    if "  " in text:
        notes.append("Remove double spaces.")
    if len([w for w in re.findall(r"[A-Za-z]{4,}", text) if w.isupper()]) > 1:
        notes.append("Avoid ALL CAPS.")
    if element == "button":
        if words > 4:
            notes.append("Buttons work best at one to four words.")
        if text.rstrip().endswith((".", "!")):
            notes.append("Remove the end punctuation from a button.")
    if element == "error":
        if any(v in low for v in VAGUE_ERRORS):
            notes.append("Say what actually happened instead of a vague phrase.")
        if "!" in text:
            notes.append("Avoid exclamation marks in error messages.")
        if len(text) < 25:
            notes.append("Too short to say what happened and what to do.")
        elif not any(w in low for w in FIX_WORDS):
            notes.append("Add the next step the user should take.")
    if element == "empty_state" and len(text) < 20:
        notes.append("Explain what belongs here and offer a next action.")
    for use, avoid in rules:
        if re.search(rf"\b{re.escape(avoid)}\b", text, re.I):
            notes.append(f"Uses \"{avoid}\"; the style guide says use \"{use}\".")
    return notes


def lint(items: list[dict[str, Any]], sections: list[dict[str, Any]]) -> dict[str, list[str]]:
    rules = terminology_rules(sections)
    return {it["id"]: n for it in items if (n := lint_item(it, rules))}


def export_markdown(title: str, sections: list[dict[str, Any]], items: list[dict[str, Any]]) -> str:
    out = [f"# {title}", ""]
    for s in sections:
        out += [f"## {s['title']}", "", s["text"].strip() or "_Not yet written._", ""]
    out += ["## Copy deck", "", "| ID | Screen | Element | Copy | Chars | Status |", "| --- | --- | --- | --- | --- | --- |"]
    for it in items:
        copy = (it["text"] or "_empty_").replace("\n", " ").replace("|", "\\|")
        out.append(f"| {it['id']} | {it['screen']} | {it['element']} | {copy} | {len(it['text'])} | {it['status']} |")
    return "\n".join(out) + "\n"
