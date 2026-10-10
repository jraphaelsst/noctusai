"""meta.leadgen.* — rehearse a Meta Lead-Ads lead end to end.

Tools registered:
- meta.leadgen.simulate — WRITE. confirm-gated.

Mirrors `imovelweb.webhook.simulate`: instead of waiting for a real ad click it
POSTs a synthetic lead at the social-wiring product's
`POST /api/meta/leadgen/simular` (CONTRACT sw-lead-to-contract §1.4), which runs
the SAME `upsert_lead` → `ingest_meta_lead` path as the real webhook — minus the
Graph fetch — so campaign resolution (ad → adset → campaign → form → REF), the
cliente attach and the imóvel links are exercised for real. The stored row is
marked `simulado=true` and the card's timeline reads "Lead simulado".

Platform staff only (the endpoint 403s `not_platform_staff` otherwise), so the
credential is a staff operator bearer token in `SOCIAL_WIRING_OPERATOR_TOKEN`,
read from this connector's own `.env` like every other secret.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool
from pydantic import BaseModel, ConfigDict, Field

from _kit.errors import confirmation_required_message, typed_error

from ..settings import get_settings

logger = logging.getLogger(__name__)

SIMULATE_PATH = "/api/meta/leadgen/simular"
TIMEOUT_SECONDS = 30.0


class LeadgenApiError(Exception):
    """Connector-side error carrying an HTTP-ish `status`
    (424 = not configured · 412 = confirmation required · else the product's)."""

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(LeadgenApiError):
    def __init__(self, action: str, effect: str = "") -> None:
        super().__init__(
            confirmation_required_message(action, effect, noun="write action"),
            status=412,
        )


class SimulateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ad_id: Optional[str] = Field(default=None, description="Meta ad id (most specific campanha match).")
    adset_id: Optional[str] = Field(default=None, description="Meta ad-set id.")
    campaign_id: Optional[str] = Field(default=None, description="Meta campaign id.")
    form_id: Optional[str] = Field(default=None, description="Meta lead-form id.")
    nome: str = Field(..., min_length=1, description="The lead's name.")
    telefone: Optional[str] = Field(default=None, description="Phone, E.164 preferred.")
    email: Optional[str] = None
    respostas: Optional[dict[str, str]] = Field(
        default=None,
        description="Extra form answers. `REF` is the fallback imóvel código "
        "when no campanha matches the ids above.",
    )
    confirm: bool = Field(default=False, description="Must be true — this creates a lead + card.")


class SimulateOutput(BaseModel):
    simulated: bool
    http_status: Optional[int] = None
    meta_lead_id: Optional[str] = None
    lead_id: Optional[str] = None
    atendimento_id: Optional[str] = None
    cliente_id: Optional[str] = None
    imoveis: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


def _post(url: str, token: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 — operator-configured product URL
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "noctusai-meta-leadgen-simulator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return int(response.status), json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return int(exc.code), json.loads(raw)
        except ValueError:
            return int(exc.code), {"detail": raw.decode("utf-8", "replace")[:500]}


async def simulate(args: dict) -> dict:
    inp = SimulateInput(**args)
    # The gate is evaluated FIRST — before reading settings, before any I/O.
    if inp.confirm is not True:
        err = ConfirmationRequiredError(
            "meta.leadgen.simulate",
            "creates a simulated Meta lead, its cliente and card in the target org",
        )
        logger.info("meta.leadgen.simulate BLOCKED (unconfirmed)")
        return SimulateOutput(simulated=False, error=typed_error(err)).model_dump()

    settings = get_settings()
    if not settings.leadgen_simulate_configured:
        err = LeadgenApiError(
            "meta.leadgen.simulate is not configured — set SOCIAL_WIRING_URL and "
            "SOCIAL_WIRING_OPERATOR_TOKEN (a platform-staff bearer token) in "
            "mcp/meta/.env.",
            status=424,
        )
        return SimulateOutput(simulated=False, error=typed_error(err)).model_dump()

    body = {k: v for k, v in inp.model_dump(exclude={"confirm"}).items() if v not in (None, {})}
    url = settings.social_wiring_url.rstrip("/") + SIMULATE_PATH
    logger.info("meta.leadgen.simulate AUDIT confirmed=true url=%s", url)
    try:
        status, payload = await asyncio.to_thread(
            _post, url, settings.social_wiring_operator_token, body
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        err = LeadgenApiError(f"social-wiring unreachable: {exc}", status=502)
        return SimulateOutput(simulated=False, error=typed_error(err)).model_dump()

    if status != 200:
        # A refusal is a RESULT (403 not_platform_staff is the interesting one):
        # surface the product's own code verbatim.
        detail = payload.get("detail") or (payload.get("error") or {}).get("message") or payload
        err = LeadgenApiError(
            f"{payload.get('code') or 'http_error'}: {detail}", status=status
        )
        return SimulateOutput(
            simulated=False, http_status=status, error=typed_error(err)
        ).model_dump()

    data = payload.get("data") or {}
    return SimulateOutput(
        simulated=True,
        http_status=status,
        meta_lead_id=data.get("meta_lead_id"),
        lead_id=data.get("lead_id"),
        atendimento_id=data.get("atendimento_id"),
        cliente_id=data.get("cliente_id"),
        imoveis=data.get("imoveis") or [],
    ).model_dump()


HANDLERS = {"meta.leadgen.simulate": simulate}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="meta.leadgen.simulate",
            description=(
                "Rehearse a Meta Lead-Ads lead: POSTs a synthetic lead at the "
                "social-wiring product, which runs the real webhook ingest path "
                "(minus the Graph fetch) — campanha resolution by ad/adset/"
                "campaign/form id, REF fallback, cliente attach, imóvel links. "
                "The stored row is marked simulado and the timeline shows "
                "'Lead simulado'. Platform staff token required. WRITE — "
                "requires confirm=true."
            ),
            inputSchema=SimulateInput.model_json_schema(),
        )
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
