"""Accounts for the writers marketplace: scrypt passwords and database-backed sessions."""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.models import AuthSession, MarketAccount

SESSION_COOKIE = "bs_session"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MAX_FAILURES, FAILURE_WINDOW = 5, 600  # attempts per window (seconds)

# Per-process brute-force limiter. On multi-instance deployments use a shared store instead.
_failures: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_rate_limit(key: str) -> None:
    now = time.monotonic()
    recent = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW]
    _failures[key] = recent
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")


def record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.monotonic())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)


def create_session(db: Session, account: MarketAccount) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_hash_token(token),
            account_id=account.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return token


def destroy_session(db: Session, token: str | None) -> None:
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).delete()
        db.commit()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def account_from_request(db: Session, request: Request) -> MarketAccount | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).first()
    if not sess:
        return None
    if _aware(sess.expires_at) < datetime.now(UTC):
        db.delete(sess)
        db.commit()
        return None
    return db.get(MarketAccount, sess.account_id)


def check_origin(request: Request) -> None:
    """Reject cross-site state-changing requests (defence in depth beside SameSite=Lax)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin and origin.split("://", 1)[-1] != request.headers.get("host", ""):
        raise HTTPException(status_code=403, detail="Cross-site request blocked")


def is_admin_email(email: str) -> bool:
    admins = {e.strip().lower() for e in settings.marketplace_admin_emails.split(",") if e.strip()}
    return email.lower() in admins
