"""meta.ads.* tools — Marketing-API read + management surface.

Tools registered:
- meta.ads.list_campaigns       — READ. No confirm gate.
- meta.ads.insights             — READ. No confirm gate.
- meta.ads.create_campaign      — WRITE. confirm-gated + audit.
- meta.ads.create_ad_set        — WRITE. confirm-gated + audit.
- meta.ads.create_ad_creative   — WRITE. confirm-gated + audit.
- meta.ads.create_ad            — WRITE. confirm-gated + audit.
- meta.ads.update_campaign_status — WRITE. confirm-gated + audit.
- meta.ads.update_ad_set_budget — WRITE. confirm-gated + audit.

Thin wrappers over `noctusai_lib.integrations.meta` (write/ads surface
shipped by META-WRITE-LIB + META-ADS-MGMT). NO connector logic — the
Graph POST, spec shaping and the App-Review honesty-gate all live in the
seed adapter. Deferred-config: no `META_SYSTEM_USER_TOKEN` ⇒
`FakeMetaAdapter` (writes simulated, recorded — the "scope-approved"
path) so the server boots and tests are deterministic; a real token ⇒
`MetaOAuthAdapter`, and a scope-absent write raises
`MetaGraphError(requires_app_review=True)` — surfaced verbatim, NEVER a
faked success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.meta import MetaGraphError, get_meta_adapter
from noctusai_lib.integrations.meta.types import (
    AdCreativeSpec,
    AdSetSpec,
    AdSpec,
    CampaignSpec,
)

from ..settings import get_settings
from ..types import (
    AdCampaignOut,
    AdCreativeOut,
    AdInsightsInput,
    AdInsightsOut,
    AdInsightsOutput,
    AdOut,
    AdSetOut,
    CreateAdCreativeInput,
    CreateAdCreativeOutput,
    CreateAdInput,
    CreateAdOutput,
    CreateAdSetInput,
    CreateAdSetOutput,
    CreateCampaignInput,
    CreateCampaignOutput,
    ListCampaignsInput,
    ListCampaignsOutput,
    UpdateAdSetBudgetInput,
    UpdateAdSetBudgetOutput,
    UpdateCampaignStatusInput,
    UpdateCampaignStatusOutput,
)

logger = logging.getLogger(__name__)
_audit = logging.getLogger("meta.audit")


def _adapter():
    s = get_settings()
    return get_meta_adapter(
        system_user_token=s.meta_system_user_token, graph_version=None
    )


def _meta_error(e: MetaGraphError) -> dict:
    """Typed-error envelope + Meta's branchable signals. `requires_app_review`
    is the honesty-gate flag: scope-absent on the real path → True, never a
    faked success."""
    env = typed_error(e)
    env["http_status"] = getattr(e, "http_status", None)
    env["is_auth_error"] = getattr(e, "is_auth_error", False)
    env["is_rate_limited"] = getattr(e, "is_rate_limited", False)
    env["requires_app_review"] = getattr(e, "requires_app_review", False)
    return env


def _campaign_out(c) -> AdCampaignOut:
    return AdCampaignOut(
        id=c.id,
        name=c.name,
        objective=c.objective,
        status=c.status,
        effective_status=c.effective_status,
    )


def _ad_set_out(s) -> AdSetOut:
    return AdSetOut(
        id=s.id,
        name=s.name,
        status=s.status,
        effective_status=s.effective_status,
        campaign_id=s.campaign_id,
        daily_budget=s.daily_budget,
        billing_event=s.billing_event,
        optimization_goal=s.optimization_goal,
    )


def _unconfirmed(output_cls, tool: str):
    return output_cls(
        error=typed_error(
            PermissionError(
                f"{tool} is a WRITE — re-call with confirm=true to perform it."
            )
        )
    ).model_dump()


# ─── Handlers ────────────────────────────────────────────────────────────


async def list_campaigns(args: dict) -> dict:
    inp = ListCampaignsInput(**args)
    adapter = _adapter()
    try:
        rows = adapter.list_ad_campaigns(inp.ad_account_id)
    except MetaGraphError as e:
        return ListCampaignsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return ListCampaignsOutput(
        campaigns=[_campaign_out(c) for c in rows], auth_mode=adapter.auth_mode
    ).model_dump()


async def ad_insights(args: dict) -> dict:
    inp = AdInsightsInput(**args)
    adapter = _adapter()
    try:
        ins = adapter.ad_insights(
            inp.object_id, inp.level, date_preset=inp.date_preset
        )
    except MetaGraphError as e:
        return AdInsightsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return AdInsightsOutput(
        insights=AdInsightsOut(
            object_id=ins.object_id, level=ins.level, metrics=dict(ins.metrics)
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def create_campaign(args: dict) -> dict:
    inp = CreateCampaignInput(**args)
    if not inp.confirm:
        return _unconfirmed(CreateCampaignOutput, "meta.ads.create_campaign")
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.create_campaign acct=%s name=%r objective=%s confirm=true",
        inp.ad_account_id,
        inp.name,
        inp.objective,
    )
    try:
        c = adapter.create_ad_campaign(
            inp.ad_account_id,
            CampaignSpec(
                name=inp.name,
                objective=inp.objective,
                special_ad_categories=list(inp.special_ad_categories),
            ),
        )
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.create_campaign FAILED err=%s", e)
        return CreateCampaignOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return CreateCampaignOutput(
        campaign=_campaign_out(c), auth_mode=adapter.auth_mode
    ).model_dump()


async def create_ad_set(args: dict) -> dict:
    inp = CreateAdSetInput(**args)
    if not inp.confirm:
        return _unconfirmed(CreateAdSetOutput, "meta.ads.create_ad_set")
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.create_ad_set acct=%s campaign=%s budget=%s confirm=true",
        inp.ad_account_id,
        inp.campaign_id,
        inp.daily_budget,
    )
    try:
        s = adapter.create_ad_set(
            inp.ad_account_id,
            AdSetSpec(
                name=inp.name,
                campaign_id=inp.campaign_id,
                daily_budget=inp.daily_budget,
                billing_event=inp.billing_event,
                optimization_goal=inp.optimization_goal,
            ),
        )
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.create_ad_set FAILED err=%s", e)
        return CreateAdSetOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return CreateAdSetOutput(
        ad_set=_ad_set_out(s), auth_mode=adapter.auth_mode
    ).model_dump()


async def create_ad_creative(args: dict) -> dict:
    inp = CreateAdCreativeInput(**args)
    if not inp.confirm:
        return _unconfirmed(CreateAdCreativeOutput, "meta.ads.create_ad_creative")
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.create_ad_creative acct=%s name=%r confirm=true",
        inp.ad_account_id,
        inp.name,
    )
    try:
        cr = adapter.create_ad_creative(
            inp.ad_account_id, AdCreativeSpec(name=inp.name)
        )
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.create_ad_creative FAILED err=%s", e)
        return CreateAdCreativeOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return CreateAdCreativeOutput(
        creative=AdCreativeOut(id=cr.id, name=cr.name),
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def create_ad(args: dict) -> dict:
    inp = CreateAdInput(**args)
    if not inp.confirm:
        return _unconfirmed(CreateAdOutput, "meta.ads.create_ad")
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.create_ad acct=%s adset=%s creative=%s confirm=true",
        inp.ad_account_id,
        inp.adset_id,
        inp.creative_id,
    )
    try:
        ad = adapter.create_ad(
            inp.ad_account_id,
            AdSpec(
                name=inp.name, adset_id=inp.adset_id, creative_id=inp.creative_id
            ),
        )
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.create_ad FAILED err=%s", e)
        return CreateAdOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return CreateAdOutput(
        ad=AdOut(
            id=ad.id,
            name=ad.name,
            status=ad.status,
            effective_status=ad.effective_status,
            adset_id=ad.adset_id,
            creative_id=ad.creative_id,
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def update_campaign_status(args: dict) -> dict:
    inp = UpdateCampaignStatusInput(**args)
    if not inp.confirm:
        return _unconfirmed(
            UpdateCampaignStatusOutput, "meta.ads.update_campaign_status"
        )
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.update_campaign_status campaign=%s status=%s confirm=true",
        inp.campaign_id,
        inp.status,
    )
    try:
        c = adapter.update_campaign_status(inp.campaign_id, inp.status)
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.update_campaign_status FAILED err=%s", e)
        return UpdateCampaignStatusOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return UpdateCampaignStatusOutput(
        campaign=_campaign_out(c), auth_mode=adapter.auth_mode
    ).model_dump()


async def update_ad_set_budget(args: dict) -> dict:
    inp = UpdateAdSetBudgetInput(**args)
    if not inp.confirm:
        return _unconfirmed(
            UpdateAdSetBudgetOutput, "meta.ads.update_ad_set_budget"
        )
    adapter = _adapter()
    _audit.info(
        "AUDIT meta.ads.update_ad_set_budget ad_set=%s budget=%s confirm=true",
        inp.ad_set_id,
        inp.daily_budget,
    )
    try:
        s = adapter.update_ad_set_budget(inp.ad_set_id, inp.daily_budget)
    except MetaGraphError as e:
        _audit.warning("AUDIT meta.ads.update_ad_set_budget FAILED err=%s", e)
        return UpdateAdSetBudgetOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return UpdateAdSetBudgetOutput(
        ad_set=_ad_set_out(s), auth_mode=adapter.auth_mode
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "meta.ads.list_campaigns": list_campaigns,
    "meta.ads.insights": ad_insights,
    "meta.ads.create_campaign": create_campaign,
    "meta.ads.create_ad_set": create_ad_set,
    "meta.ads.create_ad_creative": create_ad_creative,
    "meta.ads.create_ad": create_ad,
    "meta.ads.update_campaign_status": update_campaign_status,
    "meta.ads.update_ad_set_budget": update_ad_set_budget,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    _READ = "READ-ONLY — no confirm gate. Fake adapter when unconfigured."
    _WRITE = (
        "WRITE — you MUST pass confirm=true or the call is refused with a "
        "typed error and nothing is mutated. Real path needs the "
        "App-Review-approved ads_management scope; absent → typed error "
        "with requires_app_review=true (never a faked success)."
    )
    return [
        Tool(
            name="meta.ads.list_campaigns",
            description=f"List ad campaigns under an ad account. {_READ}",
            inputSchema=ListCampaignsInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.insights",
            description=(
                f"Insight metrics for a campaign/ad-set/ad. {_READ}"
            ),
            inputSchema=AdInsightsInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.create_campaign",
            description=f"Create an ad campaign (defaults to PAUSED). {_WRITE}",
            inputSchema=CreateCampaignInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.create_ad_set",
            description=f"Create an ad set under a campaign. {_WRITE}",
            inputSchema=CreateAdSetInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.create_ad_creative",
            description=f"Create an ad creative. {_WRITE}",
            inputSchema=CreateAdCreativeInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.create_ad",
            description=f"Create an ad (adset+creative). {_WRITE}",
            inputSchema=CreateAdInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.update_campaign_status",
            description=f"Update a campaign's status. {_WRITE}",
            inputSchema=UpdateCampaignStatusInput.model_json_schema(),
        ),
        Tool(
            name="meta.ads.update_ad_set_budget",
            description=f"Update an ad set's daily budget. {_WRITE}",
            inputSchema=UpdateAdSetBudgetInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
