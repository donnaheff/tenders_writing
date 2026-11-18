import re
from collections import Counter
from typing import Any

AMBIGUITY_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"\b(tbd|to be confirmed|to be agreed|tbc)\b",
        "High",
        "Unconfirmed requirement or milestone marked TBD/TBC. Ask the buyer to confirm exact dates, scope, or thresholds before submission.",
    ),
    (
        r"\b(reasonable|as appropriate|where applicable|as required|sufficient)\b",
        "Medium",
        "Subjective qualifier without measurable acceptance criteria. Request objective SLA targets or minimum volume thresholds.",
    ),
    (
        r"\b(etc\.?|and similar|such as)\b",
        "Medium",
        "Open-ended scope phrasing ('etc.' / 'and similar'). Clarify the exhaustive list of deliverables included in fixed pricing.",
    ),
    (
        r"\b(unlimited|all liability|sole discretion)\b",
        "High",
        "Uncapped risk or unilateral term. Clarify liability cap and commercial risk allocation.",
    ),
    (
        r"\b(weighting|scoring)\b.*\b(tbd|unstated|discretion)\b",
        "High",
        "Evaluation weighting appears unstated. Request the exact scoring methodology and sub-criteria weights.",
    ),
]

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "by",
    "is",
    "are",
    "be",
    "we",
    "you",
    "your",
    "our",
    "do",
    "does",
    "how",
    "what",
    "when",
    "if",
    "that",
    "this",
    "all",
    "any",
}


def tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def summarize_notice(
    title: str,
    raw_text: str,
    funder_or_buyer: str,
    contract_value: float,
    currency: str,
    deadline: str,
) -> str:
    clean_body = " ".join(raw_text.split())
    snippet = clean_body[:240] + ("..." if len(clean_body) > 240 else "")
    value_str = f"{currency} {contract_value:,.0f}" if contract_value > 0 else "Value TBC"
    return f"{funder_or_buyer} — {title} ({value_str}, deadline {deadline}). {snippet}".strip()


def extract_grant_criteria(
    structured_criteria: list[dict[str, Any]],
    raw_pack_text: str,
    funder_type: str,
) -> list[dict[str, Any]]:
    if structured_criteria:
        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(structured_criteria, start=1):
            normalized.append(
                {
                    "criterion_id": item.get("criterion_id") or f"C{idx}",
                    "title": item.get("title") or f"Criterion {idx}",
                    "weight": float(item.get("weight", 25.0)),
                    "max_score": float(item.get("max_score", 5.0)),
                    "guidance": item.get("guidance")
                    or "Provide quantified evidence aligned to funder rubric.",
                }
            )
        return normalized

    # Fallback deterministic extraction from raw_pack_text
    segments = [
        seg.strip()
        for line in raw_pack_text.splitlines()
        for seg in re.split(r"[;\n]+|,\s*(?=[A-Za-z])", line)
        if seg.strip()
    ]
    extracted: list[dict[str, Any]] = []
    for seg in segments:
        for match in re.finditer(r"([A-Za-z0-9 &/-]+)\s*\((\d{1,3})%\)", seg):
            title = re.sub(r"^(?:evaluation criteria|grant)\s*:\s*", "", match.group(1), flags=re.I)
            title = title.split(".")[-1].strip(" :-")
            extracted.append(
                {
                    "criterion_id": f"C{len(extracted) + 1}",
                    "title": title,
                    "weight": float(match.group(2)),
                    "max_score": 5.0,
                    "guidance": seg,
                }
            )
            if len(extracted) >= 6:
                break
        if len(extracted) >= 6:
            break

    if extracted:
        return extracted

    # Standard structured rubric defaults by funder family
    presets = {
        "EU": [
            ("Excellence & Novelty", 40.0, 5.0, "Objectives, methodology, state-of-the-art advance."),
            ("Impact & Exploitation", 35.0, 5.0, "EU policy alignment, scale-up, dissemination."),
            ("Quality & Efficiency of Implementation", 25.0, 5.0, "Work packages, consortium, risk."),
        ],
        "UKRI": [
            ("Vision & Approach", 40.0, 10.0, "Innovation rationale, technical feasibility, roadmap."),
            ("Team & Capability", 30.0, 10.0, "Track record, partners, governance."),
            ("Value for Money & Impact", 30.0, 10.0, "UK economic/societal return, budget justification."),
        ],
        "World Bank": [
            ("Technical Methodology & Context", 40.0, 100.0, "Country alignment, field delivery plan."),
            ("Key Experts & Institutional Capacity", 35.0, 100.0, "Team CVs and comparable assignments."),
            ("Safeguards, Fiduciary & Sustainability", 25.0, 100.0, "ESF safeguards and handover."),
        ],
        "Foundation": [
            ("Mission Alignment & Theory of Change", 40.0, 5.0, "Beneficiary outcomes and equity."),
            ("Evidence & Measurement Plan", 30.0, 5.0, "Baseline, KPIs, learning loop."),
            ("Delivery Readiness & Budget Realism", 30.0, 5.0, "Unit economics and governance."),
        ],
    }
    chosen = presets.get(funder_type, presets["EU"])
    return [
        {
            "criterion_id": f"C{idx}",
            "title": title,
            "weight": weight,
            "max_score": max_score,
            "guidance": guidance,
        }
        for idx, (title, weight, max_score, guidance) in enumerate(chosen, start=1)
    ]


def compute_proposal_weighted_score(sections: list[dict[str, Any]]) -> float:
    total_weight = sum(float(s.get("weight", 0.0)) for s in sections)
    if total_weight <= 0:
        return 0.0
    weighted_sum = 0.0
    for s in sections:
        weight = float(s.get("weight", 0.0))
        max_score = float(s.get("max_score", 5.0)) or 5.0
        self_score = float(s.get("self_score", 0.0))
        ratio = max(0.0, min(1.0, self_score / max_score))
        weighted_sum += ratio * weight
    return round((weighted_sum / total_weight) * 100.0, 2)


def match_security_questionnaire(
    questionnaire_items: list[dict[str, Any]],
    answer_library: list[Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for idx, q in enumerate(questionnaire_items, start=1):
        q_text = q.get("question", "")
        q_tokens = tokenize(q_text)
        best_item = None
        best_score = 0.0

        for lib_item in answer_library:
            lib_text = f"{lib_item.question_pattern} {' '.join(lib_item.tags or [])} {lib_item.answer_text}"
            lib_tokens = tokenize(lib_text)
            if not q_tokens or not lib_tokens:
                continue
            overlap = len(q_tokens & lib_tokens)
            union = len(q_tokens | lib_tokens)
            # Weighted toward query coverage so concise questions match rich library answers
            coverage = overlap / max(1, len(q_tokens))
            jaccard = overlap / max(1, union)
            score = round(0.75 * coverage + 0.25 * jaccard, 3)
            if score > best_score:
                best_score = score
                best_item = lib_item

        matched = best_item is not None and best_score >= 0.2
        results.append(
            {
                "id": q.get("id") or f"SQ-{idx}",
                "question": q_text,
                "matched_answer_id": best_item.id if matched else None,
                "matched_answer_text": best_item.answer_text if matched else "",
                "confidence": round(min(1.0, best_score), 2) if matched else 0.0,
                "status": "matched" if matched else "needs_authoring",
            }
        )
    return results


def analyze_pack_for_clarifications(source_text: str) -> list[dict[str, Any]]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", source_text) if s.strip()]
    questions: list[dict[str, Any]] = []
    seen_excerpts: set[str] = set()

    for sentence in sentences:
        for pattern, priority, reason in AMBIGUITY_PATTERNS:
            if re.search(pattern, sentence, flags=re.IGNORECASE):
                if sentence in seen_excerpts:
                    continue
                seen_excerpts.add(sentence)
                q_idx = len(questions) + 1
                questions.append(
                    {
                        "id": f"CQ-{q_idx}",
                        "priority": priority,
                        "clause_excerpt": sentence[:240],
                        "ambiguity_reason": reason,
                        "drafted_question": (
                            f"Regarding '{sentence[:110]}...', could the Authority please confirm the exact "
                            f"measurable requirement, boundary, or evaluation rule that bidders should price and commit to?"
                        ),
                        "status": "draft",
                        "buyer_response": "",
                    }
                )
                break

    if not questions and source_text.strip():
        questions.append(
            {
                "id": "CQ-1",
                "priority": "Low",
                "clause_excerpt": source_text.strip()[:200],
                "ambiguity_reason": "General pre-submission commercial & TUPE/dependency verification.",
                "drafted_question": (
                    "Could the Authority confirm whether TUPE, incumbent handover obligations, "
                    "or third-party licensing dependencies apply to this contract?"
                ),
                "status": "draft",
                "buyer_response": "",
            }
        )
    return questions


def calculate_price_matrix(
    lines: list[dict[str, Any]],
    margin_pct: float,
    contingency_pct: float,
) -> tuple[list[dict[str, Any]], float, float]:
    normalized_lines: list[dict[str, Any]] = []
    subtotal = 0.0
    for idx, line in enumerate(lines, start=1):
        qty = float(line.get("quantity", 1.0))
        rate = float(line.get("unit_rate", 0.0))
        line_total = round(qty * rate, 2)
        subtotal += line_total
        normalized_lines.append(
            {
                "line_id": line.get("line_id") or f"L{idx}",
                "category": line.get("category", "Delivery"),
                "description": line.get("description", "Line item"),
                "unit": line.get("unit", "day"),
                "quantity": qty,
                "unit_rate": rate,
                "line_total": line_total,
            }
        )
    subtotal = round(subtotal, 2)
    multiplier = 1.0 + (margin_pct / 100.0) + (contingency_pct / 100.0)
    total_price = round(subtotal * multiplier, 2)
    return normalized_lines, subtotal, total_price


def build_cost_narrative(
    bid_title: str,
    currency: str,
    subtotal: float,
    margin_pct: float,
    contingency_pct: float,
    total_price: float,
    lines: list[dict[str, Any]],
) -> str:
    categories = Counter()
    for line in lines:
        categories[line.get("category", "Delivery")] += float(line.get("line_total", 0.0))
    breakdown = ", ".join(
        f"{cat}: {currency} {val:,.2f}" for cat, val in categories.most_common()
    )
    return (
        f"Cost Narrative for {bid_title}: Direct delivery base cost totals {currency} {subtotal:,.2f} "
        f"({breakdown}). A transparent {margin_pct:.1f}% corporate overhead/margin and {contingency_pct:.1f}% "
        f"risk-managed contingency yields a fixed-fee total of {currency} {total_price:,.2f}. "
        f"All unit rates are benchmarked against public-sector framework ceilings and include mobilisation, "
        f"quality assurance, and knowledge transfer with zero hidden pass-through fees."
    )


def build_social_value_narrative(
    bid_title: str,
    buyer_framework: str,
    themes: list[str],
    net_zero_target_year: int,
    baseline_emissions_tco2e: float,
    annual_reduction_pct: float,
    real_living_wage_accredited: bool,
    supply_chain_commitments: str,
    kpis: list[dict[str, Any]],
) -> str:
    theme_text = ", ".join(themes) if themes else "Net Zero & Equal Opportunity"
    wage_text = (
        "Accredited Real Living Wage employer across all direct staff and Tier-1 delivery partners."
        if real_living_wage_accredited
        else "Committed to transitioning all contract roles to Real Living Wage benchmarks within 6 months."
    )
    kpi_text = "; ".join(
        f"{k.get('metric', 'KPI')}: {k.get('target', 'TBD')}" for k in kpis
    )
    return (
        f"Social Value & Sustainability Statement — {bid_title} ({buyer_framework}). "
        f"Priority Themes: {theme_text}. "
        f"Carbon & Net Zero: Committed to Net Zero by {net_zero_target_year} from a verified baseline of "
        f"{baseline_emissions_tco2e:.1f} tCO2e/yr with >= {annual_reduction_pct:.1f}% annual Scope 1-3 reduction. "
        f"Fair Work: {wage_text} "
        f"Supply Chain: {supply_chain_commitments or '30-day prompt payment and SME ring-fencing.'} "
        f"Measurable KPIs: {kpi_text or 'Quarterly carbon & apprenticeship reporting.'}"
    )


def compare_win_loss_debrief(
    bid_title: str,
    buyer_name: str,
    outcome: str,
    criterion_comparisons: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], float, float]:
    feedback_letter = (
        f"Dear Procurement Team at {buyer_name},\n\n"
        f"Thank you for notifying us of the {outcome.upper()} decision for '{bid_title}'. "
        f"In line with procurement transparency standards, we respectfully request written criterion-by-criterion "
        f"scoring feedback, evaluator strengths/weaknesses, and comparative winning-bid benchmarks so we can "
        f"continuously improve our future submissions.\n\nYours faithfully,\nBid Studio Outcomes Team"
    )
    fixes: list[dict[str, Any]] = []
    internal_scores: list[float] = []
    buyer_scores: list[float] = []

    for row in criterion_comparisons:
        crit = row.get("criterion", "Criterion")
        internal_s = float(row.get("internal_score", 0.0))
        buyer_s = float(row.get("buyer_score", 0.0))
        internal_scores.append(internal_s)
        buyer_scores.append(buyer_s)
        delta = round(buyer_s - internal_s, 2)
        if delta < 0 or buyer_s < 70:
            severity = "High" if delta <= -10 or buyer_s < 60 else "Medium"
            fixes.append(
                {
                    "criterion": crit,
                    "score_delta": delta,
                    "severity": severity,
                    "action": (
                        f"Close {abs(delta):.1f}-point optimism gap on '{crit}': replace generic claims "
                        f"with buyer-verified case metrics and pre-submission red-team scoring."
                    ),
                }
            )

    avg_internal = round(sum(internal_scores) / len(internal_scores), 2) if internal_scores else 0.0
    avg_buyer = round(sum(buyer_scores) / len(buyer_scores), 2) if buyer_scores else 0.0
    return feedback_letter, fixes, avg_internal, avg_buyer


def match_notices_for_subscription(sub: Any, notices: list[Any]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    sub_sectors = {s.lower() for s in (sub.sectors or [])}
    sub_types = {t.lower() for t in (sub.notice_types or [])}
    sub_keywords = [k.lower() for k in (sub.keywords or [])]

    for n in notices:
        if n.status == "closed":
            continue
        if sub_types and n.notice_type.lower() not in sub_types:
            continue
        if sub_sectors and n.sector.lower() not in sub_sectors:
            continue
        if n.contract_value < (sub.min_value or 0.0):
            continue
        if sub.max_value is not None and n.contract_value > sub.max_value:
            continue
        haystack = f"{n.title} {n.raw_pack_text} {n.cpv_or_topic} {n.funder_or_buyer}".lower()
        if sub_keywords and not any(kw in haystack for kw in sub_keywords):
            continue

        matched.append(
            {
                "notice_id": n.id,
                "notice_type": n.notice_type,
                "title": n.title,
                "funder_or_buyer": n.funder_or_buyer,
                "sector": n.sector,
                "contract_value": n.contract_value,
                "currency": n.currency,
                "deadline": n.deadline,
                "ai_summary": n.ai_summary
                or summarize_notice(
                    n.title,
                    n.raw_pack_text,
                    n.funder_or_buyer,
                    n.contract_value,
                    n.currency,
                    n.deadline,
                ),
            }
        )
    return matched


def build_buyer_intelligence_report(
    buyer_name: str,
    sector: str | None,
    awarded_notices: list[Any],
) -> dict[str, Any]:
    filtered = [
        n
        for n in awarded_notices
        if n.notice_type == "awarded_tender"
        and buyer_name.lower() in n.funder_or_buyer.lower()
        and (not sector or sector.lower() == n.sector.lower())
    ]
    if not filtered:
        return {
            "awards_analyzed": 0,
            "total_spend": 0.0,
            "average_award_value": 0.0,
            "min_award_value": 0.0,
            "max_award_value": 0.0,
            "top_winners": [],
            "insights": [
                f"No historical awarded notices matched '{buyer_name}'. Broaden buyer name or ingest more notices."
            ],
        }

    values = [float(n.contract_value) for n in filtered]
    total_spend = round(sum(values), 2)
    avg_val = round(total_spend / len(values), 2)
    winner_counts: Counter[str] = Counter()
    winner_spend: Counter[str] = Counter()
    for n in filtered:
        supplier = n.awarded_supplier or "Undisclosed Winner"
        winner_counts[supplier] += 1
        winner_spend[supplier] += float(n.contract_value)

    top_winners = [
        {
            "supplier": supplier,
            "wins": count,
            "total_value": round(winner_spend[supplier], 2),
            "share_pct": round((count / len(filtered)) * 100.0, 1),
        }
        for supplier, count in winner_counts.most_common(5)
    ]

    top_supplier = top_winners[0]
    insights = [
        f"{buyer_name} awarded {len(filtered)} contracts totaling {total_spend:,.2f} (avg {avg_val:,.2f}).",
        f"Leading incumbent is {top_supplier['supplier']} with {top_supplier['wins']} win(s) ({top_supplier['share_pct']}% share).",
        "Target competitive differentiation around mobilisation speed, social value KPIs, and transparent pricing.",
    ]
    return {
        "awards_analyzed": len(filtered),
        "total_spend": total_spend,
        "average_award_value": avg_val,
        "min_award_value": round(min(values), 2),
        "max_award_value": round(max(values), 2),
        "top_winners": top_winners,
        "insights": insights,
    }


def default_framework_checklist(vehicle_type: str) -> list[dict[str, Any]]:
    base = [
        {"item_id": "FW-1", "title": "PAS 91 / Standard Selection Questionnaire (SQ)", "completed": False, "notes": ""},
        {"item_id": "FW-2", "title": "Cyber Essentials / ISO 27001 Evidence", "completed": False, "notes": ""},
        {"item_id": "FW-3", "title": "Public & Employers Liability Insurance Certificates", "completed": False, "notes": ""},
        {"item_id": "FW-4", "title": "3x Buyer-Signed Reference Case Studies", "completed": False, "notes": ""},
        {"item_id": "FW-5", "title": "Rate Card & Lot Pricing Schedule", "completed": False, "notes": ""},
        {"item_id": "FW-6", "title": "Carbon Reduction Plan (PPN 06/21)", "completed": False, "notes": ""},
    ]
    if vehicle_type == "dps":
        base.append({"item_id": "FW-7", "title": "DPS Category & Geographic Lot Selection", "completed": False, "notes": ""})
    elif vehicle_type == "approved_supplier_list":
        base.append({"item_id": "FW-7", "title": "Financial Standing & Credit Check Pack", "completed": False, "notes": ""})
    return base


def validate_public_sector_draft(
    specification_text: str,
    evaluation_criteria: list[dict[str, Any]],
) -> tuple[float, list[str], str]:
    issues: list[str] = []
    total_weight = sum(float(c.get("weight_pct", 0.0)) for c in evaluation_criteria)

    if not evaluation_criteria:
        issues.append("No evaluation criteria defined.")
    elif abs(total_weight - 100.0) > 0.01:
        issues.append(f"Evaluation criteria weights sum to {total_weight:.1f}%, but must sum to 100.0%.")

    for c in evaluation_criteria:
        if not c.get("scoring_guidance"):
            issues.append(f"Criterion '{c.get('name', 'Unnamed')}' is missing scoring guidance for evaluators.")
        if float(c.get("max_score", 0.0)) <= 0:
            issues.append(f"Criterion '{c.get('name', 'Unnamed')}' must have max_score > 0.")

    ambiguous_hits = 0
    for pattern, _, _ in AMBIGUITY_PATTERNS:
        if re.search(pattern, specification_text, flags=re.IGNORECASE):
            ambiguous_hits += 1
    if ambiguous_hits > 0:
        issues.append(
            f"Specification contains {ambiguous_hits} ambiguous phrase category(ies) (e.g., TBD/reasonable/etc.) that will trigger supplier clarification questions."
        )
    if len(specification_text.strip()) < 60:
        issues.append("Specification text is too brief (< 60 chars) to support fair, comparable bids.")

    clarity_score = max(0.0, round(100.0 - (len(issues) * 18.0), 1))
    status = "validated" if not issues else "draft"
    return clarity_score, issues, status
