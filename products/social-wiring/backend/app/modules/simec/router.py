"""SIMEC HTTP surface. Contract:
``products/social-wiring/projects/marketing-intelligence/specs/simec-api-contract.md``.

    GET  /api/simec/accounts
    GET  /api/simec/config/defaults?platform=instagram
    GET  /api/simec/config?platform=instagram[&account_id=]
    PUT  /api/simec/config/org                         (owner/admin)
    PUT  /api/simec/accounts/{account_id}/config       (owner/admin)
    POST /api/simec/accounts/{account_id}/readouts
    GET  /api/simec/accounts/{account_id}/readouts?limit=20
    GET  /api/simec/accounts/{account_id}/readouts/latest
    GET  /api/simec/readouts/{readout_id}

Every route: authenticated (``get_current_user_org`` → strict 401); org from
the SESSION, never a parameter; an account is resolved org-scoped and must be
a ``provider="instagram"`` connection (else 404 — also the cross-tenant
answer). Config writes are owner/admin (trusted ``noctus_users`` row, 403
otherwise). Invalid overrides / periods → 422 with the validator's message.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.domain.content_performance import default_config_dict, load_default_config

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_current_user_org
from app.modules.instagram.repository import INSTAGRAM_PROVIDER, IgInsightsRepository
from app.modules.instagram.sync_service import TZ_BR, missing_insights_scope
from app.modules.simec.repository import SimecRepository
from app.modules.simec.service import SimecConfigInvalid, SimecPeriodInvalid, SimecService
from app.modules.simec.sources import make_metrics_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simec", tags=["simec"])

Platform = Literal["instagram"]


# ─── DI seams (tests override via app.dependency_overrides) ──────────────
def get_simec_repository() -> SimecRepository:
    return SimecRepository(get_admin_client())


def get_ig_repository_for_simec() -> IgInsightsRepository:
    return IgInsightsRepository(get_admin_client())


def _today_br() -> date:
    return datetime.now(timezone.utc).astimezone(TZ_BR).date()


def get_simec_source_kind() -> str:
    """Which metrics source serves readings (``settings.simec_metrics_source``)."""
    return settings.simec_metrics_source


def get_simec_service(
    repo: SimecRepository = Depends(get_simec_repository),
    ig_repo: IgInsightsRepository = Depends(get_ig_repository_for_simec),
    source_kind: str = Depends(get_simec_source_kind),
) -> SimecService:
    try:
        source = make_metrics_source("instagram", source_kind, ig_repo=ig_repo)
    except ValueError as exc:
        logger.error("SIMEC metrics source misconfigured: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return SimecService(repo, source, today=_today_br)


def get_admin_gate() -> Callable[[Any, Optional[Request], str], None]:
    """``(auth, request, context) -> None``; raises 403 unless owner/admin in
    the request's selected org (trusted ``noctus_users`` row)."""
    return lambda auth, request, context: require_org_admin_for(get_core_client(), auth, request, context)


# ─── models ──────────────────────────────────────────────────────────────
class ConfigWriteIn(StrictHttpModel):
    platform: Platform = "instagram"
    overrides: dict[str, Any] = Field(default_factory=dict)


class ReadoutRequestIn(StrictHttpModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    cadence: str = "mensal"


class LatestReadoutRef(BaseModel):
    id: UUID
    computed_at: datetime
    period_start: date
    period_end: date
    source: str


class SimecAccountOut(BaseModel):
    account_id: UUID
    label: Optional[str] = None
    username: Optional[str] = None
    marca_id: Optional[UUID] = None
    status: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    insights_scope_granted: bool
    latest_readout: Optional[LatestReadoutRef] = None


class SimecAccountsOut(BaseModel):
    metrics_source: str
    accounts: list[SimecAccountOut]


class ConfigOut(BaseModel):
    platform: str
    version: str
    fingerprint: str
    config: dict[str, Any]
    layers: dict[str, Any]


class ReadoutSummaryOut(BaseModel):
    id: UUID
    account_id: UUID
    platform: str
    source: str
    period_start: date
    period_end: date
    history_start: date
    config_version: str
    config_fingerprint: str
    status_counts: dict[str, int]
    computed_by: Optional[str] = None
    computed_at: datetime


class ReadingOut(BaseModel):
    content_id: Optional[str] = None
    window: Optional[str] = None
    published_on: Optional[date] = None
    collected_on: Optional[date] = None
    format: Optional[str] = None
    topic: Optional[str] = None
    status: str
    age_days: Optional[float] = None
    metrics: dict[str, Any]
    indicators: dict[str, Any]
    source_ref: Optional[dict[str, Any]] = None


class ReadoutOut(ReadoutSummaryOut):
    config: dict[str, Any]
    panel: dict[str, Any]
    baselines: list[dict[str, Any]]
    alerts: dict[str, Any]
    readings: list[ReadingOut]


class ReadoutListOut(BaseModel):
    items: list[ReadoutSummaryOut]


class LatestReadoutOut(BaseModel):
    readout: Optional[ReadoutOut] = None


# ─── helpers ─────────────────────────────────────────────────────────────
def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _user_id(auth: tuple) -> Optional[str]:
    return str(getattr(auth[0], "id", "") or "") or None


def resolve_simec_account(
    account_id: str,
    auth: tuple = Depends(get_current_user_org),
    ig_repo: IgInsightsRepository = Depends(get_ig_repository_for_simec),
) -> dict[str, Any]:
    org_id = _org(auth)
    try:
        account_uuid = UUID(account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid account_id") from exc
    account = ig_repo.get_account(account_uuid, org_id)
    if account is None or account.get("provider") != INSTAGRAM_PROVIDER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"instagram account {account_uuid} not found for this org")
    return {**account, "_org_uuid": org_id, "_account_uuid": account_uuid}


def _readout_out(payload: dict[str, Any]) -> ReadoutOut:
    readings = [
        ReadingOut(
            content_id=r.get("content_id"), window=r.get("janela"),
            published_on=r.get("published_on"), collected_on=r.get("collected_on"),
            format=r.get("formato"), topic=r.get("tema"), status=r["status"],
            age_days=r.get("age_days"), metrics=r.get("metrics") or {},
            indicators=r.get("indicators") or {}, source_ref=r.get("source_ref"),
        )
        for r in payload.get("readings", [])
    ]
    return ReadoutOut(**{k: v for k, v in payload.items() if k != "readings"}, readings=readings)


# ─── routes ──────────────────────────────────────────────────────────────
@router.get("/accounts", response_model=SimecAccountsOut)
def list_accounts(
    auth: tuple = Depends(get_current_user_org),
    ig_repo: IgInsightsRepository = Depends(get_ig_repository_for_simec),
    svc: SimecService = Depends(get_simec_service),
    repo: SimecRepository = Depends(get_simec_repository),
) -> SimecAccountsOut:
    """The org's Instagram connections (any status) + each one's latest
    readout. An org with no connection gets ``accounts: []`` — the FE's
    "conecte o Instagram" empty state."""
    org_id = _org(auth)
    out = []
    for a in ig_repo.list_org_accounts(org_id):
        aid = UUID(str(a["id"]))
        latest = repo.list_readouts(org_id, aid, limit=1)
        info = a.get("channel_info") or {}
        meta = a.get("metadata") or {}
        out.append(SimecAccountOut(
            account_id=aid, label=a.get("account_label"),
            username=info.get("username") or meta.get("channel_title"),
            marca_id=a.get("marca_id"), status=a.get("status"),
            last_synced_at=a.get("last_synced_at"),
            insights_scope_granted=not missing_insights_scope(a),
            latest_readout=LatestReadoutRef(**{k: latest[0][k] for k in
                                               ("id", "computed_at", "period_start", "period_end", "source")})
            if latest else None,
        ))
    return SimecAccountsOut(metrics_source=svc.source_name, accounts=out)


@router.get("/config/defaults", response_model=ConfigOut)
def get_default_config(
    platform: Platform = Query(default="instagram"),
    auth: tuple = Depends(get_current_user_org),
) -> ConfigOut:
    """The seed's recommended defaults (no org layer applied)."""
    cfg = load_default_config(platform)
    return ConfigOut(platform=platform, version=cfg.version, fingerprint=cfg.fingerprint,
                     config=default_config_dict(platform),
                     layers={"defaults": {"version": cfg.version}, "org": None, "account": None})


@router.get("/config", response_model=ConfigOut)
def get_config(
    platform: Platform = Query(default="instagram"),
    account_id: Optional[str] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    ig_repo: IgInsightsRepository = Depends(get_ig_repository_for_simec),
    svc: SimecService = Depends(get_simec_service),
) -> ConfigOut:
    """The EFFECTIVE config (defaults ⊕ org ⊕ profile) + each layer."""
    org_id = _org(auth)
    acc_uuid = None
    if account_id is not None:
        acc_uuid = resolve_simec_account(account_id, auth, ig_repo)["_account_uuid"]
    try:
        return ConfigOut(**svc.resolve_config(org_id, platform, acc_uuid).to_dict())
    except SimecConfigInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/config/org", response_model=ConfigOut)
def put_org_config(
    body: ConfigWriteIn,
    auth: tuple = Depends(get_current_user_org),
    svc: SimecService = Depends(get_simec_service),
    admin_gate=Depends(get_admin_gate),
    request: Request = None,
) -> ConfigOut:
    """Replace the org layer (partial overrides). ``{}`` resets to defaults."""
    admin_gate(auth, request, "A configuração do SIMEC")
    try:
        resolved = svc.save_config(_org(auth), body.platform, None, body.overrides, user_id=_user_id(auth))
    except SimecConfigInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    return ConfigOut(**resolved.to_dict())


@router.put("/accounts/{account_id}/config", response_model=ConfigOut)
def put_account_config(
    body: ConfigWriteIn,
    account: dict = Depends(resolve_simec_account),
    auth: tuple = Depends(get_current_user_org),
    svc: SimecService = Depends(get_simec_service),
    admin_gate=Depends(get_admin_gate),
    request: Request = None,
) -> ConfigOut:
    """Replace this profile's layer (partial overrides on top of the org's)."""
    admin_gate(auth, request, "A configuração do SIMEC")
    try:
        resolved = svc.save_config(account["_org_uuid"], body.platform, account["_account_uuid"],
                                   body.overrides, user_id=_user_id(auth))
    except SimecConfigInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    return ConfigOut(**resolved.to_dict())


@router.post("/accounts/{account_id}/readouts", response_model=ReadoutOut,
             status_code=status.HTTP_201_CREATED)
def create_readout(
    body: ReadoutRequestIn,
    account: dict = Depends(resolve_simec_account),
    auth: tuple = Depends(get_current_user_org),
    svc: SimecService = Depends(get_simec_service),
) -> ReadoutOut:
    """Compute + store a readout now. Period defaults to the ``cadence``
    review period ending today (BRT)."""
    try:
        payload = svc.compute(
            account["_org_uuid"], account["_account_uuid"], "instagram",
            period_start=body.period_start, period_end=body.period_end,
            cadence=body.cadence, user_id=_user_id(auth),
        )
    except (SimecConfigInvalid, SimecPeriodInvalid) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _readout_out(payload)


@router.get("/accounts/{account_id}/readouts", response_model=ReadoutListOut)
def list_readouts(
    limit: int = Query(default=20, ge=1, le=100),
    account: dict = Depends(resolve_simec_account),
    repo: SimecRepository = Depends(get_simec_repository),
) -> ReadoutListOut:
    rows = repo.list_readouts(account["_org_uuid"], account["_account_uuid"], limit=limit)
    return ReadoutListOut(items=[ReadoutSummaryOut(**r) for r in rows])


@router.get("/accounts/{account_id}/readouts/latest", response_model=LatestReadoutOut)
def latest_readout(
    account: dict = Depends(resolve_simec_account),
    svc: SimecService = Depends(get_simec_service),
) -> LatestReadoutOut:
    """``{"readout": null}`` when none was computed yet (not a 404)."""
    rid = svc.latest_readout_id(account["_org_uuid"], account["_account_uuid"])
    if rid is None:
        return LatestReadoutOut(readout=None)
    payload = svc.readout_payload(account["_org_uuid"], rid)
    return LatestReadoutOut(readout=_readout_out(payload) if payload else None)


@router.get("/readouts/{readout_id}", response_model=ReadoutOut)
def get_readout(
    readout_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: SimecService = Depends(get_simec_service),
) -> ReadoutOut:
    payload = svc.readout_payload(_org(auth), readout_id)
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"readout {readout_id} not found")
    return _readout_out(payload)


__all__ = [
    "router",
    "get_admin_gate",
    "get_ig_repository_for_simec",
    "get_simec_repository",
    "get_simec_service",
    "get_simec_source_kind",
]
