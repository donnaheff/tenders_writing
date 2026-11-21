"""Software licence keys: offline-verifiable, signed with Ed25519.

A key looks like `BS1.<payload>.<signature>` (both base64url). The payload is JSON describing
the licensee, plan and limits; the signature is made with the vendor's private key. The app
only ever holds the *public* key (LICENSE_PUBLIC_KEY), so it can verify keys but never mint them.
"""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from bid_studio.config import settings

PREFIX = "BS1"
PLANS = {
    # plan -> (max_workspaces, max_members_per_workspace); None means unlimited
    "starter": (1, 3),
    "team": (1, 15),
    "consultancy": (None, None),
}


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class License:
    key_id: str
    licensee: str
    plan: str
    max_workspaces: int | None
    max_members: int | None
    issued_at: str
    expires_at: str | None  # ISO date, None = perpetual

    def expiry(self) -> date | None:
        return date.fromisoformat(self.expires_at) if self.expires_at else None


class LicenseError(ValueError):
    """The key is malformed, forged or otherwise unusable."""


def sign(private_key: Ed25519PrivateKey, payload: dict[str, Any]) -> str:
    body = _b64e(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    sig = _b64e(private_key.sign(f"{PREFIX}.{body}".encode()))
    return f"{PREFIX}.{body}.{sig}"


def parse(key: str, public_key_b64: str) -> License:
    """Verify signature and structure. Does not judge expiry (see `evaluate`)."""
    if not public_key_b64:
        raise LicenseError("This installation has no LICENSE_PUBLIC_KEY configured")
    parts = (key or "").strip().split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenseError("Not a Bid Studio licence key")
    try:
        public = Ed25519PublicKey.from_public_bytes(_b64d(public_key_b64))
        public.verify(_b64d(parts[2]), f"{parts[0]}.{parts[1]}".encode())
    except InvalidSignature as exc:
        raise LicenseError("Licence key signature is invalid") from exc
    except Exception as exc:  # bad base64 / key length
        raise LicenseError("Licence key could not be read") from exc
    try:
        data = json.loads(_b64d(parts[1]))
        plan = data["plan"]
        if plan not in PLANS:
            raise LicenseError(f"Unknown plan {plan!r}")
        default_ws, default_members = PLANS[plan]
        lic = License(
            key_id=str(data["kid"]),
            licensee=str(data["licensee"]),
            plan=plan,
            max_workspaces=data.get("max_workspaces", default_ws),
            max_members=data.get("max_members", default_members),
            issued_at=str(data.get("issued_at", "")),
            expires_at=data.get("expires_at"),
        )
        lic.expiry()
    except LicenseError:
        raise
    except Exception as exc:
        raise LicenseError("Licence key payload is malformed") from exc
    return lic


def new_key_id() -> str:
    return _b64e(Ed25519PrivateKey.generate().public_key().public_bytes_raw())[:12]


def issue(
    private_key: Ed25519PrivateKey,
    *,
    licensee: str,
    plan: str,
    days: int | None = 365,
    max_workspaces: int | None = None,
    max_members: int | None = None,
    today: date | None = None,
) -> str:
    if plan not in PLANS:
        raise LicenseError(f"Unknown plan {plan!r}; use one of {sorted(PLANS)}")
    today = today or datetime.now(UTC).date()
    payload: dict[str, Any] = {
        "kid": new_key_id(),
        "licensee": licensee,
        "plan": plan,
        "issued_at": today.isoformat(),
        "expires_at": (today + timedelta(days=days)).isoformat() if days else None,
    }
    if max_workspaces is not None:
        payload["max_workspaces"] = max_workspaces
    if max_members is not None:
        payload["max_members"] = max_members
    return sign(private_key, payload)


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    return private, _b64e(private.public_key().public_bytes_raw())


@dataclass
class Status:
    state: str  # disabled | missing | invalid | valid | grace | expired | revoked
    allowed: bool
    enforcement: str
    license: License | None = None
    message: str = ""
    days_left: int | None = None

    def as_dict(self) -> dict[str, Any]:
        lic = self.license
        return {
            "state": self.state,
            "allowed": self.allowed,
            "enforcement": self.enforcement,
            "message": self.message,
            "days_left": self.days_left,
            "licensee": lic.licensee if lic else None,
            "plan": lic.plan if lic else None,
            "key_id": lic.key_id if lic else None,
            "expires_at": lic.expires_at if lic else None,
            "limits": {
                "max_workspaces": lic.max_workspaces if lic else None,
                "max_members": lic.max_members if lic else None,
            },
        }


def evaluate(key: str | None, today: date | None = None) -> Status:
    """Decide what the installation may do, given the configured enforcement mode."""
    mode = settings.license_enforcement.lower()
    if mode not in ("off", "warn", "on"):
        mode = "on"  # unknown value: fail closed
    today = today or datetime.now(UTC).date()

    if mode == "off":
        return Status("disabled", True, mode, message="Licence enforcement is off")

    def status(state, ok, **kw):
        # In warn mode nothing is blocked, but the state is still reported truthfully.
        return Status(state, ok or mode == "warn", mode, **kw)

    if not key:
        return status("missing", False, message="No licence key is installed")
    try:
        lic = parse(key, settings.license_public_key)
    except LicenseError as exc:
        return status("invalid", False, message=str(exc))
    revoked = {r.strip() for r in settings.license_revoked_ids.split(",") if r.strip()}
    if lic.key_id in revoked:
        return status("revoked", False, license=lic, message="This licence key has been revoked")

    expiry = lic.expiry()
    if expiry is None:
        return status("valid", True, license=lic, message="Perpetual licence")
    days_left = (expiry - today).days
    if days_left >= 0:
        return status("valid", True, license=lic, days_left=days_left, message=f"Valid until {expiry}")
    grace = settings.license_grace_days
    if -days_left <= grace:
        return status(
            "grace",
            True,
            license=lic,
            days_left=days_left,
            message=f"Expired on {expiry}; {grace + days_left} grace day(s) remain. Renew now.",
        )
    return status("expired", False, license=lic, days_left=days_left, message=f"Expired on {expiry}")


# ---------------------------------------------------------------- app integration

def installed_key(db) -> str:
    """The key in use: LICENSE_KEY env wins, otherwise the newest activated key."""
    from bid_studio.models import LicenseRecord  # local import avoids a models<->services cycle

    if settings.license_key.strip():
        return settings.license_key.strip()
    rec = db.query(LicenseRecord).order_by(LicenseRecord.id.desc()).first()
    return rec.key if rec else ""


def current_status(db) -> Status:
    return evaluate(installed_key(db))


PUBLIC_API_GETS = ("/api/v1/grants/feed", "/api/v1/market/writers", "/api/v1/market/job-types")  # the public /grants page reads these
OPEN_PATH_PREFIXES = ("/static", "/docs", "/redoc", "/openapi.json")
OPEN_API_PREFIXES = ("/api/v1/health", "/api/v1/license", "/api/v1/contact")


def needs_license(path: str, method: str) -> bool:
    """Which requests are blocked when the installation is unlicensed (enforcement on)."""
    if path.startswith("/app"):
        return path != "/app/license"
    if not path.startswith("/api/"):
        return False  # public marketing site, docs and static assets stay open
    if path.startswith(OPEN_API_PREFIXES):
        return False
    if method == "GET" and path.startswith(PUBLIC_API_GETS):
        return False
    return True


def check_limit(db, kind: str, workspace_id: int | None = None) -> None:
    """Raise LicenseError when adding another workspace/member would exceed the plan."""
    from bid_studio.models import Workspace, WorkspaceMember

    status = current_status(db)
    if status.state not in ("valid", "grace") or status.license is None:
        return  # disabled/warn/blocked states are handled elsewhere
    lic = status.license
    if kind == "workspace" and lic.max_workspaces is not None:
        if db.query(Workspace).count() >= lic.max_workspaces:
            raise LicenseError(
                f"Your {lic.plan} licence allows {lic.max_workspaces} workspace(s). Upgrade to add more."
            )
    if kind == "member" and lic.max_members is not None:
        count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).count()
        if count >= lic.max_members:
            raise LicenseError(
                f"Your {lic.plan} licence allows {lic.max_members} member(s) per workspace. Upgrade to add more."
            )
