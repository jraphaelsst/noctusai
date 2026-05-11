"""Platform-admin endpoint to flush the LLM response cache.

Dispatches to the active `CacheBackend` via `flush_for_model` — which handles
InMemoryCacheBackend (dev), RedisCacheBackend (prod), or any other backend
that exposes a `flush_prefix(prefix)` method.

Access: `noctus_role == "admin"` only (platform-level, not per-org). Any
non-admin call → 403.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_user
from app.schemas.admin_cache import FlushBody
from noctusai_lib.integrations.llm import get_llm_config
from noctusai_lib.integrations.llm.cache import flush_for_model
from noctusai_lib.integrations.llm.models import all_providers, models_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/llm-cache", tags=["Admin · LLM Cache"])


async def _require_platform_admin(authorization: Optional[str]) -> None:
    user, _ = await get_current_user(authorization)
    noctus_role = (user.user_metadata or {}).get("noctus_role")
    if noctus_role != "admin":
        raise HTTPException(status_code=403, detail="Platform admin required")


def _validate_target(provider: str, model: str) -> None:
    """Best-effort validation that the provider/model pair is known to the catalog.

    Accepts unknown pairs with only a warning — the cache key is just a
    string, and a noctus admin flushing a provider/model we don't catalog
    yet is a legitimate operation (e.g. a model rolled out before the
    catalog caught up).
    """
    if provider not in all_providers():
        logger.warning("Flush target provider=%s is not in the catalog", provider)
        return
    known_ids = {entry.id for entry in models_for(provider)}
    if model not in known_ids:
        logger.warning(
            "Flush target model=%s not in catalog for provider=%s", model, provider,
        )


@router.post("/flush")
async def flush_llm_cache(
    body: FlushBody,
    authorization: Optional[str] = Header(None),
):
    """Flush every cached response for `(product, provider, model)`.

    Requires `noctus_role=admin`. Idempotent — flushing an already-empty
    bucket returns `{deleted: 0}` without error.
    """
    await _require_platform_admin(authorization)

    config = get_llm_config()
    if config.cache_backend is None or not config.cache_enabled:
        return {"deleted": 0, "note": "cache disabled or no backend configured"}

    _validate_target(body.provider, body.model)

    deleted = await flush_for_model(
        config.cache_backend,
        product=body.product,
        provider=body.provider,
        model=body.model,
    )
    logger.info(
        "admin.llm_cache.flush product=%s provider=%s model=%s deleted=%d",
        body.product, body.provider, body.model, deleted,
    )
    return {"deleted": deleted, "product": body.product, "provider": body.provider, "model": body.model}
