from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.database import get_db
from bid_studio.models import LicenseRecord, Workspace, WorkspaceMember
from bid_studio.services import licensing

router = APIRouter(prefix="/api/v1/license", tags=["license"])


class ActivateRequest(BaseModel):
    key: str = Field(min_length=10, max_length=4000)


def _status_payload(db: Session) -> dict:
    status = licensing.current_status(db)
    data = status.as_dict()
    data["source"] = "environment" if settings.license_key.strip() else "database"
    data["usage"] = {
        "workspaces": db.query(Workspace).count(),
        "max_members_in_a_workspace": max(
            (
                db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == w.id).count()
                for w in db.query(Workspace).all()
            ),
            default=0,
        ),
    }
    return data


@router.get("")
def get_license_status(db: Session = Depends(get_db)):
    return _status_payload(db)


@router.post("", status_code=201)
def activate_license(payload: ActivateRequest, db: Session = Depends(get_db)):
    """Install a licence key. Only a key signed by the vendor's private key is accepted."""
    key = payload.key.strip()
    try:
        lic = licensing.parse(key, settings.license_public_key)
    except licensing.LicenseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    status = licensing.evaluate(key)
    if status.state in ("expired", "revoked"):
        raise HTTPException(status_code=422, detail=status.message)
    db.add(LicenseRecord(key=key, key_id=lic.key_id, licensee=lic.licensee, plan=lic.plan))
    db.commit()
    return _status_payload(db)
