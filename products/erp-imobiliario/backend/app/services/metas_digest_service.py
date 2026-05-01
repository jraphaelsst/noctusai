"""
Metas biweekly digest — builds and sends the quinzena-closing email summary.

Triggered:
  - Manually via `POST /api/metas/digest/{periodo_id}` (admin-only).
  - Externally via a cron job (n8n / GitHub Actions) that posts to the
    same endpoint on the Friday of each quinzena.

Content:
  - Period name + date range + status
  - Top-3 unificado ranking (rank, corretor, score, VGV)
  - Team-level summary (meta vs realized per team)
  - Milestone stats (how many 50/80/100% crossings happened in the period)

Delivery:
  - Delegates to `noctusai_lib.email.digest.send_digest` (P3 pattern, shipped
    by ai-expansion Tier 2 Phase 4 2026-04-25). The shared helper handles the
    3-tier credential chain (org → platform → env), dry-run on missing key,
    and Resend POST with structured return shape. This service is now purely
    domain logic + render; the send-machinery is shared.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none
from noctusai_lib.integrations.email.digest import Digest, render as render_digest, send_digest
from noctusai_lib.primitives.parsing import format_brl

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "email_templates"


def _fmt_brl(value: float | int | None) -> str:
    """Thin alias of `noctusai_lib.parsing.format_brl(..., decimals=0)`.

    ERP digest renders monetary values without centavos for compactness
    (e.g. "R$ 1.234"). The lib helper handles the rest (None → "R$ 0",
    BRL-locale separators).
    """
    return format_brl(value, decimals=0)


async def _fetch_context(db: Any, periodo_id: str) -> Optional[Dict[str, Any]]:
    """Gather everything needed to render the digest. Returns None if
    the period doesn't exist or has no org_id."""
    periodo = first_or_none(
        db.table("meta_periodos").select("*").eq("id", periodo_id).execute()
    )
    if not periodo:
        return None
    org_id = periodo["org_id"]

    equipes = db.table("equipes").select("*").eq("org_id", org_id).eq("ativo", True).execute().data or []
    metas_equipe = (
        db.table("metas_equipe").select("*").eq("periodo_id", periodo_id).execute().data or []
    )

    # Realized VGV per equipe (sum of meta_eventos.valor_vgv for members in the
    # period window). Implemented as one query per equipe to keep logic simple —
    # can be a view later.
    realized_per_equipe: Dict[str, float] = {}
    for equipe in equipes:
        membros_rows = (
            db.table("equipe_membros")
            .select("user_id")
            .eq("equipe_id", equipe["id"])
            .is_("left_at", "null")
            .execute()
            .data or []
        )
        member_ids = [m["user_id"] for m in membros_rows]
        if not member_ids:
            realized_per_equipe[equipe["id"]] = 0.0
            continue
        eventos = (
            db.table("meta_eventos")
            .select("valor_vgv")
            .in_("corretor_id", member_ids)
            .gte("created_at", periodo["data_inicio"])
            .lte("created_at", periodo["data_fim"])
            .execute()
            .data or []
        )
        realized_per_equipe[equipe["id"]] = sum(float(e.get("valor_vgv") or 0) for e in eventos)

    # Milestone crossings for the period.
    milestones = (
        db.table("meta_milestones")
        .select("milestone")
        .eq("periodo_id", periodo_id)
        .execute()
        .data or []
    )
    milestone_counts = {50: 0, 80: 0, 100: 0}
    for m in milestones:
        milestone_counts[m["milestone"]] = milestone_counts.get(m["milestone"], 0) + 1

    return {
        "periodo": periodo,
        "org_id": org_id,
        "equipes": equipes,
        "metas_equipe": metas_equipe,
        "realized_per_equipe": realized_per_equipe,
        "milestone_counts": milestone_counts,
    }


def _build_template_context(
    ctx: Dict[str, Any], top_rankings: List[Dict[str, Any]]
) -> dict[str, Any]:
    """Translate the domain context into pre-formatted strings for the
    Jinja template. Keeps templates declarative + matches the BRL/medal
    conventions of the original inline render."""
    p = ctx["periodo"]
    equipes_raw = ctx["equipes"]
    metas_by_equipe = {
        m["equipe_id"]: m for m in ctx["metas_equipe"] if m.get("categoria") == "vgv"
    }
    realized = ctx["realized_per_equipe"]
    ms = ctx["milestone_counts"]

    equipes_view: list[dict[str, Any]] = []
    for eq in equipes_raw:
        meta = float((metas_by_equipe.get(eq["id"]) or {}).get("valor_meta") or 0)
        real = realized.get(eq["id"], 0.0)
        pct = int((real / meta) * 100) if meta > 0 else 0
        equipes_view.append({
            "nome": eq["nome"],
            "cor": eq.get("cor") or "#888",
            "meta_brl": _fmt_brl(meta),
            "real_brl": _fmt_brl(real),
            "pct": pct,
        })

    medals_html = ["🥇", "🥈", "🥉"]
    medals_text = ["1º", "2º", "3º"]
    rankings_view: list[dict[str, Any]] = []
    for i, r in enumerate(top_rankings[:3]):
        rankings_view.append({
            "medal": medals_html[i] if i < 3 else "#",
            "medal_text": medals_text[i] if i < 3 else f"{i+1}º",
            "corretor_short": str(r.get("corretor_id", ""))[:8] + "…",
            "score_label": f"{float(r.get('score_unificado') or 0):.1f}",
            "vgv_brl": _fmt_brl(r.get("vgv") or 0),
        })

    return {
        "periodo_tipo": str(p["tipo"]).capitalize(),
        "periodo_inicio": p["data_inicio"],
        "periodo_fim": p["data_fim"],
        "periodo_status": p["status"],
        "top_rankings": rankings_view,
        "equipes": equipes_view,
        "milestone_50": ms.get(50, 0),
        "milestone_80": ms.get(80, 0),
        "milestone_100": ms.get(100, 0),
    }


def _render_bodies(
    ctx: Dict[str, Any], top_rankings: List[Dict[str, Any]]
) -> tuple[str, str]:
    return render_digest(
        html_template="metas_digest.html.j2",
        text_template="metas_digest.txt.j2",
        context=_build_template_context(ctx, top_rankings),
        search_paths=[_TEMPLATE_DIR],
    )


async def send_biweekly_digest(
    db: Any,
    periodo_id: str,
    recipient: str,
    top_rankings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build and send the biweekly digest email.

    `top_rankings` should be passed in by the caller (the router computes it
    via `meta_rankings_service`) so this function stays presentation-only
    and independent of the ranking implementation.
    """
    ctx = await _fetch_context(db, periodo_id)
    if not ctx:
        return {"sent": False, "reason": "periodo_not_found"}

    rankings = top_rankings or []
    html, text = _render_bodies(ctx, rankings)
    subject = f"Fechamento de quinzena — {ctx['periodo']['data_inicio']} a {ctx['periodo']['data_fim']}"

    digest = Digest(subject=subject, text=text, html=html)
    result = await send_digest(
        digest, recipient=recipient, org_id=ctx["org_id"], log_prefix="METAS DIGEST",
    )

    # Preserve the legacy return-dict shape so router callers don't break.
    if result.dry_run:
        return {
            "sent": False, "dry_run": True, "subject": subject,
            "html": html, "text": text,
        }
    if result.error:
        return {"sent": False, "error": result.error}
    return {"sent": True, "external_id": result.external_id, "subject": subject}
