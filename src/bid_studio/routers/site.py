from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import ContactRequest
from bid_studio.schemas import ContactRequestCreate

router = APIRouter()

PAGES = {
    "/": ("site_home.html", "home"),
    "/features": ("site_features.html", "features"),
    "/pricing": ("site_pricing.html", "pricing"),
    "/about": ("site_about.html", "about"),
    "/contact": ("site_contact.html", "contact"),
}


def _make_page(template: str, active: str):
    def page(request: Request) -> HTMLResponse:
        return request.app.state.templates.TemplateResponse(
            request=request, name=template, context={"active": active}
        )

    return page


for _path, (_template, _active) in PAGES.items():
    router.add_api_route(
        _path,
        _make_page(_template, _active),
        methods=["GET"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )


@router.post("/api/v1/contact", status_code=201, tags=["site"])
def submit_contact_request(payload: ContactRequestCreate, db: Session = Depends(get_db)):
    item = ContactRequest(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": "received"}
