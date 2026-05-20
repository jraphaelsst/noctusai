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
- `<schema>.llm_usage(org_id, provider, model, operation, *_tokens, cost_estimate_usd, at)`

Both tables live in each product's schema — RLS-scoped per-org. Migrations
ship per product (products/*/backend/migrations/NNN_llm_preferences.sql and
NNN_llm_usage.sql).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import all_providers, models_for
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

    async def _require_org(authorization):
        user, token = await deps.get_current_user(authorization)
        return user, deps.get_org_id(user), token

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
        result = (
            db.table("llm_preferences")
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
        db.table("llm_preferences").upsert(
            {
                "org_id": org_id,
                "provider": body.provider,
                "chat_model": body.chat_model,
                "embedding_model": body.embedding_model,
            },
            on_conflict="org_id",
        ).execute()
        return {"ok": True}

    @router.get("/usage")
    async def obter_usage(
        authorization: Optional[str] = Header(None),
        from_: Optional[str] = Query(None, alias="from", description="ISO-8601 start (default now-30d)"),
        to: Optional[str] = Query(None, description="ISO-8601 end (default now)"),
        group_by: str = Query(
            "provider_model",
            description="provider_model | provider | model | operation",
        ),
        limit: int = Query(5000, ge=1, le=20000, description="Max rows to scan"),
    ):
        """Return LLM token usage + cost for the caller's org.

        RLS-scoped: only the caller's org rows are visible (for ERP admins,
        every row in their org via the admin_full policy).

        Returns `{events, aggregate}` — `events` is the raw sample (capped
        at `limit`), `aggregate` is a grouped summary totalling calls,
        tokens, and estimated cost.
        """
        user, org_id, token = await _require_org(authorization)

        # Resolve date window.
        now = datetime.now(tz=timezone.utc)
        start = _parse_iso(from_) or (now - timedelta(days=30))
        end = _parse_iso(to) or now
        db = deps.get_user_client(token)
        rows = (
            db.table("llm_usage")
            .select("*")
            .gte("at", start.isoformat())
            .lte("at", end.isoformat())
            .order("at", desc=True)
            .limit(limit)
            .execute()
        ).data or []

        return {
            "events": rows,
            "aggregate": _aggregate_rows(rows, group_by),
            "window": {"from": start.isoformat(), "to": end.isoformat()},
        }

    return router


def _aggregate_rows(rows: list[dict], group_by: str) -> list[dict]:
    """Group the raw rows by the requested key. Returns a list of bucket
    dicts sorted by total_tokens desc — the shape the UI wants."""
    key_fn = {
        "provider": lambda r: (r.get("provider"),),
        "model": lambda r: (r.get("model"),),
        "operation": lambda r: (r.get("operation"),),
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
            "cost_estimate_usd": 0.0,
        })
        bucket["calls"] += 1
        bucket["prompt_tokens"] += row.get("prompt_tokens") or 0
        bucket["completion_tokens"] += row.get("completion_tokens") or 0
        bucket["total_tokens"] += row.get("total_tokens") or 0
        bucket["cost_estimate_usd"] += float(row.get("cost_estimate_usd") or 0)
    out = list(buckets.values())
    out.sort(key=lambda b: b["total_tokens"], reverse=True)
    return out
