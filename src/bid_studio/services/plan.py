"""Work packages, budget and supporting documents for a proposal, with consistency checks."""

from typing import Any, Literal

from pydantic import BaseModel, Field

CATEGORIES = ("personnel", "travel", "equipment", "subcontracting", "other")
RISK_HIGH, RISK_MEDIUM = 15, 8

Id = Field(min_length=1, max_length=40)


class Task(BaseModel):
    id: str = Id
    title: str = Field(default="", max_length=200)
    start_month: int = Field(default=1, ge=1, le=120)
    end_month: int = Field(default=1, ge=1, le=120)


class Deliverable(BaseModel):
    id: str = Id
    title: str = Field(default="", max_length=200)
    month: int = Field(default=1, ge=1, le=120)
    type: str = Field(default="report", max_length=40)


class Milestone(BaseModel):
    id: str = Id
    title: str = Field(default="", max_length=200)
    month: int = Field(default=1, ge=1, le=120)


class WorkPackage(BaseModel):
    id: str = Id
    title: str = Field(default="", max_length=200)
    lead: str = Field(default="", max_length=160)
    start_month: int = Field(default=1, ge=1, le=120)
    end_month: int = Field(default=12, ge=1, le=120)
    objectives: str = Field(default="", max_length=4000)
    tasks: list[Task] = Field(default_factory=list, max_length=40)
    deliverables: list[Deliverable] = Field(default_factory=list, max_length=40)
    milestones: list[Milestone] = Field(default_factory=list, max_length=40)


class BudgetLine(BaseModel):
    id: str = Id
    wp: str = Field(default="", max_length=40)
    category: Literal["personnel", "travel", "equipment", "subcontracting", "other"] = "personnel"
    description: str = Field(default="", max_length=300)
    quantity: float = Field(default=0, ge=0, le=1_000_000)
    unit: str = Field(default="", max_length=40)
    unit_cost: float = Field(default=0, ge=0, le=100_000_000)


class Budget(BaseModel):
    indirect_pct: float = Field(default=0, ge=0, le=100)
    indirect_base: Literal["all", "excl_subcontracting"] = "all"
    match_funding: float = Field(default=0, ge=0, le=1_000_000_000)
    lines: list[BudgetLine] = Field(default_factory=list, max_length=300)


class DocSection(BaseModel):
    id: str = Id
    title: str = Field(default="", max_length=200)
    prompt: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=40000)


class RiskRow(BaseModel):
    id: str = Id
    description: str = Field(default="", max_length=600)
    category: str = Field(default="other", max_length=30)
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    mitigation: str = Field(default="", max_length=1000)
    owner: str = Field(default="", max_length=120)


class Document(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    title: str = Field(default="", max_length=200)
    sections: list[DocSection] = Field(default_factory=list, max_length=30)
    rows: list[RiskRow] = Field(default_factory=list, max_length=100)


class Plan(BaseModel):
    duration_months: int = Field(default=36, ge=1, le=120)
    work_packages: list[WorkPackage] = Field(default_factory=list, max_length=30)
    budget: Budget = Field(default_factory=Budget)
    documents: list[Document] = Field(default_factory=list, max_length=10)


def empty_plan() -> dict[str, Any]:
    return Plan().model_dump()


def risk_band(score: int) -> str:
    return "high" if score >= RISK_HIGH else "medium" if score >= RISK_MEDIUM else "low"


def analyze_budget(plan: Plan, proposal_requested: float) -> dict[str, Any]:
    b = plan.budget
    by_wp: dict[str, float] = {}
    by_cat = dict.fromkeys(CATEGORIES, 0.0)
    direct = subcontracting = 0.0
    lines = []
    for ln in b.lines:
        total = round(ln.quantity * ln.unit_cost, 2)
        lines.append({"id": ln.id, "total": total})
        by_wp[ln.wp or "(unassigned)"] = round(by_wp.get(ln.wp or "(unassigned)", 0.0) + total, 2)
        by_cat[ln.category] = round(by_cat[ln.category] + total, 2)
        direct += total
        if ln.category == "subcontracting":
            subcontracting += total
    base = direct - subcontracting if b.indirect_base == "excl_subcontracting" else direct
    indirect = round(base * b.indirect_pct / 100.0, 2)
    total = round(direct + indirect, 2)
    requested = round(max(total - b.match_funding, 0.0), 2)
    return {
        "lines": lines,
        "by_wp": by_wp,
        "by_category": by_cat,
        "direct": round(direct, 2),
        "indirect": indirect,
        "total": total,
        "match_funding": b.match_funding,
        "requested": requested,
        "proposal_requested": proposal_requested,
        "variance": round(requested - proposal_requested, 2),
    }


def analyze(plan: Plan, proposal_requested: float) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(level: str, message: str) -> None:
        checks.append({"level": level, "message": message})

    duration = plan.duration_months
    wp_ids = [w.id for w in plan.work_packages]
    if len(set(wp_ids)) != len(wp_ids):
        add("error", "Work package ids must be unique.")
    for w in plan.work_packages:
        label = f"{w.id} {w.title}".strip()
        if w.end_month < w.start_month:
            add("error", f"{label}: ends (month {w.end_month}) before it starts (month {w.start_month}).")
        if w.end_month > duration:
            add("error", f"{label}: ends in month {w.end_month}, after the {duration}-month project.")
        if not w.deliverables:
            add("warning", f"{label}: has no deliverables.")
        for t in w.tasks:
            if t.end_month < t.start_month or t.start_month < w.start_month or t.end_month > w.end_month:
                add("error", f"{label}, task {t.id}: months {t.start_month}-{t.end_month} fall outside the work package (months {w.start_month}-{w.end_month}).")
        for d in w.deliverables:
            if d.month > duration or d.month < w.start_month or d.month > w.end_month:
                add("warning", f"{label}, deliverable {d.id}: month {d.month} is outside the work package span.")
        for m in w.milestones:
            if m.month > duration:
                add("warning", f"{label}, milestone {m.id}: month {m.month} is after the project ends.")
    if not plan.work_packages:
        add("warning", "No work packages defined yet.")

    budget = analyze_budget(plan, proposal_requested)
    known = set(wp_ids)
    for ln in plan.budget.lines:
        if ln.wp and ln.wp not in known:
            add("error", f"Budget line {ln.id} refers to unknown work package {ln.wp!r}.")
        if not ln.wp:
            add("warning", f"Budget line {ln.id} is not assigned to a work package.")
        if ln.category == "personnel" and ln.unit and "month" not in ln.unit.lower() and "day" not in ln.unit.lower():
            add("warning", f"Budget line {ln.id}: personnel is usually costed in person-months or days.")
    if not plan.budget.lines:
        add("warning", "No budget lines yet.")
    elif proposal_requested > 0 and abs(budget["variance"]) > max(1.0, proposal_requested * 0.01):
        add(
            "warning",
            f"Budget requests {budget['requested']:,.2f} but the proposal requests {proposal_requested:,.2f} "
            f"(difference {budget['variance']:+,.2f}).",
        )

    risk = None
    for d in plan.documents:
        if d.key != "risk_register":
            continue
        rows = []
        for r in d.rows:
            score = r.likelihood * r.impact
            rows.append({"id": r.id, "score": score, "band": risk_band(score)})
            if score >= RISK_MEDIUM and not r.mitigation.strip():
                add("warning", f"Risk {r.id} scores {score} but has no mitigation.")
        risk = {"rows": sorted(rows, key=lambda x: -x["score"]), "high": sum(1 for x in rows if x["band"] == "high")}
    return {
        "budget": budget,
        "risk": risk,
        "checks": checks,
        "errors": sum(1 for c in checks if c["level"] == "error"),
        "warnings": sum(1 for c in checks if c["level"] == "warning"),
    }


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def export_markdown(title: str, currency: str, plan: Plan, analysis: dict[str, Any]) -> str:
    out = [f"# {title}: project plan", f"- **Duration:** {plan.duration_months} months", ""]
    out.append("## Work packages")
    for w in plan.work_packages:
        out += [f"### {w.id}: {w.title}", f"- **Lead:** {w.lead or 'TBC'}  |  **Months:** {w.start_month}-{w.end_month}"]
        if w.objectives.strip():
            out += ["", w.objectives.strip()]
        if w.tasks:
            out += ["", "| Task | Title | Months |", "| --- | --- | --- |"]
            out += [f"| {t.id} | {t.title} | {t.start_month}-{t.end_month} |" for t in w.tasks]
        if w.deliverables:
            out += ["", "| Deliverable | Title | Type | Month |", "| --- | --- | --- | --- |"]
            out += [f"| {d.id} | {d.title} | {d.type} | {d.month} |" for d in w.deliverables]
        if w.milestones:
            out += ["", "| Milestone | Title | Month |", "| --- | --- | --- |"]
            out += [f"| {m.id} | {m.title} | {m.month} |" for m in w.milestones]
        out.append("")
    b = analysis["budget"]
    out += ["## Budget", f"All amounts in {currency}.", "",
            "| Line | WP | Category | Description | Qty | Unit | Unit cost | Total |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    totals = {x["id"]: x["total"] for x in b["lines"]}
    for ln in plan.budget.lines:
        out.append(f"| {ln.id} | {ln.wp} | {ln.category} | {ln.description} | {ln.quantity:g} | {ln.unit} | {_fmt(ln.unit_cost)} | {_fmt(totals.get(ln.id, 0))} |")
    out += ["", f"- **Direct costs:** {_fmt(b['direct'])}",
            f"- **Indirect costs ({plan.budget.indirect_pct:g}%):** {_fmt(b['indirect'])}",
            f"- **Total cost:** {_fmt(b['total'])}", f"- **Match funding:** {_fmt(b['match_funding'])}",
            f"- **Funding requested:** {_fmt(b['requested'])}", ""]
    if b["by_wp"]:
        out += ["| Work package | Cost |", "| --- | --- |"] + [f"| {k} | {_fmt(v)} |" for k, v in b["by_wp"].items()] + [""]
    for d in plan.documents:
        out += [f"## {d.title}"]
        if d.key == "risk_register":
            out += ["", "| ID | Risk | Category | L | I | Score | Mitigation | Owner |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
            out += [f"| {r.id} | {r.description} | {r.category} | {r.likelihood} | {r.impact} | {r.likelihood * r.impact} ({risk_band(r.likelihood * r.impact)}) | {r.mitigation} | {r.owner} |" for r in d.rows]
        for s in d.sections:
            out += ["", f"### {s.title}", "", s.text.strip() or "_Not yet written._"]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
