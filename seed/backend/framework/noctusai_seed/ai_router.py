"""
Shared AI-outputs router — `/api/ai/outputs` for every product that opts in
to the P1 indicator pattern (ai-expansion §5a).

Endpoint:
    GET /api/ai/outputs?ref_type=&ref_id=  → list[AIOutput-shaped dicts]

Storage: `<schema>.ai_outputs` per product. Migration template documented
in `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md § ai/`. RLS policy is
product-specific (typically scopes by org through the entity referenced
by ref_id).

Per the seed-injector pattern: products opt in via
`create_product_app(standard_routers=["ai_outputs", ...])`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from noctusai_lib.ai import fetch_outputs_for

logger = logging.getLogger(__name__)


def create_ai_outputs_router(deps) -> APIRouter:
    """Build the `/api/ai/outputs` router for a product.

    `deps` is the product's `ProductDependencies` instance. The product's
    schema is read from `deps._db.schema` (matches the LLM router pattern).
    """
    router = APIRouter(prefix="/api/ai", tags=["AI"])

    @router.get("/outputs")
    async def list_outputs(
        authorization: Optional[str] = Header(None),
        ref_type: str = Query(..., min_length=1, description="Entity-type label, e.g. 'ativo' / 'nota' / 'campanha'"),
        ref_id: str = Query(..., min_length=1, description="Entity UUID (or other primary-key string)"),
        limit: int = Query(50, ge=1, le=200),
    ):
        """List every AI output recorded against a given entity, newest first."""
        # Auth: any authenticated user; RLS enforces per-row scoping.
        user, token = await deps.get_current_user(authorization)
        # Use the user-token-bound client so RLS applies; falling back to
        # admin client would bypass scoping.
        db = deps.get_user_client(token)
        try:
            rows = fetch_outputs_for(
                db,
                schema=deps._db.schema,
                ref_type=ref_type,
                ref_id=ref_id,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("ai_outputs.list failed for ref=%s/%s: %s", ref_type, ref_id, exc)
            # Empty list keeps the indicator silent rather than crashing the page.
            rows = []
        return {"data": rows, "count": len(rows)}

    return router
