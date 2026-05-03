"""
Mailing M4 — campaign debrief (ai-expansion Phase 12).

After a campaign finishes sending (status='enviada' / completed_at set),
this service produces a post-mortem narrative for the campaign creator:

  1. Aggregates `mailing.send_logs` for the campaign:
     - Total recipients, sent, delivered, opened, clicked, bounced, complained, failed
     - Top clicked links (joined from `mailing.link_clicks`)
     - Bounce rate + open rate + click rate
  2. Asks `chat_completion(cache=True, temperature=0)` for a 3-paragraph
     PT debrief: (1) panorama dos números, (2) o que funcionou ou não,
     (3) UMA recomendação para a próxima campanha.
  3. Renders html + text inline (Jinja migration is pending — see KB
     § 04-SHARED-LIBRARY § email/).
  4. Hands to `noctusai_lib.email.digest.send_digest`.

Trigger: invoked from the campaign-completion path (`send_service` /
`webhooks` finalisation) OR from a scheduled cron post-send hook OR via
manual `POST /api/ai/campaigns/{id}/debrief/send`. The marketer who
created the campaign is the default recipient.

LGPD: send_logs status counts are operational; recipient emails NEVER
enter the prompt; per-link click counts (anonymous totals) do.
"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from noctusai_lib.domain.digest import (
    build_and_send,
    email_template_dir,
    narrative as digest_narrative,
    render_digest_pair,
)
from noctusai_lib.integrations.email.digest import Digest

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = email_template_dir(__file__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "mailing-campaign-debrief@v1"


def _pct(num: int, denom: int) -> float:
    return round((num / denom * 100.0), 2) if denom > 0 else 0.0


async def _generate_narrative(
    *,
    campaign_name: str,
    metrics: dict[str, Any],
    top_links: list[tuple[str, int]],
    org_id: Optional[str],
) -> str:
    link_lines = "\n".join(
        f"- {url}: {n} cliques" for url, n in top_links[:5]
    ) or "- (sem cliques rastreados)"
    system = (
        "Você é um analista de e-mail marketing brasileiro. Resuma o "
        "desempenho de uma campanha em três parágrafos curtos: (1) panorama "
        "dos números, (2) o que funcionou ou não funcionou, (3) UMA "
        "recomendação concreta para a próxima campanha. Tom direto e útil, "
        "sem clichês, sem emojis. Não invente dados além dos fornecidos."
    )
    user_prompt = (
        f"Campanha: {campaign_name}\n"
        f"Total de destinatários: {metrics['total_recipients']}\n"
        f"Enviados: {metrics['sent']} ({metrics['sent_rate']}%)\n"
        f"Entregues: {metrics['delivered']} ({metrics['delivered_rate']}%)\n"
        f"Abertos: {metrics['opened']} ({metrics['open_rate']}%)\n"
        f"Cliques: {metrics['clicked']} ({metrics['click_rate']}%)\n"
        f"Bounces: {metrics['bounced']} ({metrics['bounce_rate']}%)\n"
        f"Reclamações: {metrics['complained']}\n"
        f"Falhas: {metrics['failed']}\n"
        f"Top links clicados:\n{link_lines}"
    )
    fallback = (
        f"Resumo automático da campanha {campaign_name!r}: "
        f"{metrics['delivered']} entregues / {metrics['opened']} aberturas "
        f"({metrics['open_rate']}%) / {metrics['clicked']} cliques "
        f"({metrics['click_rate']}%). Sem narrativa detalhada — LLM "
        f"indisponível para esta janela."
    )
    return await digest_narrative(
        system=system,
        user_prompt=user_prompt,
        model=MODEL,
        cache=True,
        org_id=org_id,
        fallback=fallback,
    )


async def _fetch_window(
    db: Any, campaign_id: str
) -> Optional[tuple[dict[str, Any], list[dict], list[dict]]]:
    """Pull campaign metadata + send_logs + link_clicks for one campaign.

    Returns `(campaign, send_logs, link_clicks)` or `None` if the campaign
    doesn't exist.
    """
    camp_res = (
        db.table("campaigns")
        .select("id, nome, total_recipients, total_sent, total_failed, completed_at, created_by")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    campaign = camp_res.data
    if not campaign:
        return None

    send_logs = (
        db.table("send_logs")
        .select("id, status")
        .eq("campaign_id", campaign_id)
        .limit(5000)
        .execute()
    ).data or []

    send_log_ids = [s["id"] for s in send_logs]
    link_clicks: list[dict] = []
    if send_log_ids:
        link_clicks = (
            db.table("link_clicks")
            .select("send_log_id, url")
            .in_("send_log_id", send_log_ids)
            .limit(2000)
            .execute()
        ).data or []
    return campaign, send_logs, link_clicks


def _aggregate(
    campaign: dict, send_logs: list[dict], link_clicks: list[dict]
) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    """Compute the per-status counts + open/click/bounce rates + top links."""
    status_counter: Counter[str] = Counter()
    for s in send_logs:
        status_counter[s.get("status") or "unknown"] += 1

    sent = sum(
        status_counter.get(k, 0)
        for k in ("sent", "delivered", "opened", "clicked", "bounced", "complained")
    )
    delivered = sum(
        status_counter.get(k, 0)
        for k in ("delivered", "opened", "clicked")
    )
    opened = sum(status_counter.get(k, 0) for k in ("opened", "clicked"))
    clicked = status_counter.get("clicked", 0)
    bounced = status_counter.get("bounced", 0)
    complained = status_counter.get("complained", 0)
    failed = status_counter.get("failed", 0)
    total_recipients = (
        campaign.get("total_recipients") or len(send_logs) or 0
    )

    metrics = {
        "total_recipients": total_recipients,
        "sent": sent,
        "delivered": delivered,
        "opened": opened,
        "clicked": clicked,
        "bounced": bounced,
        "complained": complained,
        "failed": failed,
        "sent_rate": _pct(sent, total_recipients),
        "delivered_rate": _pct(delivered, sent),
        "open_rate": _pct(opened, delivered),
        "click_rate": _pct(clicked, delivered),
        "bounce_rate": _pct(bounced, sent),
    }

    link_counter: Counter[str] = Counter()
    for c in link_clicks:
        url = c.get("url")
        if url:
            link_counter[url] += 1
    top_links = link_counter.most_common(10)
    return metrics, top_links


def _build_metric_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Shape the metrics dict into a list of `{label, value}` rows for the
    Jinja template loop. Pre-formatting here keeps the template thin."""
    return [
        {"label": "Destinatários", "value": metrics["total_recipients"]},
        {"label": "Enviados", "value": f"{metrics['sent']} ({metrics['sent_rate']}%)"},
        {"label": "Entregues", "value": f"{metrics['delivered']} ({metrics['delivered_rate']}%)"},
        {"label": "Aberturas", "value": f"{metrics['opened']} ({metrics['open_rate']}%)"},
        {"label": "Cliques", "value": f"{metrics['clicked']} ({metrics['click_rate']}%)"},
        {"label": "Bounces", "value": f"{metrics['bounced']} ({metrics['bounce_rate']}%)"},
        {"label": "Reclamações", "value": metrics["complained"]},
        {"label": "Falhas", "value": metrics["failed"]},
    ]


def _render_bodies(
    *, campaign_name: str, metrics: dict[str, Any], top_links: list[tuple[str, int]], narrative: str
) -> tuple[str, str]:
    return render_digest_pair(
        "campaign_debrief",
        narrative=narrative,
        context={
            "campaign_name": campaign_name,
            "metric_rows": _build_metric_rows(metrics),
            "top_links": top_links,
        },
        search_paths=[_TEMPLATE_DIR],
        prompt_version=PROMPT_VERSION,
    )


async def build_debrief(
    db: Any, *, campaign_id: str, org_id: Optional[str] = None
) -> Optional[tuple[Digest, dict[str, Any]]]:
    """Compute aggregates + narrative + render. No DB writes, no email send.

    Returns `(Digest, summary)` or None if the campaign doesn't exist.
    """
    fetched = await _fetch_window(db, campaign_id=campaign_id)
    if fetched is None:
        return None
    campaign, send_logs, link_clicks = fetched
    campaign_name = campaign.get("nome") or "Campanha sem nome"

    metrics, top_links = _aggregate(campaign, send_logs, link_clicks)
    narrative = await _generate_narrative(
        campaign_name=campaign_name,
        metrics=metrics,
        top_links=top_links,
        org_id=org_id,
    )

    html, text = _render_bodies(
        campaign_name=campaign_name, metrics=metrics, top_links=top_links, narrative=narrative
    )
    digest = Digest(
        subject=f"[NoctusAI] Debrief da campanha — {campaign_name}",
        text=text,
        html=html,
    )
    summary = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "metrics": metrics,
        "top_links": [{"url": u, "clicks": n} for u, n in top_links[:5]],
        "narrative": narrative,
    }
    return digest, summary


async def send_campaign_debrief(
    db: Any,
    *,
    campaign_id: str,
    recipient: str,
    org_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Build + send via Resend. Returns DigestSendResult-shaped dict, or None
    when the campaign doesn't exist."""
    built = await build_debrief(db, campaign_id=campaign_id, org_id=org_id)
    if built is None:
        return None
    digest, summary = built
    result = await build_and_send(
        digest, recipient=recipient, org_id=org_id, log_prefix="CAMPAIGN DEBRIEF"
    )
    return {**result, "summary": summary}
