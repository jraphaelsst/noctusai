"""
`AIOutput` dataclass + persistence helpers for the per-entity AI-output
storage pattern (P1 from ai-expansion §5a Pattern Catalog).

Per-product schema contract: every product that uses `<AIIndicator>` ships
a `<schema>.ai_outputs` table conforming to the shape below. The migration
template is documented in `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md
§ ai/`.

```sql
CREATE TABLE <schema>.ai_outputs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ref_type     TEXT NOT NULL,
    ref_id       UUID NOT NULL,
    kind         TEXT NOT NULL,            -- 'classification' | 'score' | 'flag' | 'extraction' | 'narrative'
    label        TEXT NOT NULL,            -- display text
    score        NUMERIC,                  -- nullable; 0-1 confidence OR arbitrary domain scalar
    chip         TEXT,                     -- nullable; short visual badge (≤20 chars by convention)
    explanation  TEXT,                     -- nullable; hover/expand body (≤140 chars by convention)
    confidence   NUMERIC,                  -- nullable; 0-1
    model_version TEXT,                    -- nullable; e.g. 'gpt-4o-mini'
    prompt_version TEXT,                   -- nullable; e.g. 'erp-categorize@v1'
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON <schema>.ai_outputs (ref_type, ref_id);
CREATE INDEX ON <schema>.ai_outputs (created_at DESC);

ALTER TABLE <schema>.ai_outputs ENABLE ROW LEVEL SECURITY;
-- product-specific policy: typically (org_id-of-ref-row = current_org()).
-- Each product writes its own RLS policy targeting its scoping shape.
```
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


_VALID_KINDS = ("classification", "score", "flag", "extraction", "narrative")


@dataclass
class AIOutput:
    """One row of `<schema>.ai_outputs`.

    Service code constructs one of these per AI inference + persists via
    `persist_output(db, schema, output)`. Fields with `Optional` typing map
    to nullable columns.
    """

    ref_type: str
    ref_id: str
    kind: str  # one of _VALID_KINDS
    label: str
    score: Optional[float] = None
    chip: Optional[str] = None
    explanation: Optional[str] = None
    confidence: Optional[float] = None
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None  # set by DB on insert
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"AIOutput.kind={self.kind!r} not in {_VALID_KINDS}"
            )
        if self.label is None or not str(self.label).strip():
            raise ValueError("AIOutput.label is required (display text)")
        if self.confidence is not None and not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(
                f"AIOutput.confidence={self.confidence} out of [0, 1] range"
            )
        # Soft length warnings (don't raise — just trim for display).
        if self.chip and len(self.chip) > 20:
            self.chip = self.chip[:20]
        if self.explanation and len(self.explanation) > 280:
            self.explanation = self.explanation[:280]

    def to_insert_payload(self) -> dict[str, Any]:
        """Return a dict shaped for `db.table('ai_outputs').insert(...)` —
        drops `id` / `created_at` / `updated_at` (DB-defaulted)."""
        d = asdict(self)
        for k in ("id", "created_at", "updated_at"):
            d.pop(k, None)
        return d


def persist_output(db, schema: str, output: AIOutput) -> dict[str, Any]:
    """Insert an `AIOutput` row and return the persisted dict (with id).

    Args:
        db: any Supabase-like client. Must support `.schema(name).table(name)
            .insert(payload).execute()`. Tests pass `MockSupabaseClient`.
        schema: target product schema (e.g. 'erp', 'mailing', 'pf'). Bare
            `public` callers pass `schema=None` and let the bound client
            decide.
        output: the `AIOutput` to persist.

    Returns:
        Dict with the persisted row including `id` + DB-set timestamps.
    """
    payload = output.to_insert_payload()
    # Set updated_at on insert too — products that re-insert (overwrite) will
    # see consistent timestamps.
    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    if schema:
        result = db.schema(schema).table("ai_outputs").insert(payload).execute()
    else:
        result = db.table("ai_outputs").insert(payload).execute()
    rows = result.data if isinstance(result.data, list) else [result.data]
    return rows[0] if rows else {}


def fetch_outputs_for(
    db, schema: str, ref_type: str, ref_id: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Fetch every `ai_outputs` row matching `(ref_type, ref_id)`, newest first.

    The frontend's `<AIIndicator>` calls this via the `/api/ai/outputs`
    endpoint that the seed framework registers as a standard router (P1
    pattern; opt-in via `standard_routers=["ai_outputs"]`).
    """
    if schema:
        q = db.schema(schema).table("ai_outputs")
    else:
        q = db.table("ai_outputs")
    result = (
        q.select("*")
        .eq("ref_type", ref_type)
        .eq("ref_id", ref_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def safe_persist_indicator(
    db,
    *,
    schema: Optional[str],
    ref_type: str,
    ref_id: str,
    out: dict,
    logger: Optional[logging.Logger] = None,
) -> dict:
    """Build an `AIOutput` from an AI-service dict + persist it; on failure,
    return the would-have-inserted payload with ``id=None`` and a
    ``persist_error`` key so the caller can still surface the inference.

    This is the seed-side absorption of the byte-identical
    ``_persist_indicator`` wrappers shipped in PF + ERP routers.
    Filed by `projects/ai-plumbing-seed-absorption/` (2026-05-04) at N=2
    recurrence; see `KB § PATTERNS/project-execution.md § 2.7`.

    Args:
        db: any Supabase-like client (same contract as `persist_output`).
        schema: target product schema (e.g. ``"erp"``, ``"personal-finance"``);
            ``None`` is allowed for `public`-schema callers.
        ref_type: the entity type the indicator references (e.g. ``"transacao"``,
            ``"ativo"``, ``"cliente"``).
        ref_id: the entity id (UUID-string).
        out: the AI-service-produced dict. Required keys: ``kind``, ``label``.
            Optional keys consumed: ``score``, ``chip``, ``explanation``,
            ``confidence``, ``model_version``, ``prompt_version``. Extra keys
            are ignored — callers may carry e.g. ``matched_categoria_id`` for
            downstream merging without affecting persistence.
        logger: optional logger; on persist failure a `WARNING` is emitted.
            Pass the product's module logger to keep the warning scoped.

    Returns:
        On success — the persisted row dict (with ``id`` + DB-set timestamps).
        On persist failure — ``{**output.to_insert_payload(), "id": None,
        "persist_error": str(e)}`` so the caller can show the indicator
        client-side without a 5xx (next persist run can retry).

    Persist failure is intentionally non-fatal — the indicator just won't
    show server-side until a successful run. The caller's HTTP response
    stays 200; the warning surfaces the issue for ops.
    """
    output = AIOutput(
        ref_type=ref_type,
        ref_id=ref_id,
        kind=out["kind"],
        label=out["label"],
        score=out.get("score"),
        chip=out.get("chip"),
        explanation=out.get("explanation"),
        confidence=out.get("confidence"),
        model_version=out.get("model_version"),
        prompt_version=out.get("prompt_version"),
    )
    try:
        return persist_output(db, schema=schema, output=output)
    except Exception as e:
        if logger is not None:
            logger.warning(
                "ai.persist_indicator failed for %s/%s: %s", ref_type, ref_id, e
            )
        return {**output.to_insert_payload(), "id": None, "persist_error": str(e)}
