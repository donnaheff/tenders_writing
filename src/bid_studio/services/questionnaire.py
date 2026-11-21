"""Match questionnaire questions against the workspace's answer library."""

import re
from typing import Any

from bid_studio.services.domain_logic import tokenize

MATCHED_AT, REVIEW_AT = 0.5, 0.25  # share of the question's terms found in the library answer


def parse_questions(text: str) -> list[str]:
    """One question per line; strips bullets and numbering; ignores blanks and duplicates."""
    seen, out = set(), []
    for raw in (text or "").splitlines():
        q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw).strip()
        if len(q) >= 3 and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q[:600])
    return out[:300]


def new_items(questions: list[str]) -> list[dict[str, Any]]:
    return [
        {"id": f"Q{i}", "question": q, "answer": "", "status": "unanswered", "confidence": 0.0,
         "source_answer_id": None}
        for i, q in enumerate(questions, start=1)
    ]


def best_match(question: str, library: list[Any]) -> tuple[Any | None, float]:
    q_tokens = tokenize(question)
    if not q_tokens:
        return None, 0.0
    best, best_score = None, 0.0
    for item in library:
        target = tokenize(f"{item.question_pattern} {' '.join(item.tags or [])} {item.answer_text}")
        shared = q_tokens & target
        score = len(shared) / len(q_tokens)
        if len(shared) >= 2 and score > best_score:
            best, best_score = item, score
    return best, round(best_score, 2)


def auto_match(items: list[dict[str, Any]], library: list[Any]) -> int:
    """Fill unanswered or still-unreviewed items from the library. Returns how many changed.

    Items a person has approved, or answered by hand, are never overwritten.
    """
    changed = 0
    for it in items:
        if it["status"] == "approved" or (it["answer"].strip() and it.get("source_answer_id") is None):
            continue
        match, score = best_match(it["question"], library)
        if match is None or score < REVIEW_AT:
            continue
        it["answer"] = match.answer_text
        it["source_answer_id"] = match.id
        it["confidence"] = score
        it["status"] = "matched" if score >= MATCHED_AT else "needs_review"
        changed += 1
    return changed


def export_markdown(title: str, items: list[dict[str, Any]]) -> str:
    out = [f"# {title}", "", "| # | Question | Answer | Status |", "| --- | --- | --- | --- |"]
    for it in items:
        ans = (it["answer"] or "_No answer yet_").replace("\n", " ").replace("|", "\\|")
        q = it["question"].replace("|", "\\|")
        out.append(f"| {it['id']} | {q} | {ans} | {it['status']} |")
    return "\n".join(out) + "\n"
