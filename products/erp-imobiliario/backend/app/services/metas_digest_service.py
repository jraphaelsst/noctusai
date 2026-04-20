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
  - Via Resend using the org's `resend_api_key` (3-tier credential chain).
  - Dry-run when no key resolves — logs the rendered HTML so it can be inspected.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none
from app.services.email_service import _get_resend_config, _send_via_resend
from noctusai_lib.credentials import resolve_credential

logger = logging.getLogger(__name__)


def _fmt_brl(value: float | int | None) -> str:
    if value is None:
        return "R$ 0"
    v = float(value)
    return f"R$ {v:,.0f}".replace(",", ".")


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


def _render_html(ctx: Dict[str, Any], top_rankings: List[Dict[str, Any]]) -> str:
    """Render the digest as a standalone HTML email (inline styles only)."""
    p = ctx["periodo"]
    equipes = ctx["equipes"]
    metas_by_equipe = {
        m["equipe_id"]: m for m in ctx["metas_equipe"] if m.get("categoria") == "vgv"
    }
    realized = ctx["realized_per_equipe"]
    ms = ctx["milestone_counts"]

    # Teams section
    teams_rows = []
    for eq in equipes:
        meta = float((metas_by_equipe.get(eq["id"]) or {}).get("valor_meta") or 0)
        real = realized.get(eq["id"], 0.0)
        pct = int((real / meta) * 100) if meta > 0 else 0
        color = eq.get("cor") or "#888"
        teams_rows.append(
            f'<tr>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee;">'
            f'    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:8px"></span>'
            f'    {eq["nome"]}'
            f'  </td>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;">{_fmt_brl(meta)}</td>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;">{_fmt_brl(real)}</td>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;"><strong>{pct}%</strong></td>'
            f'</tr>'
        )
    teams_html = "".join(teams_rows) or "<tr><td colspan=4 style='padding:8px;text-align:center;color:#888'>Nenhuma equipe configurada.</td></tr>"

    # Rankings section (top 3)
    rank_rows = []
    for i, r in enumerate(top_rankings[:3]):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "#"
        corretor = str(r.get("corretor_id", ""))[:8] + "…"
        score = r.get("score_unificado") or 0
        vgv = r.get("vgv") or 0
        rank_rows.append(
            f'<tr>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee;">{medal} {corretor}</td>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;">{float(score):.1f}</td>'
            f'  <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;">{_fmt_brl(vgv)}</td>'
            f'</tr>'
        )
    rank_html = "".join(rank_rows) or "<tr><td colspan=3 style='padding:8px;text-align:center;color:#888'>Sem eventos pontuados no período.</td></tr>"

    return f"""\
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#fafafa;margin:0;padding:24px;">
<div style="max-width:640px;margin:0 auto;background:white;padding:32px;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.05)">
  <h1 style="color:#111;margin:0 0 4px 0">Fechamento de quinzena</h1>
  <p style="color:#666;margin:0 0 24px 0">
    {p["tipo"].capitalize()} — de {p["data_inicio"]} a {p["data_fim"]} · status: <strong>{p["status"]}</strong>
  </p>

  <h2 style="color:#111;font-size:16px;margin:24px 0 8px">Top 3 do período</h2>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #111;">Agente</th>
      <th style="text-align:right;padding:8px;border-bottom:2px solid #111;">Score</th>
      <th style="text-align:right;padding:8px;border-bottom:2px solid #111;">VGV</th>
    </tr></thead>
    <tbody>{rank_html}</tbody>
  </table>

  <h2 style="color:#111;font-size:16px;margin:24px 0 8px">Equipes — meta vs realizado</h2>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #111;">Equipe</th>
      <th style="text-align:right;padding:8px;border-bottom:2px solid #111;">Meta VGV</th>
      <th style="text-align:right;padding:8px;border-bottom:2px solid #111;">Realizado</th>
      <th style="text-align:right;padding:8px;border-bottom:2px solid #111;">% atingido</th>
    </tr></thead>
    <tbody>{teams_html}</tbody>
  </table>

  <h2 style="color:#111;font-size:16px;margin:24px 0 8px">Marcos atingidos no período</h2>
  <p style="color:#333">
    {ms.get(50,0)}× agentes bateram 50% · {ms.get(80,0)}× bateram 80% · {ms.get(100,0)}× bateram 100%
  </p>

  <hr style="margin:32px 0;border:none;border-top:1px solid #eee" />
  <p style="color:#999;font-size:12px;margin:0">
    Enviado automaticamente pelo NoctusAI ERP. Veja o painel completo em /metas/dashboard.
  </p>
</div>
</body></html>"""


def _render_text(ctx: Dict[str, Any], top_rankings: List[Dict[str, Any]]) -> str:
    p = ctx["periodo"]
    ms = ctx["milestone_counts"]
    equipes = ctx["equipes"]
    realized = ctx["realized_per_equipe"]
    metas_by_equipe = {m["equipe_id"]: m for m in ctx["metas_equipe"] if m.get("categoria") == "vgv"}

    lines = [
        f"Fechamento de quinzena — {p['tipo']} de {p['data_inicio']} a {p['data_fim']} (status: {p['status']})",
        "",
        "Top 3 do período:",
    ]
    for i, r in enumerate(top_rankings[:3]):
        medal = ["1º", "2º", "3º"][i] if i < 3 else f"{i+1}º"
        lines.append(
            f"  {medal} {str(r.get('corretor_id',''))[:8]}… — score {float(r.get('score_unificado') or 0):.1f} · VGV {_fmt_brl(r.get('vgv'))}"
        )

    lines.append("")
    lines.append("Equipes:")
    for eq in equipes:
        meta = float((metas_by_equipe.get(eq["id"]) or {}).get("valor_meta") or 0)
        real = realized.get(eq["id"], 0.0)
        pct = int((real / meta) * 100) if meta > 0 else 0
        lines.append(f"  {eq['nome']}: {_fmt_brl(meta)} → {_fmt_brl(real)} ({pct}%)")

    lines.append("")
    lines.append(
        f"Marcos: {ms.get(50,0)}× 50%, {ms.get(80,0)}× 80%, {ms.get(100,0)}× 100%"
    )
    return "\n".join(lines)


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
    html = _render_html(ctx, rankings)
    text = _render_text(ctx, rankings)
    subject = f"Fechamento de quinzena — {ctx['periodo']['data_inicio']} a {ctx['periodo']['data_fim']}"

    config = _get_resend_config(ctx["org_id"])
    if not config:
        logger.info("[METAS DIGEST DRY-RUN] To=%s subject=%s", recipient, subject)
        logger.debug("[METAS DIGEST DRY-RUN] body:\n%s", text)
        return {"sent": False, "dry_run": True, "subject": subject, "html": html, "text": text}

    try:
        result = await _send_via_resend(config, recipient, subject, text, html=html)
        logger.info("[METAS DIGEST] sent via Resend id=%s to=%s", result.get("id"), recipient)
        return {"sent": True, "external_id": result.get("id"), "subject": subject}
    except Exception as exc:
        logger.error("[METAS DIGEST] send failed: %s", exc)
        return {"sent": False, "error": str(exc)}
