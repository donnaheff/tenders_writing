from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.database import get_db
from bid_studio.models import (
    AlertSubscription,
    EmailDeliveryLog,
    GrantProposal,
    OpportunityNotice,
    Workspace,
)
from bid_studio.routers.intelligence import build_digest
from bid_studio.services.mailer import deliver
from bid_studio.services.pipeline import auto_process_call

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

CADENCE_DAYS = {"daily": 1, "weekly": 7}


def _check_secret(authorization: str | None) -> None:
    if not settings.cron_secret:
        return
    if authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def send_due_digests(db: Session, now: datetime) -> int:
    sent = 0
    subs = db.query(AlertSubscription).filter(AlertSubscription.active.is_(True)).all()
    for sub in subs:
        last = _aware(sub.last_sent_at)
        due_after = timedelta(days=CADENCE_DAYS.get(sub.cadence, 7))
        if last is None or now - last >= due_after:
            build_digest(db, sub)
            sent += 1
    db.commit()
    return sent


def send_deadline_reminders(db: Session, now: datetime) -> int:
    """Remind each workspace once about unfinished proposals whose call closes soon."""
    sent = 0
    window_end = now.date() + timedelta(days=settings.reminder_window_days)
    proposals = (
        db.query(GrantProposal).filter(GrantProposal.status.in_(["draft", "in_review"])).all()
    )
    for proposal in proposals:
        notice = db.get(OpportunityNotice, proposal.notice_id)
        if not notice:
            continue
        try:
            deadline = date.fromisoformat(notice.deadline)
        except ValueError:
            continue
        if not (now.date() <= deadline <= window_end):
            continue
        already = (
            db.query(EmailDeliveryLog)
            .filter(
                EmailDeliveryLog.delivery_type == "deadline_reminder",
                EmailDeliveryLog.reference_id == proposal.id,
            )
            .first()
        )
        if already:
            continue
        ws = db.get(Workspace, proposal.workspace_id)
        if not ws:
            continue
        days_left = (deadline - now.date()).days
        deliver(
            db,
            workspace_id=ws.id,
            to=ws.support_email,
            subject=f"Deadline in {days_left} day(s): {proposal.title}",
            body=(
                f"'{proposal.title}' is still {proposal.status} and the call closes on "
                f"{notice.deadline}. Current self-assessed score: "
                f"{proposal.total_weighted_score}%."
            ),
            delivery_type="deadline_reminder",
            reference_id=proposal.id,
        )
        sent += 1
    db.commit()
    return sent


def auto_process_default_workspace(db: Session) -> int:
    if not settings.auto_process_grants:
        return 0
    ws = db.query(Workspace).filter(Workspace.slug == settings.default_workspace_slug).first()
    if not ws:
        return 0
    calls = (
        db.query(OpportunityNotice)
        .filter(OpportunityNotice.notice_type == "grant_call", OpportunityNotice.status == "open")
        .all()
    )
    created = 0
    for call in calls:
        if call.workspace_id not in (None, ws.id):
            continue
        _, was_created = auto_process_call(db, call, ws.id)
        created += int(was_created)
    return created


def run_all(db: Session) -> dict:
    now = datetime.now(UTC)
    return {
        "ran_at": now.isoformat(),
        "proposals_auto_created": auto_process_default_workspace(db),
        "digests_sent": send_due_digests(db, now),
        "deadline_reminders_sent": send_deadline_reminders(db, now),
    }


@router.get("/run")
@router.post("/run")
def run_automation(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
):
    """Run every scheduled job once. Safe to call repeatedly (jobs are idempotent).

    Called daily by the Vercel cron in vercel.json. If CRON_SECRET is set the caller must
    send `Authorization: Bearer <CRON_SECRET>`, which Vercel cron does automatically.
    """
    _check_secret(authorization)
    return run_all(db)
