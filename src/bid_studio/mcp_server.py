"""Bid Studio MCP server.

Exposes Bid Studio to any Model Context Protocol client (Claude, ChatGPT / OpenAI
Responses API and Agents SDK, Gemini, Cursor, VS Code, ...). Every tool is a thin
wrapper over the public REST API, so business rules live in exactly one place.

Transports
- Streamable HTTP, mounted by the FastAPI app at ``/mcp`` (see ``main.py``).
- stdio, via ``bid-studio-mcp`` / ``python -m bid_studio.mcp_server``. Set
  ``BID_STUDIO_API_URL`` to point it at a remote Bid Studio deployment.

Human-gated actions (quality-queue approval, email delivery) are deliberately NOT
exposed: an AI client should never approve its own work.
"""

from __future__ import annotations

import hmac
import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from bid_studio.config import settings

SERVER_NAME = "bid-studio"
SERVER_VERSION = "0.1.0"

INSTRUCTIONS = (
    "Bid Studio is a tender, grant and compliance writing platform. Start with "
    "list_workspaces to get a workspace_id, then search_opportunities or "
    "list_grant_calls to find work. Drafting tools create drafts only; quality "
    "approval is a human step done in the Bid Studio dashboard. Money values are "
    "in the notice's own currency."
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

# --------------------------------------------------------------------------- backend

_backend_app: Any = None


def set_backend_app(app: Any) -> None:
    """Route tool calls to this FastAPI app in-process (no network hop)."""
    global _backend_app
    _backend_app = app


class ApiError(RuntimeError):
    """Raised when the Bid Studio API rejects a call; surfaces as an MCP tool error."""


async def call_api(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
) -> tuple[Any, httpx.Headers]:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    remote = os.environ.get("BID_STUDIO_API_URL") or settings.api_base_url
    if remote:
        headers = {}
        key = os.environ.get("BID_STUDIO_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        client = httpx.AsyncClient(base_url=remote.rstrip("/"), headers=headers, timeout=30)
    else:
        if _backend_app is None:  # stdio without a remote URL: run against the local app
            from bid_studio.database import Base, SessionLocal, engine
            from bid_studio.main import app as local_app
            from bid_studio.seed import seed_database

            # The app lifespan doesn't run in stdio mode, so prepare the database here.
            Base.metadata.create_all(bind=engine)
            if settings.seed_on_startup:
                with SessionLocal() as db:
                    seed_database(db)
            set_backend_app(local_app)
        transport = httpx.ASGITransport(app=_backend_app)
        client = httpx.AsyncClient(transport=transport, base_url="http://bid-studio.local")
    async with client:
        resp = await client.request(method, path, params=params, json=json)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"Bid Studio API {resp.status_code}: {detail}")
    return resp.json(), resp.headers


async def _get(path: str, **params: Any) -> Any:
    data, _ = await call_api("GET", path, params=params)
    return data


async def _send(method: str, path: str, body: Any = None) -> Any:
    data, _ = await call_api(method, path, json=body)
    return data


def _trim_notice(n: dict[str, Any], include_pack_text: bool) -> dict[str, Any]:
    if not include_pack_text:
        n = {k: v for k, v in n.items() if k != "raw_pack_text"}
    return n


# --------------------------------------------------------------------------- server


def build_server() -> MCPServer:
    mcp = MCPServer(
        name=SERVER_NAME,
        title="Bid Studio",
        instructions=INSTRUCTIONS,
        version=SERVER_VERSION,
    )

    # ---- workspaces ------------------------------------------------------
    @mcp.tool(annotations=READ)
    async def list_workspaces() -> dict[str, Any]:
        """List workspaces (id, slug, name, branding). Call first to obtain a workspace_id."""
        return {"items": await _get("/api/v1/workspaces")}

    @mcp.tool(annotations=READ)
    async def get_workspace_summary(workspace_id: int) -> dict[str, Any]:
        """KPI summary for a workspace: open opportunities, proposals, queue depth, orders."""
        return await _get(f"/api/v1/workspaces/{workspace_id}/summary")

    # ---- opportunities ---------------------------------------------------
    @mcp.tool(annotations=READ)
    async def search_opportunities(
        query: str | None = None,
        notice_type: Literal["tender", "awarded_tender", "grant_call"] | None = None,
        sector: str | None = None,
        status: Literal["open", "awarded", "closed"] | None = None,
        workspace_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
        include_pack_text: bool = False,
    ) -> dict[str, Any]:
        """Search tenders, awarded notices and grant calls by keyword, type, sector or status.

        Returns items plus total_count for pagination. The full tender pack text is omitted
        unless include_pack_text is true (it can be large).
        """
        data, headers = await call_api(
            "GET",
            "/api/v1/notices",
            params={
                "q": query,
                "notice_type": notice_type,
                "sector": sector,
                "status": status,
                "workspace_id": workspace_id,
                "limit": max(1, min(limit, 100)),
                "offset": max(0, offset),
            },
        )
        return {
            "total_count": int(headers.get("x-total-count", len(data))),
            "items": [_trim_notice(n, include_pack_text) for n in data],
        }

    # ---- grants ----------------------------------------------------------
    @mcp.tool(annotations=READ)
    async def list_grant_calls(
        funder: str | None = None, workspace_id: int | None = None
    ) -> dict[str, Any]:
        """List funding calls (Horizon Europe, UKRI, World Bank, foundations). Filter by funder."""
        calls = await _get("/api/v1/grants/calls", funder=funder, workspace_id=workspace_id)
        return {"items": [_trim_notice(c, False) for c in calls]}

    @mcp.tool(annotations=WRITE)
    async def extract_grant_criteria(notice_id: int) -> dict[str, Any]:
        """Extract the scoring criteria and weights from a funding call."""
        return await _send("POST", f"/api/v1/grants/calls/{notice_id}/extract-criteria")

    @mcp.tool(annotations=WRITE)
    async def create_grant_proposal(
        notice_id: int,
        applicant_org: str,
        workspace_id: int = 1,
        title: str | None = None,
        requested_amount: float | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Create a draft proposal for a funding call, with one section per scoring criterion."""
        return await _send(
            "POST",
            "/api/v1/grants/proposals",
            {
                k: v
                for k, v in {
                    "workspace_id": workspace_id,
                    "notice_id": notice_id,
                    "applicant_org": applicant_org,
                    "title": title,
                    "requested_amount": requested_amount,
                    "currency": currency,
                }.items()
                if v is not None
            },
        )

    @mcp.tool(annotations=READ)
    async def list_grant_proposals(workspace_id: int = 1) -> dict[str, Any]:
        """List grant proposals in a workspace with status and weighted self-score."""
        return {"items": await _get("/api/v1/grants/proposals", workspace_id=workspace_id)}

    @mcp.tool(annotations=WRITE)
    async def update_grant_proposal_sections(
        proposal_id: int, sections: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace a proposal's sections. Each section needs criterion_id, title, weight,
        draft_text and optionally max_score, self_score and evidence_refs."""
        return await _send(
            "PUT", f"/api/v1/grants/proposals/{proposal_id}/sections", {"sections": sections}
        )

    @mcp.tool(annotations=WRITE)
    async def submit_grant_proposal_for_review(proposal_id: int) -> dict[str, Any]:
        """Queue a proposal for human quality review. Approval itself is done by a person."""
        return await _send("POST", f"/api/v1/grants/proposals/{proposal_id}/submit-review")

    @mcp.tool(annotations=READ)
    async def export_grant_proposal(proposal_id: int) -> dict[str, Any]:
        """Export a proposal as Markdown."""
        return await _get(f"/api/v1/grants/proposals/{proposal_id}/export")

    # ---- libraries & compliance -----------------------------------------
    @mcp.tool(annotations=READ)
    async def search_answer_library(
        query: str | None = None, workspace_id: int = 1
    ) -> dict[str, Any]:
        """Find reusable verified answers (security, quality, ESG, ...) by keyword."""
        items = await _get("/api/v1/answer-library", workspace_id=workspace_id)
        if query:
            terms = query.lower().split()
            items = [
                i
                for i in items
                if all(
                    t in f"{i.get('question_pattern', '')} {i.get('answer_text', '')} "
                    f"{i.get('category', '')} {' '.join(i.get('tags') or [])}".lower()
                    for t in terms
                )
            ]
        return {"items": items}

    @mcp.tool(annotations=WRITE)
    async def add_answer_library_item(
        question_pattern: str,
        answer_text: str,
        category: str = "security",
        tags: list[str] | None = None,
        workspace_id: int = 1,
    ) -> dict[str, Any]:
        """Add a verified, reusable answer to the library."""
        return await _send(
            "POST",
            "/api/v1/answer-library",
            {
                "workspace_id": workspace_id,
                "category": category,
                "question_pattern": question_pattern,
                "answer_text": answer_text,
                "tags": tags or [],
            },
        )

    @mcp.tool(annotations=WRITE)
    async def create_compliance_pack(
        title: str,
        pack_type: Literal[
            "iso_9001", "iso_27001", "security_questionnaire", "data_protection_policy"
        ],
        questions: list[str] | None = None,
        standard_ref: str = "ISO/IEC 27001:2022",
        workspace_id: int = 1,
    ) -> dict[str, Any]:
        """Create a compliance pack, optionally seeded with security-questionnaire questions."""
        return await _send(
            "POST",
            "/api/v1/compliance/packs",
            {
                "workspace_id": workspace_id,
                "pack_type": pack_type,
                "title": title,
                "standard_ref": standard_ref,
                "questions": questions or [],
            },
        )

    @mcp.tool(annotations=WRITE)
    async def auto_match_compliance_pack(pack_id: int) -> dict[str, Any]:
        """Match a pack's questionnaire against the Answer Library; unmatched ones need authoring."""
        return await _send("POST", f"/api/v1/compliance/packs/{pack_id}/auto-match")

    # ---- bid intelligence ------------------------------------------------
    @mcp.tool(annotations=WRITE)
    async def analyze_tender_for_clarifications(
        tender_title: str,
        source_text: str,
        clarification_deadline: str = "2026-12-01",
        notice_id: int | None = None,
        workspace_id: int = 1,
    ) -> dict[str, Any]:
        """Scan tender text for ambiguity (TBD, 'reasonable', 'etc.', unstated weightings) and
        draft prioritised clarification questions for the buyer."""
        return await _send(
            "POST",
            "/api/v1/clarifications/analyze-pack",
            {
                "workspace_id": workspace_id,
                "notice_id": notice_id,
                "tender_title": tender_title,
                "clarification_deadline": clarification_deadline,
                "source_text": source_text,
            },
        )

    @mcp.tool(annotations=WRITE)
    async def generate_buyer_intelligence_report(
        buyer_name: str, sector: str | None = None, workspace_id: int = 1
    ) -> dict[str, Any]:
        """Aggregate awarded notices for a buyer: contract values, repeat winners, win share."""
        return await _send(
            "POST",
            "/api/v1/intelligence/buyer-report",
            {"workspace_id": workspace_id, "buyer_name": buyer_name, "sector": sector},
        )

    @mcp.tool(annotations=WRITE)
    async def create_social_value_statement(
        bid_title: str,
        buyer_framework: Literal["UK_PPN_06_20", "EU_GPP", "Custom"] = "UK_PPN_06_20",
        themes: list[str] | None = None,
        net_zero_target_year: int = 2035,
        baseline_emissions_tco2e: float = 120.0,
        annual_reduction_pct: float = 8.0,
        real_living_wage_accredited: bool = True,
        supply_chain_commitments: str | None = None,
        workspace_id: int = 1,
    ) -> dict[str, Any]:
        """Generate a social value and sustainability statement with measurable KPIs."""
        body: dict[str, Any] = {
            "workspace_id": workspace_id,
            "bid_title": bid_title,
            "buyer_framework": buyer_framework,
            "net_zero_target_year": net_zero_target_year,
            "baseline_emissions_tco2e": baseline_emissions_tco2e,
            "annual_reduction_pct": annual_reduction_pct,
            "real_living_wage_accredited": real_living_wage_accredited,
        }
        if themes:
            body["themes"] = themes
        if supply_chain_commitments:
            body["supply_chain_commitments"] = supply_chain_commitments
        return await _send("POST", "/api/v1/social-value", body)

    # ---- review pipeline (read-only) ------------------------------------
    @mcp.tool(annotations=READ)
    async def list_quality_queue(workspace_id: int = 1) -> dict[str, Any]:
        """Show items awaiting or past human quality review, with status and score."""
        return {"items": await _get("/api/v1/quality-queue", workspace_id=workspace_id)}

    # ---- resources & prompts --------------------------------------------
    @mcp.resource("bidstudio://workspaces", mime_type="application/json")
    async def workspaces_resource() -> list[dict[str, Any]]:
        """All workspaces."""
        return await _get("/api/v1/workspaces")

    @mcp.prompt(title="Go / no-go on a tender")
    def go_no_go(notice_id: int) -> str:
        return (
            f"Assess whether we should bid on opportunity {notice_id}. Use search_opportunities "
            "(include_pack_text=true) to read it, analyze_tender_for_clarifications to find "
            "ambiguity, and generate_buyer_intelligence_report for the buyer. Finish with a "
            "go/no-go recommendation, the top 3 risks and the clarification questions to send."
        )

    @mcp.prompt(title="Draft a grant proposal")
    def draft_grant_proposal(notice_id: int, applicant_org: str) -> str:
        return (
            f"Draft a grant proposal for funding call {notice_id} on behalf of {applicant_org}. "
            "Call extract_grant_criteria, create_grant_proposal, then write each section against "
            "its criterion and weight, using search_answer_library for verified material. Save with "
            "update_grant_proposal_sections, then submit_grant_proposal_for_review."
        )

    return mcp


# --------------------------------------------------------------------------- HTTP mount


class BearerKeyMiddleware:
    """ASGI middleware guarding the /mcp endpoint with a shared API key (if configured)."""

    def __init__(self, app: Any, api_key: str, path_prefix: str = "/mcp") -> None:
        self.app = app
        self.api_key = api_key
        self.path_prefix = path_prefix

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.path_prefix) and self.api_key:
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            supplied = headers.get("x-api-key") or headers.get("authorization", "").removeprefix(
                "Bearer "
            )
            if not hmac.compare_digest(supplied.encode(), self.api_key.encode()):
                body = b'{"error":"unauthorized","detail":"Missing or invalid API key"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b'Bearer realm="bid-studio-mcp"'),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


class McpGateway:
    """Routes ``/mcp`` to the MCP app and everything else to the wrapped FastAPI app."""

    def __init__(self, app: Any, mcp_app: Any) -> None:
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and (scope["path"] == "/mcp" or scope["path"].startswith("/mcp/")):
            await self.mcp_app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def build_http_app(mcp: MCPServer) -> Any:
    """Stateless streamable-HTTP ASGI app serving MCP at ``/mcp`` (serverless friendly)."""
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        # Auth is the API key; hosts vary (Vercel previews, custom domains).
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


def main() -> None:
    """Entry point: ``bid-studio-mcp`` (stdio) or ``bid-studio-mcp --http``."""
    import sys

    server = build_server()
    if "--http" in sys.argv:
        server.run("streamable-http")
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
