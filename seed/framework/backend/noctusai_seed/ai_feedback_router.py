"""
Shared AI-feedback router — `/api/ai/feedback` for every product that opts
in to the X3 cross-cutting feedback widget (ai-expansion §5a / Phase 17).

Endpoints:
    POST /api/ai/feedback {output_ref, rating: 1|-1, notes?, prompt_version?}
        → upsert (user_id, output_ref) and return the persisted row.
    GET  /api/ai/feedback?output_ref=...
        → return the calling user's feedback row for that output, or null.

Storage: `<schema>.ai_feedback` per product. Each adopter ships a one-time
migration (template at KB § 04-SHARED-LIBRARY § ai/). RLS is product-
specific — typically scopes by org through `current_org_id()` for
multi-tenant products and by `auth.uid()` for user-scoped products like
Daily Life.

The `output_ref` field is a free-form stable identifier:
    - indicator: ``"ai_output:<uuid>"``
    - digest:    ``"digest:<service>:<token>"`` (e.g. ``"digest:audit_digest:2026-W17"``)

The router itself is auth-and-shape only — RLS does the actual scoping.
Products opt in via ``create_product_app(standard_routers=[..., "ai_feedback"])``.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class FeedbackBody(BaseModel):
    output_ref: str = Field(..., min_length=1, max_length=200)
    rating: int
    notes: Optional[str] = Field(default=None, max_length=2000)
    prompt_version: Optional[str] = Field(default=None, max_length=80)

    @field_validator("rating")
    @classmethod
    def _rating_must_be_thumbs(cls, v: int) -> int:
        if v not in (-1, 1):
            raise ValueError("rating must be 1 (up) or -1 (down)")
        return v


def create_ai_feedback_router(deps) -> APIRouter:
    """Build the `/api/ai/feedback` router for a product."""
    router = APIRouter(prefix="/api/ai", tags=["AI"])

    @router.post("/feedback")
    async def upsert_feedback(
        body: FeedbackBody,
        authorization: Optional[str] = Header(None),
    ):
        user, token = await deps.get_current_user(authorization)
        db = deps.get_user_client(token)

        payload = {
            "user_id": str(user.id),
            "output_ref": body.output_ref,
            "rating": body.rating,
            "notes": body.notes,
            "prompt_version": body.prompt_version,
        }
        # Upsert by (user_id, output_ref) — UNIQUE constraint in the migration
        # makes the second send overwrite the first (toggle behavior).
        try:
            result = (
                db.schema(deps._db.schema)
                .table("ai_feedback")
                .upsert(payload, on_conflict="user_id,output_ref")
                .execute()
            )
        except Exception as exc:
            logger.warning(
                "ai_feedback.upsert failed for ref=%s: %s", body.output_ref, exc
            )
            raise HTTPException(status_code=500, detail="Erro ao registrar feedback")
        rows = result.data if isinstance(result.data, list) else [result.data]
        return {"data": rows[0] if rows else payload}

    @router.get("/feedback")
    async def get_feedback(
        authorization: Optional[str] = Header(None),
        output_ref: str = Query(..., min_length=1, max_length=200),
    ):
        user, token = await deps.get_current_user(authorization)
        db = deps.get_user_client(token)
        try:
            result = (
                db.schema(deps._db.schema)
                .table("ai_feedback")
                .select("*")
                .eq("user_id", str(user.id))
                .eq("output_ref", output_ref)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.warning("ai_feedback.get failed for ref=%s: %s", output_ref, exc)
            return {"data": None}
        rows = result.data or []
        return {"data": rows[0] if rows else None}

    return router
