"""Access control for proposals that are being worked on through the marketplace.

Proposals with no active marketplace job keep the original open behaviour. Once a job that
links a proposal is in progress, only that job's client, its accepted writer and marketplace
admins may read or change it.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import JobBrief
from bid_studio.services.auth import account_from_request, check_origin

ACTIVE_JOB_STATUSES = ("in_progress", "delivered")


def active_job_for_proposal(db: Session, proposal_id: int) -> JobBrief | None:
    return (
        db.query(JobBrief)
        .filter(JobBrief.proposal_id == proposal_id, JobBrief.status.in_(ACTIVE_JOB_STATUSES))
        .first()
    )


def proposal_guard(proposal_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    job = active_job_for_proposal(db, proposal_id)
    if job is None:
        return
    check_origin(request)
    account = account_from_request(db, request)
    if account is None:
        raise HTTPException(status_code=401, detail="Sign in to work on this proposal")
    allowed = account.role == "admin" or account.id in (job.client_account_id, job.writer_account_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="You are not part of the job for this proposal")
