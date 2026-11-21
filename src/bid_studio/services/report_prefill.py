"""Pre-fill documents from the proposal or tender they are linked to.

Anything the system cannot know (status, spend to date, where a criterion is answered) is left as a
[TO CONFIRM: ...] placeholder, which also blocks submission until a person fills it in.
"""

from typing import Any

from bid_studio.models import GrantProposal, OpportunityNotice, ProposalPlan
from bid_studio.services import plan as planlib


def _plan_for(db, proposal: GrantProposal) -> planlib.Plan:
    row = db.query(ProposalPlan).filter(ProposalPlan.proposal_id == proposal.id).first()
    return planlib.Plan.model_validate(row.data) if row and row.data else planlib.Plan()


def funder_report(db, proposal: GrantProposal, final: bool) -> dict[str, str]:
    plan = _plan_for(db, proposal)
    analysis = planlib.analyze(plan, proposal.requested_amount or 0.0)
    cur = proposal.currency
    kind = "final report" if final else "progress report"
    out = {
        "summary": (
            f"This is the {kind} for \"{proposal.title}\" ({proposal.applicant_org or 'applicant'}). "
            "Reporting period: [TO CONFIRM: dates]. Headline: [TO CONFIRM: one-line summary of progress]."
        ),
    }
    rows = [
        f"| {w.id} {w.title} | {d.id} {d.title} | month {d.month} | [TO CONFIRM: complete / in progress / delayed] |"
        for w in plan.work_packages for d in w.deliverables
    ] + [
        f"| {w.id} {w.title} | Milestone {m.id} {m.title} | month {m.month} | [TO CONFIRM: achieved / due / delayed] |"
        for w in plan.work_packages for m in w.milestones
    ]
    if rows:
        out["deliverables"] = "\n".join(
            ["| Work package | Deliverable or milestone | Planned | Status |", "| --- | --- | --- | --- |", *rows]
        )
    budget = analysis["budget"]
    if budget["total"]:
        lines = [
            f"| {wp} | {amount:,.2f} | [TO CONFIRM] | [TO CONFIRM] |" for wp, amount in budget["by_wp"].items()
        ]
        out["budget"] = "\n".join(
            [f"All amounts in {cur}.", "",
             "| Work package | Budget | Spent to date | Variance |", "| --- | --- | --- | --- |", *lines, "",
             f"Total budget {budget['total']:,.2f}, of which funding requested {budget['requested']:,.2f} "
             f"and match funding {budget['match_funding']:,.2f}. Forecast to completion: [TO CONFIRM]."]
        )
    if plan.work_packages:
        out["progress"] = "\n".join(
            f"- **{w.id} {w.title}** (months {w.start_month}-{w.end_month}): [TO CONFIRM: progress against plan]"
            for w in plan.work_packages
        )
    return out


def method_statement(notice: OpportunityNotice) -> dict[str, str]:
    criteria: list[dict[str, Any]] = notice.structured_criteria or []
    if not criteria:
        return {}
    lines = [
        f"- **{c.get('title', 'Criterion')}** ({c.get('weight', '?')}%): [TO CONFIRM: which section answers this]"
        for c in criteria
    ]
    return {"criteria_map": "\n".join(lines)}
