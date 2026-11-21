import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.database import get_db
from bid_studio.models import (
    GrantProposal,
    JobBid,
    JobBrief,
    JobMessage,
    JobReview,
    MarketAccount,
    Workspace,
    WorkspaceMember,
    WriterProfile,
)
from bid_studio.services import auth, licensing
from bid_studio.services.access import active_job_for_proposal
from bid_studio.services.mailer import deliver

router = APIRouter(prefix="/api/v1/market", tags=["marketplace"])

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MESSAGE_STATUSES = ("in_progress", "delivered", "completed")


# ---------------------------------------------------------------- schemas

class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_RE, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(pattern="^(writer|client)$")
    organisation: str = Field(default="", max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class SampleIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    url: str = Field(pattern=r"^https?://", max_length=500)


class ProfileIn(BaseModel):
    headline: str = Field(default="", max_length=200)
    bio: str = Field(default="", max_length=4000)
    specialisms: list[str] = Field(default_factory=list, max_length=20)
    funders: list[str] = Field(default_factory=list, max_length=20)
    day_rate: float = Field(default=0.0, ge=0, le=100000)
    currency: str = Field(default="GBP", min_length=3, max_length=10)
    samples: list[SampleIn] = Field(default_factory=list, max_length=10)


class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=220)
    description: str = Field(default="", max_length=8000)
    funder: str = Field(default="", max_length=200)
    deadline: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    budget_min: float = Field(default=0.0, ge=0)
    budget_max: float = Field(default=0.0, ge=0)
    currency: str = Field(default="GBP", min_length=3, max_length=10)
    proposal_id: int | None = None


class BidIn(BaseModel):
    price: float = Field(gt=0, le=10_000_000)
    timeline_days: int = Field(default=14, ge=1, le=730)
    message: str = Field(default="", max_length=4000)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class ChangesIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


# ---------------------------------------------------------------- dependencies

def optional_account(request: Request, db: Session = Depends(get_db)) -> MarketAccount | None:
    auth.check_origin(request)
    return auth.account_from_request(db, request)


def current_account(account: MarketAccount | None = Depends(optional_account)) -> MarketAccount:
    if account is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return account


def role_required(*roles: str):
    def dep(account: MarketAccount = Depends(current_account)) -> MarketAccount:
        if account.role not in roles:
            raise HTTPException(status_code=403, detail=f"This needs a {' or '.join(roles)} account")
        return account

    return dep


# ---------------------------------------------------------------- helpers

def _account_dict(a: MarketAccount, db: Session) -> dict:
    profile = db.query(WriterProfile).filter(WriterProfile.account_id == a.id).first()
    return {
        "id": a.id,
        "email": a.email,
        "name": a.name,
        "role": a.role,
        "organisation": a.organisation,
        "workspace_id": a.workspace_id,
        "writer_status": profile.status if profile else None,
    }


def _writer_dict(p: WriterProfile, name: str) -> dict:
    return {
        "id": p.id,
        "name": name,
        "headline": p.headline,
        "bio": p.bio,
        "specialisms": p.specialisms,
        "funders": p.funders,
        "day_rate": p.day_rate,
        "currency": p.currency,
        "samples": p.samples,
        "rating_avg": p.rating_avg,
        "rating_count": p.rating_count,
        "completed_jobs": p.completed_jobs,
    }


def _name_of(db: Session, account_id: int | None) -> str:
    a = db.get(MarketAccount, account_id) if account_id else None
    return a.name if a else ""


def _participant(job: JobBrief, account: MarketAccount) -> bool:
    return account.role == "admin" or account.id in (job.client_account_id, job.writer_account_id)


def _job_dict(job: JobBrief, db: Session, account: MarketAccount | None) -> dict:
    mine = account is not None and _participant(job, account)
    data = {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "funder": job.funder,
        "deadline": job.deadline or None,
        "budget_min": job.budget_min,
        "budget_max": job.budget_max,
        "currency": job.currency,
        "status": job.status,
        "client_name": _name_of(db, job.client_account_id),
        "bid_count": db.query(JobBid).filter(JobBid.job_id == job.id).count(),
        "created_at": job.created_at,
        "is_client": account is not None and account.id == job.client_account_id,
        "is_writer": account is not None and account.id == job.writer_account_id,
    }
    if mine:
        data.update(
            {
                "proposal_id": job.proposal_id,
                "writer_name": _name_of(db, job.writer_account_id),
                "agreed_price": job.agreed_price,
                "platform_fee": job.platform_fee,
                "payment_status": job.payment_status,
            }
        )
    return data


def _get_job(db: Session, job_id: int) -> JobBrief:
    job = db.get(JobBrief, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _notify(db: Session, job: JobBrief, to_id: int | None, subject: str, body: str, kind: str):
    to = db.get(MarketAccount, to_id) if to_id else None
    if to:
        deliver(
            db,
            workspace_id=job.workspace_id,
            to=to.email,
            subject=subject,
            body=body,
            delivery_type=kind,
            reference_id=job.id,
        )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "development",
        max_age=settings.session_days * 86400,
        path="/",
    )


# ---------------------------------------------------------------- auth

@router.post("/auth/register", status_code=201)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.query(MarketAccount).filter(MarketAccount.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    role = "admin" if auth.is_admin_email(email) else payload.role
    workspace_id = None
    if role == "client":
        try:
            licensing.check_limit(db, "workspace")
        except licensing.LicenseError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        ws = Workspace(
            slug=f"client-{secrets.token_hex(4)}",
            name=payload.organisation or payload.name,
            brand_name=payload.organisation or payload.name,
        )
        db.add(ws)
        db.flush()
        workspace_id = ws.id
    account = MarketAccount(
        email=email,
        name=payload.name.strip(),
        password_hash=auth.hash_password(payload.password),
        role=role,
        organisation=payload.organisation,
        workspace_id=workspace_id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    _set_session_cookie(response, auth.create_session(db, account))
    return _account_dict(account, db)


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    key = f"{email}|{request.client.host if request.client else ''}"
    auth.check_rate_limit(key)
    account = db.query(MarketAccount).filter(MarketAccount.email == email).first()
    stored = account.password_hash if account else auth.hash_password("dummy-password-for-timing")
    if not (auth.verify_password(payload.password, stored) and account):
        auth.record_failure(key)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    auth.clear_failures(key)
    _set_session_cookie(response, auth.create_session(db, account))
    return _account_dict(account, db)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_origin(request)
    auth.destroy_session(db, request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)):
    return _account_dict(account, db)


# ---------------------------------------------------------------- writers

@router.get("/writers")
def list_writers(
    response: Response,
    q: str | None = None,
    specialism: str | None = None,
    funder: str | None = None,
    max_rate: float | None = Query(default=None, ge=0),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    sort: str = Query(default="rating", pattern="^(rating|rate|jobs|newest)$"),
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = (
        db.query(WriterProfile, MarketAccount)
        .join(MarketAccount, MarketAccount.id == WriterProfile.account_id)
        .filter(WriterProfile.status == "approved")
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                MarketAccount.name.ilike(like),
                WriterProfile.headline.ilike(like),
                WriterProfile.bio.ilike(like),
                cast(WriterProfile.specialisms, String).ilike(like),
                cast(WriterProfile.funders, String).ilike(like),
            )
        )
    if specialism:
        query = query.filter(cast(WriterProfile.specialisms, String).ilike(f'%"{specialism}"%'))
    if funder:
        query = query.filter(cast(WriterProfile.funders, String).ilike(f'%"{funder}"%'))
    if max_rate is not None:
        query = query.filter(WriterProfile.day_rate <= max_rate)
    if min_rating is not None:
        query = query.filter(WriterProfile.rating_avg >= min_rating)
    order = {
        "rating": [WriterProfile.rating_avg.desc(), WriterProfile.rating_count.desc()],
        "rate": [WriterProfile.day_rate.asc()],
        "jobs": [WriterProfile.completed_jobs.desc()],
        "newest": [WriterProfile.id.desc()],
    }[sort]
    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(*order, WriterProfile.id).offset(offset).limit(limit).all()
    return [_writer_dict(p, a.name) for p, a in rows]


@router.get("/writers/me")
def my_profile(account: MarketAccount = Depends(role_required("writer")), db: Session = Depends(get_db)):
    p = db.query(WriterProfile).filter(WriterProfile.account_id == account.id).first()
    if not p:
        return {"exists": False, "status": None}
    return {"exists": True, "status": p.status, **_writer_dict(p, account.name)}


@router.put("/writers/me")
def save_my_profile(
    payload: ProfileIn,
    account: MarketAccount = Depends(role_required("writer")),
    db: Session = Depends(get_db),
):
    p = db.query(WriterProfile).filter(WriterProfile.account_id == account.id).first()
    data = payload.model_dump()
    data["samples"] = [s.model_dump() for s in payload.samples]
    data["specialisms"] = [s.strip() for s in payload.specialisms if s.strip()]
    data["funders"] = [s.strip() for s in payload.funders if s.strip()]
    if p is None:
        p = WriterProfile(account_id=account.id, status="pending", **data)
        db.add(p)
    else:
        if p.status == "suspended":
            raise HTTPException(status_code=403, detail="Your profile is suspended; contact support")
        for k, v in data.items():
            setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return {"status": p.status, **_writer_dict(p, account.name)}


@router.get("/writers/{writer_id}")
def get_writer(writer_id: int, db: Session = Depends(get_db)):
    p = db.get(WriterProfile, writer_id)
    if not p or p.status != "approved":
        raise HTTPException(status_code=404, detail="Writer not found")
    return _writer_dict(p, _name_of(db, p.account_id))


@router.get("/writers/{writer_id}/reviews")
def writer_reviews(writer_id: int, db: Session = Depends(get_db)):
    p = db.get(WriterProfile, writer_id)
    if not p or p.status != "approved":
        raise HTTPException(status_code=404, detail="Writer not found")
    rows = (
        db.query(JobReview, JobBrief)
        .join(JobBrief, JobBrief.id == JobReview.job_id)
        .filter(JobReview.writer_account_id == p.account_id)
        .order_by(JobReview.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "rating": r.rating,
            "comment": r.comment,
            "job_title": j.title,
            "reviewer": _name_of(db, r.reviewer_account_id),
            "created_at": r.created_at,
        }
        for r, j in rows
    ]


@router.get("/admin/writers")
def admin_list_writers(
    status: str = "pending",
    _: MarketAccount = Depends(role_required("admin")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WriterProfile, MarketAccount)
        .join(MarketAccount, MarketAccount.id == WriterProfile.account_id)
        .filter(WriterProfile.status == status)
        .order_by(WriterProfile.id)
        .all()
    )
    return [{**_writer_dict(p, a.name), "email": a.email, "status": p.status} for p, a in rows]


def _set_writer_status(db: Session, writer_id: int, status: str) -> dict:
    p = db.get(WriterProfile, writer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Writer not found")
    p.status = status
    db.commit()
    return {"id": p.id, "status": p.status}


@router.post("/admin/writers/{writer_id}/approve")
def approve_writer(
    writer_id: int, _: MarketAccount = Depends(role_required("admin")), db: Session = Depends(get_db)
):
    return _set_writer_status(db, writer_id, "approved")


@router.post("/admin/writers/{writer_id}/suspend")
def suspend_writer(
    writer_id: int, _: MarketAccount = Depends(role_required("admin")), db: Session = Depends(get_db)
):
    return _set_writer_status(db, writer_id, "suspended")


# ---------------------------------------------------------------- jobs

def _approved_writer(db: Session, account: MarketAccount) -> WriterProfile:
    p = db.query(WriterProfile).filter(WriterProfile.account_id == account.id).first()
    if not p or p.status != "approved":
        raise HTTPException(status_code=403, detail="Your writer profile must be approved first")
    return p


@router.post("/jobs", status_code=201)
def create_job(
    payload: JobIn,
    account: MarketAccount = Depends(role_required("client")),
    db: Session = Depends(get_db),
):
    if payload.budget_max and payload.budget_max < payload.budget_min:
        raise HTTPException(status_code=422, detail="Maximum budget is below the minimum")
    if payload.proposal_id is not None:
        proposal = db.get(GrantProposal, payload.proposal_id)
        if not proposal or proposal.workspace_id != account.workspace_id:
            raise HTTPException(status_code=404, detail="Proposal not found in your workspace")
        clash = (
            db.query(JobBrief)
            .filter(
                JobBrief.proposal_id == payload.proposal_id,
                JobBrief.status.in_(("open", "in_progress", "delivered")),
            )
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="This proposal already has a live job")
    job = JobBrief(
        client_account_id=account.id, workspace_id=account.workspace_id, **payload.model_dump()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_dict(job, db, account)


@router.get("/jobs")
def list_jobs(
    response: Response,
    scope: str = Query(default="open", pattern="^(open|mine)$"),
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    account: MarketAccount = Depends(current_account),
    db: Session = Depends(get_db),
):
    query = db.query(JobBrief)
    if scope == "mine":
        bid_job_ids = db.query(JobBid.job_id).filter(JobBid.writer_account_id == account.id)
        if account.role != "admin":
            query = query.filter(
                or_(
                    JobBrief.client_account_id == account.id,
                    JobBrief.writer_account_id == account.id,
                    JobBrief.id.in_(bid_job_ids),
                )
            )
    else:
        if account.role == "client":
            raise HTTPException(status_code=403, detail="Clients see their own briefs under scope=mine")
        if account.role == "writer":
            _approved_writer(db, account)
        query = query.filter(JobBrief.status == "open")
    if q:
        like = f"%{q}%"
        query = query.filter(or_(JobBrief.title.ilike(like), JobBrief.description.ilike(like), JobBrief.funder.ilike(like)))
    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(JobBrief.id.desc()).offset(offset).limit(limit).all()
    return [_job_dict(j, db, account) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if not _participant(job, account):
        has_bid = (
            db.query(JobBid)
            .filter(JobBid.job_id == job.id, JobBid.writer_account_id == account.id)
            .first()
        )
        if not (has_bid or (job.status == "open" and account.role == "writer")):
            raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/bids", status_code=201)
def place_bid(
    job_id: int,
    payload: BidIn,
    account: MarketAccount = Depends(role_required("writer")),
    db: Session = Depends(get_db),
):
    _approved_writer(db, account)
    job = _get_job(db, job_id)
    if job.status != "open":
        raise HTTPException(status_code=409, detail="This job is no longer open for bids")
    if db.query(JobBid).filter(JobBid.job_id == job.id, JobBid.writer_account_id == account.id).first():
        raise HTTPException(status_code=409, detail="You have already bid on this job")
    bid = JobBid(job_id=job.id, writer_account_id=account.id, currency=job.currency, **payload.model_dump())
    db.add(bid)
    _notify(db, job, job.client_account_id, f"New bid on '{job.title}'",
            f"{account.name} bid {job.currency} {payload.price:,.2f} ({payload.timeline_days} days).", "market_bid")
    db.commit()
    db.refresh(bid)
    return {"id": bid.id, "status": bid.status, "price": bid.price}


def _bid_dict(b: JobBid, db: Session) -> dict:
    p = db.query(WriterProfile).filter(WriterProfile.account_id == b.writer_account_id).first()
    return {
        "id": b.id,
        "job_id": b.job_id,
        "writer_id": p.id if p else None,
        "writer_name": _name_of(db, b.writer_account_id),
        "writer_rating": p.rating_avg if p else 0,
        "writer_rating_count": p.rating_count if p else 0,
        "price": b.price,
        "currency": b.currency,
        "timeline_days": b.timeline_days,
        "message": b.message,
        "status": b.status,
        "created_at": b.created_at,
    }


@router.get("/jobs/{job_id}/bids")
def list_bids(job_id: int, account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    query = db.query(JobBid).filter(JobBid.job_id == job.id)
    if not (account.id == job.client_account_id or account.role == "admin"):
        query = query.filter(JobBid.writer_account_id == account.id)  # writers see only their own
    return [_bid_dict(b, db) for b in query.order_by(JobBid.price).all()]


@router.post("/jobs/{job_id}/bids/{bid_id}/withdraw")
def withdraw_bid(
    job_id: int, bid_id: int, account: MarketAccount = Depends(role_required("writer")), db: Session = Depends(get_db)
):
    bid = db.get(JobBid, bid_id)
    if not bid or bid.job_id != job_id or bid.writer_account_id != account.id:
        raise HTTPException(status_code=404, detail="Bid not found")
    if bid.status != "pending":
        raise HTTPException(status_code=409, detail=f"A {bid.status} bid cannot be withdrawn")
    bid.status = "withdrawn"
    db.commit()
    return _bid_dict(bid, db)


@router.post("/jobs/{job_id}/bids/{bid_id}/accept")
def accept_bid(
    job_id: int, bid_id: int, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)
):
    job = _get_job(db, job_id)
    if job.client_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "open":
        raise HTTPException(status_code=409, detail="This job is not open")
    bid = db.get(JobBid, bid_id)
    if not bid or bid.job_id != job.id or bid.status != "pending":
        raise HTTPException(status_code=404, detail="Pending bid not found")
    writer = db.get(MarketAccount, bid.writer_account_id)
    try:
        licensing.check_limit(db, "member", job.workspace_id)
    except licensing.LicenseError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    for other in db.query(JobBid).filter(JobBid.job_id == job.id, JobBid.id != bid.id, JobBid.status == "pending"):
        other.status = "rejected"
    bid.status = "accepted"
    job.status = "in_progress"
    job.accepted_bid_id = bid.id
    job.writer_account_id = bid.writer_account_id
    job.agreed_price = bid.price
    job.platform_fee = round(bid.price * settings.marketplace_fee_pct / 100.0, 2)
    exists = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == job.workspace_id, WorkspaceMember.email == writer.email)
        .first()
    )
    if not exists:
        db.add(WorkspaceMember(workspace_id=job.workspace_id, email=writer.email, full_name=writer.name, role="writer"))
    _notify(db, job, writer.id, f"Your bid was accepted: '{job.title}'",
            f"Agreed price {job.currency} {job.agreed_price:,.2f}. Open the job to start.", "market_accepted")
    db.commit()
    return _job_dict(job, db, account)


def _transition(db, job, account, *, who, from_states, to_state, notify_to, subject, body, kind):
    if who == "client" and job.client_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if who == "writer" and job.writer_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in from_states:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}; expected {' or '.join(from_states)}")
    job.status = to_state
    if notify_to:
        _notify(db, job, notify_to, subject, body, kind)


@router.post("/jobs/{job_id}/deliver")
def deliver_job(job_id: int, account: MarketAccount = Depends(role_required("writer")), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _transition(db, job, account, who="writer", from_states=("in_progress",), to_state="delivered",
                notify_to=job.client_account_id, subject=f"Delivered: '{job.title}'",
                body="The writer has marked the work as delivered. Please review it.", kind="market_delivered")
    db.commit()
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/approve")
def approve_job(job_id: int, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _transition(db, job, account, who="client", from_states=("delivered",), to_state="completed",
                notify_to=job.writer_account_id, subject=f"Approved: '{job.title}'",
                body="The client approved your work. Thank you!", kind="market_completed")
    profile = db.query(WriterProfile).filter(WriterProfile.account_id == job.writer_account_id).first()
    if profile:
        profile.completed_jobs += 1
    db.commit()
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/request-changes")
def request_changes(
    job_id: int, payload: ChangesIn, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)
):
    job = _get_job(db, job_id)
    _transition(db, job, account, who="client", from_states=("delivered",), to_state="in_progress",
                notify_to=job.writer_account_id, subject=f"Changes requested: '{job.title}'",
                body=payload.note, kind="market_changes")
    db.add(JobMessage(job_id=job.id, sender_account_id=account.id, body=f"Changes requested: {payload.note}"))
    db.commit()
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _transition(db, job, account, who="client", from_states=("open", "in_progress"), to_state="cancelled",
                notify_to=job.writer_account_id, subject=f"Cancelled: '{job.title}'",
                body="The client cancelled this job.", kind="market_cancelled")
    for b in db.query(JobBid).filter(JobBid.job_id == job.id, JobBid.status == "pending"):
        b.status = "rejected"
    db.commit()
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/payment/mark-paid")
def mark_paid(job_id: int, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if job.client_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("in_progress", "delivered", "completed") or job.payment_status != "unpaid":
        raise HTTPException(status_code=409, detail="Payment cannot be marked as paid now")
    job.payment_status = "client_marked_paid"
    _notify(db, job, job.writer_account_id, f"Payment sent: '{job.title}'",
            "The client says they have paid you. Please confirm when it arrives.", "market_paid")
    db.commit()
    return _job_dict(job, db, account)


@router.post("/jobs/{job_id}/payment/confirm")
def confirm_payment(job_id: int, account: MarketAccount = Depends(role_required("writer")), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if job.writer_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.payment_status != "client_marked_paid":
        raise HTTPException(status_code=409, detail="No payment is waiting for confirmation")
    job.payment_status = "writer_confirmed"
    db.commit()
    return _job_dict(job, db, account)


# ---------------------------------------------------------------- messages and reviews

def _message_participant(job: JobBrief, account: MarketAccount) -> None:
    if not _participant(job, account):
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}/messages")
def list_messages(job_id: int, account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _message_participant(job, account)
    rows = db.query(JobMessage).filter(JobMessage.job_id == job.id).order_by(JobMessage.id).all()
    return [
        {"id": m.id, "sender": _name_of(db, m.sender_account_id), "mine": m.sender_account_id == account.id,
         "body": m.body, "created_at": m.created_at}
        for m in rows
    ]


@router.post("/jobs/{job_id}/messages", status_code=201)
def post_message(
    job_id: int, payload: MessageIn, account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)
):
    job = _get_job(db, job_id)
    _message_participant(job, account)
    if job.status not in MESSAGE_STATUSES:
        raise HTTPException(status_code=409, detail="Messaging opens once a bid is accepted")
    msg = JobMessage(job_id=job.id, sender_account_id=account.id, body=payload.body.strip())
    db.add(msg)
    other = job.writer_account_id if account.id == job.client_account_id else job.client_account_id
    _notify(db, job, other, f"New message on '{job.title}'", payload.body[:300], "market_message")
    db.commit()
    return {"id": msg.id}


@router.post("/jobs/{job_id}/review", status_code=201)
def review_writer(
    job_id: int, payload: ReviewIn, account: MarketAccount = Depends(role_required("client")), db: Session = Depends(get_db)
):
    job = _get_job(db, job_id)
    if job.client_account_id != account.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="You can review a writer once the job is completed")
    if db.query(JobReview).filter(JobReview.job_id == job.id).first():
        raise HTTPException(status_code=409, detail="This job has already been reviewed")
    db.add(JobReview(job_id=job.id, writer_account_id=job.writer_account_id,
                     reviewer_account_id=account.id, rating=payload.rating, comment=payload.comment))
    db.flush()
    ratings = [r.rating for r in db.query(JobReview).filter(JobReview.writer_account_id == job.writer_account_id)]
    profile = db.query(WriterProfile).filter(WriterProfile.account_id == job.writer_account_id).first()
    if profile:
        profile.rating_count = len(ratings)
        profile.rating_avg = round(sum(ratings) / len(ratings), 2)
    db.commit()
    return {"rating_avg": profile.rating_avg if profile else None, "rating_count": len(ratings)}


@router.get("/jobs/{job_id}/studio-link")
def studio_link(job_id: int, account: MarketAccount = Depends(current_account), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _message_participant(job, account)
    live = job.proposal_id and active_job_for_proposal(db, job.proposal_id)
    return {"proposal_id": job.proposal_id, "url": f"/app/studio/{job.proposal_id}" if job.proposal_id else None,
            "access_restricted": bool(live)}

