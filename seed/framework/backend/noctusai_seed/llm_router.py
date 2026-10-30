"""
Shared LLM router — `/api/llm/*` endpoints every product inherits.

Endpoints:
  GET  /api/llm/providers               → [{ provider, configured, stub }]
  GET  /api/llm/models?provider=openai  → [{ id, label, kind, stub }]
  GET  /api/llm/preferences             → { provider, chat_model, embedding_model }
  PUT  /api/llm/preferences             → same
  GET  /api/llm/usage                   → { events, aggregate } — RLS-scoped

Per the seed-injector pattern: no product writes this code. `create_product_app()`
auto-includes this router whenever an `LLMConfig` is active (always, given
Phase 3's default).

Storage:
- `<schema>.llm_preferences(org_id, provider, chat_model, embedding_model, updated_at)`
- usage: the central ledger `public.ai_usage` (core migration 091, D25) —
  every product's calls, attributed + priced at write time; this router reads
  the caller's org rows for THIS product only.

`llm_preferences` lives in each product's schema — RLS-scoped per-org
(products/*/backend/migrations/NNN_llm_preferences.sql).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from noctusai_lib.api.auth._blocking import run_blocking

from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import all_providers, models_for
from noctusai_lib.integrations.llm.attribution import get_default_product
from noctusai_lib.integrations.llm.ledger_read import (
    AiUsageWindowTooLarge,
    aggregate_ai_usage,
    read_ai_usage_rows,
)
from noctusai_lib.primitives.parsing import parse_iso_or_400 as _parse_iso

logger = logging.getLogger(__name__)


class ProviderInfo(BaseModel):
    provider: str
    configured: bool
    stub: bool


class ModelInfo(BaseModel):
    id: str
    label: str
    kind: str
    stub: bool
    description: str = ""


class PreferencesBody(BaseModel):
    provider: str = Field(..., min_length=1)
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None


def _has_any_stub_model(provider: str) -> bool:
    return any(m.stub for m in models_for(provider))


def create_llm_router(deps) -> APIRouter:
    """Build the `/api/llm/*` router for a product.

    `deps` is the product's `ProductDependencies` instance; we use it to
    resolve the caller's org_id (required for per-org credential checks and
    preference storage).
    """
    router = APIRouter(prefix="/api/llm", tags=["LLM"])

    # Trusted org (SEC-1, 2026-09-28): `public.noctus_users` first — NOT the
    # user-writable `user_metadata.org_id` `deps.get_org_id` reads. The org
    # scopes `resolve_credential` (a service-side lookup), so a spoofed org
    # would report another tenant's provider configuration. NO metadata
    # fallback: a caller without a `noctus_users` row has no org here (403).
    _get_current_user_org = make_get_current_user_org(
        # Late-bound: resolve `deps.get_current_user` per request, exactly as
        # the pre-SEC-1 imperative calls did (a product/test rebinding it after
        # mount must still take effect).
        lambda authorization: deps.get_current_user(authorization),
        lambda _user: None,
        get_admin_client_fn=lambda: deps.get_core_client(),
    )

    async def _require_org(authorization):
        user, token, org_id = await _get_current_user_org(authorization)
        return user, org_id, token

    @router.get("/providers", response_model=list[ProviderInfo])
    async def listar_providers(authorization: Optional[str] = Header(None)):
        """List every registered LLM provider with its configured/stub status
        for the caller's org. A provider is `configured=true` when
        `resolve_credential("<provider>_api_key", org_id)` returns non-empty
        (any tier: org / platform / env)."""
        user, org_id, _token = await _require_org(authorization)

        result: list[ProviderInfo] = []
        for provider in all_providers():
            key = resolve_credential(f"{provider}_api_key", org_id)
            result.append(ProviderInfo(
                provider=provider,
                configured=bool(key),
                stub=_has_any_stub_model(provider),
            ))
        return result

    @router.get("/models", response_model=list[ModelInfo])
    async def listar_models(
        provider: str = Query(..., min_length=1),
        kind: Optional[str] = Query(None, description="Filter by kind: chat/embedding/audio/vision"),
        authorization: Optional[str] = Header(None),
    ):
        """Return every model in the catalog for the given provider,
        optionally filtered by kind. Available whether the provider is
        configured or not — UI uses this to render disabled options."""
        await _require_org(authorization)
        entries = models_for(provider, kind)  # type: ignore[arg-type]
        return [
            ModelInfo(
                id=m.id,
                label=m.label,
                kind=m.kind,
                stub=m.stub,
                description=m.description,
            )
            for m in entries
        ]

    @router.get("/preferences")
    async def obter_preferences(authorization: Optional[str] = Header(None)):
        """Return the caller's org's LLM preferences, or null values if
        not set (implying the product's defaults apply)."""
        user, org_id, token = await _require_org(authorization)
        db = deps.get_user_client(token)
        result = await run_blocking(
            lambda: db.table("llm_preferences")
            .select("provider, chat_model, embedding_model")
            .eq("org_id", org_id)
            .maybe_single()
            .execute()
        )
        return result.data or {"provider": None, "chat_model": None, "embedding_model": None}

    @router.put("/preferences")
    async def salvar_preferences(
        body: PreferencesBody,
        authorization: Optional[str] = Header(None),
    ):
        """Upsert the caller's org's LLM preferences. Only owners/admins/managers
        may change them (anyone-can-set would let any team member redirect
        the org's LLM spend)."""
        user, org_id, token = await _require_org(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin", "manager"):
            raise HTTPException(status_code=403, detail="Permissão insuficiente")

        # Validate provider exists
        if body.provider not in all_providers():
            raise HTTPException(
                status_code=400,
                detail=f"Provider desconhecido: {body.provider}",
            )
        db = deps.get_user_client(token)
        await run_blocking(
            lambda: db.table("llm_preferences").upsert(
                {
                    "org_id": org_id,
                    "provider": body.provider,
                    "chat_model": body.chat_model,
                    "embedding_model": body.embedding_model,
                },
                on_conflict="org_id",
            ).execute()
        )
        return {"ok": True}

    @router.get("/usage")
    async def obter_usage(
        authorization: Optional[str] = Header(None),
        from_: Optional[str] = Query(None, alias="from", description="ISO-8601 start (default now-30d)"),
        to: Optional[str] = Query(None, description="ISO-8601 end (default now)"),
        group_by: str = Query(
            "provider_model",
            description="provider_model | provider | model | operation | feature",
        ),
        limit: int = Query(500, ge=1, le=5000, description="Max raw events returned"),
    ):
        """LLM usage + cost of the caller's org IN THIS PRODUCT, read from the
        central ledger ``public.ai_usage`` (D25).

        Org = the trusted ``noctus_users`` resolution (never metadata); the
        read runs on the service-role core client filtered by that org and by
        this process's product slug, so a caller only ever sees its own org.

        Returns ``{events, aggregate, ledger, window}`` — ``events`` the newest
        ``limit`` rows, ``aggregate`` grouped by ``group_by``, ``ledger`` the
        per product → per feature roll-up (`aggregate_ai_usage`).
        """
        _user, org_id, _token = await _require_org(authorization)
        if not org_id:
            raise HTTPException(status_code=403, detail="Usuário sem organização")

        now = datetime.now(tz=timezone.utc)
        start = _parse_iso(from_) or (now - timedelta(days=30))
        end = _parse_iso(to) or now
        product = get_default_product()
        db = deps.get_core_client()
        try:
            rows = await run_blocking(
                lambda: read_ai_usage_rows(
                    db, start=start, end=end, org_id=str(org_id), product=product,
                )
            )
        except AiUsageWindowTooLarge:
            raise HTTPException(status_code=400, detail="Janela grande demais; reduza o período")

        newest = sorted(rows, key=lambda r: str(r.get("created_at") or ""), reverse=True)[:limit]
        return {
            "events": newest,
            "aggregate": _aggregate_rows(rows, group_by),
            "ledger": aggregate_ai_usage(rows),
            "window": {"from": start.isoformat(), "to": end.isoformat()},
        }

    return router


def _aggregate_rows(rows: list[dict], group_by: str) -> list[dict]:
    """Group ledger rows by the requested key. Returns a list of bucket
    dicts sorted by total_tokens desc — the shape the UI wants."""
    key_fn = {
        "provider": lambda r: (r.get("provider"),),
        "model": lambda r: (r.get("model"),),
        "operation": lambda r: (r.get("operation"),),
        "feature": lambda r: (r.get("feature"),),
        "provider_model": lambda r: (r.get("provider"), r.get("model")),
    }.get(group_by, lambda r: (r.get("provider"), r.get("model")))

    buckets: dict[tuple, dict] = {}
    for row in rows:
        key = key_fn(row)
        bucket = buckets.setdefault(key, {
            "key": key,
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_brl": 0.0,
        })
        inp = int(row.get("input_tokens") or 0)
        out = int(row.get("output_tokens") or 0)
        bucket["calls"] += 1
        bucket["prompt_tokens"] += inp
        bucket["completion_tokens"] += out
        bucket["total_tokens"] += inp + out
        bucket["cost_usd"] += float(row.get("cost_usd") or 0)
        bucket["cost_brl"] += float(row.get("cost_brl") or 0)
    out_rows = list(buckets.values())
    out_rows.sort(key=lambda b: b["total_tokens"], reverse=True)
    return out_rows
