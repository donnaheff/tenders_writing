"""AI assistant for the Grant Studio.

With ANTHROPIC_API_KEY set, requests go to Claude (Anthropic Messages API). Without a key a
deterministic rule-based helper handles draft / improve / shorten / critique so the feature
works offline; it is labelled as such and never pretends to be an LLM.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from bid_studio.config import settings
from bid_studio.services.domain_logic import tokenize

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ACTIONS = ("draft", "improve", "shorten", "critique", "ask")

SYSTEM_PROMPT = (
    "You are an expert grant-writing assistant inside a proposal editor. You help the applicant "
    "answer one scored criterion of a funding call. Rules: write in clear, specific, funder-ready "
    "prose; never invent facts, figures, partners, results or citations; where a fact is needed "
    "but not provided, write a bracketed placeholder such as [TO CONFIRM: number of beneficiaries]; "
    "only draw on the 'Verified material' supplied; respect any word limit; return only the "
    "requested text with no preamble or commentary unless asked for a critique."
)

FILLERS = [
    (r"\bin order to\b", "to"),
    (r"\butili[sz]e\b", "use"),
    (r"\bat this point in time\b", "now"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bvery\b ", ""),
    (r"\breally\b ", ""),
    (r"\bbasically\b,? ", ""),
    (r"\bit is important to note that\b ", ""),
    (r"\bin the event that\b", "if"),
    (r"\ba number of\b", "several"),
]


@dataclass
class AssistantRequest:
    action: str
    section: dict[str, Any]
    guidance: str = ""
    call_title: str = ""
    funder: str = ""
    call_summary: str = ""
    applicant: str = ""
    instruction: str = ""
    material: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AssistantResult:
    text: str
    provider: str
    model: str = ""
    suggested_score: float | None = None
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def provider_status() -> dict[str, str]:
    if settings.anthropic_api_key:
        return {"provider": "claude", "model": settings.assistant_model}
    return {"provider": "offline", "model": ""}


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


# ---------------------------------------------------------------- Claude

def build_prompt(req: AssistantRequest) -> str:
    sec = req.section
    limit = sec.get("word_limit")
    lines = [
        f"Funder: {req.funder}",
        f"Call: {req.call_title}",
        f"Call summary: {req.call_summary}",
        f"Applicant: {req.applicant or '[TO CONFIRM: applicant organisation]'}",
        (
            f"Document: {sec.get('doc_title')}; section: {sec.get('title')}"
            if sec.get("is_doc")
            else f"Criterion: {sec.get('title')} (weight {sec.get('weight')}%, scored out of {sec.get('max_score')})"
        ),
        f"Guidance for this {'section' if sec.get('is_doc') else 'criterion'}: {req.guidance or 'none provided'}",
        f"Word limit: {limit if limit else 'none'}",
    ]
    if req.material:
        lines.append("Verified material you may draw on:")
        lines += [f"- {m['title']}: {m['text']}" for m in req.material]
    current = (sec.get("draft_text") or "").strip()
    if req.action == "draft":
        task = "Write a first draft of the response for this criterion."
    elif req.action == "improve":
        task = "Rewrite the current text to score higher on this criterion: clearer, more specific, better structured. Keep all facts."
    elif req.action == "shorten":
        task = f"Shorten the current text to at most {limit or int(_words(current) * 0.8)} words, keeping the strongest points."
    elif req.action == "critique":
        task = (
            "Critique the current text as a funder's reviewer would. Reply with JSON only: "
            '{"suggested_score": <number between 0 and max score>, "strengths": [..], "gaps": [..], "summary": ".."}'
        )
    else:
        task = req.instruction
    if req.instruction and req.action != "ask":
        task += f" Additional instruction: {req.instruction}"
    lines += ["", f"Task: {task}", "", "Current text:", current or "(empty)"]
    return "\n".join(lines)


def call_claude(prompt: str) -> str:
    resp = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": settings.assistant_model,
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=settings.assistant_timeout,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content") or []
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _parse_critique(raw: str, max_score: float) -> AssistantResult:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    score = data.get("suggested_score")
    if isinstance(score, (int, float)):
        score = round(max(0.0, min(float(max_score), float(score))), 2)
    else:
        score = None
    return AssistantResult(
        text=str(data.get("summary") or raw),
        provider="claude",
        model=settings.assistant_model,
        suggested_score=score,
        strengths=[str(x) for x in data.get("strengths", [])][:8],
        gaps=[str(x) for x in data.get("gaps", [])][:8],
    )


# ---------------------------------------------------------------- offline helper

def _offline_draft(req: AssistantRequest) -> AssistantResult:
    sec = req.section
    guidance_points = [g.strip() for g in re.split(r"[;.]|,\s*(?=[a-z])", req.guidance) if g.strip()]
    applicant = req.applicant or "[TO CONFIRM: applicant organisation]"
    paras = (
        []
        if sec.get("is_doc")
        else [
            f"{applicant} proposes to address {sec.get('title', 'this criterion').lower()} for "
            f"{req.call_title or 'this call'} as follows. [TO CONFIRM: one-sentence summary of the project aim]"
        ]
    )
    for point in guidance_points[:4]:
        paras.append(f"{point[0].upper() + point[1:]}: [TO CONFIRM: your specific approach, with numbers and dates].")
    for m in req.material[:2]:
        paras.append(m["text"])
    paras.append("[TO CONFIRM: expected outcomes, how they will be measured, and who is responsible.]")
    return AssistantResult(
        text="\n\n".join(paras),
        provider="offline",
        notes=[
            "Offline scaffold: structure and placeholders only. Replace each [TO CONFIRM] with real detail.",
            "Add an Anthropic API key (ANTHROPIC_API_KEY) to get full drafts.",
        ],
    )


def _offline_improve(req: AssistantRequest) -> AssistantResult:
    text = req.section.get("draft_text", "") or ""
    out, changes = text, 0
    for pattern, repl in FILLERS:
        out, n = re.subn(pattern, repl, out, flags=re.I)
        changes += n
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    long_sents = [s for s in _sentences(out) if _words(s) > 35]
    notes = [f"Removed or simplified {changes} filler phrase(s)."] if changes else ["No filler phrases found."]
    if long_sents:
        notes.append(f"{len(long_sents)} sentence(s) exceed 35 words; consider splitting them.")
    if not re.search(r"\d", out):
        notes.append("No numbers or dates found: reviewers score specific, measurable claims higher.")
    return AssistantResult(text=out.strip(), provider="offline", notes=notes)


def _offline_shorten(req: AssistantRequest) -> AssistantResult:
    text = req.section.get("draft_text", "") or ""
    target = req.section.get("word_limit") or max(1, int(_words(text) * 0.8))
    sents = _sentences(text)
    focus = tokenize(f"{req.section.get('title', '')} {req.guidance}")
    ranked = sorted(
        range(len(sents)),
        key=lambda i: (-(len(focus & tokenize(sents[i])) + (1 if re.search(r"\d", sents[i]) else 0)), i),
    )
    keep: set[int] = set()
    used = 0
    for i in ranked:
        w = _words(sents[i])
        if used + w <= target:
            keep.add(i)
            used += w
    result = " ".join(sents[i] for i in sorted(keep))
    notes = [f"Kept {len(keep)} of {len(sents)} sentences ({used} words, target {target})."]
    if not keep and sents:
        result = " ".join(sents[0].split()[:target])
        notes.append("Even the first sentence exceeded the limit, so it was truncated.")
    return AssistantResult(text=result, provider="offline", notes=notes)


def _offline_critique(req: AssistantRequest) -> AssistantResult:
    sec = req.section
    text = sec.get("draft_text", "") or ""
    max_score = float(sec.get("max_score", 5) or 5)
    focus = tokenize(f"{sec.get('title', '')} {req.guidance}")
    present = focus & tokenize(text)
    coverage = len(present) / len(focus) if focus else 0.0
    has_numbers = bool(re.search(r"\d", text))
    has_evidence = bool(sec.get("evidence_refs"))
    wc = _words(text)
    strengths, gaps = [], []
    if coverage >= 0.5:
        strengths.append("Addresses most of the funder's guidance terms.")
    if has_numbers:
        strengths.append("Includes specific numbers or dates.")
    if has_evidence:
        strengths.append("Cites evidence from the library.")
    missing = sorted(focus - present)[:6]
    if missing:
        gaps.append("Guidance terms not mentioned: " + ", ".join(missing) + ".")
    if not has_numbers:
        gaps.append("No numbers or dates; add measurable targets.")
    if not has_evidence:
        gaps.append("No evidence cited; insert a case study or metric from the Library.")
    if "[TO CONFIRM" in text:
        gaps.append("Contains [TO CONFIRM] placeholders that must be replaced.")
    if wc < 60:
        gaps.append(f"Only {wc} words; reviewers usually expect a developed answer.")
    if sec.get("word_limit") and wc > sec["word_limit"]:
        gaps.append(f"Over the word limit by {wc - sec['word_limit']} words.")
    ratio = 0.25 + 0.4 * coverage + 0.15 * has_numbers + 0.15 * has_evidence + (0.05 if wc >= 120 else 0)
    ratio = 0.0 if not text.strip() else min(ratio, 1.0)
    return AssistantResult(
        text=(
            f"Heuristic review: {round(coverage * 100)}% of the guidance terms appear in your text. "
            "This is a keyword-based estimate, not a reviewer's judgement."
        ),
        provider="offline",
        suggested_score=None if sec.get("is_doc") else round(max_score * ratio * 2) / 2,
        strengths=strengths,
        gaps=gaps,
        notes=["Add an Anthropic API key for a reviewer-style critique."],
    )


def run(req: AssistantRequest) -> AssistantResult:
    if req.action not in ACTIONS:
        raise ValueError(f"Unknown action {req.action!r}")
    if req.action == "ask" and not req.instruction.strip():
        raise ValueError("Please enter a question or instruction")
    if settings.anthropic_api_key:
        raw = call_claude(build_prompt(req))
        if req.action == "critique":
            return _parse_critique(raw, float(req.section.get("max_score", 5) or 5))
        return AssistantResult(text=raw, provider="claude", model=settings.assistant_model)
    if req.action == "ask":
        return AssistantResult(
            text=(
                "Free-form questions need an AI model. Set ANTHROPIC_API_KEY to enable them. "
                "Meanwhile Draft, Improve, Shorten and Critique work offline."
            ),
            provider="offline",
        )
    return {
        "draft": _offline_draft,
        "improve": _offline_improve,
        "shorten": _offline_shorten,
        "critique": _offline_critique,
    }[req.action](req)
