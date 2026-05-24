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

**LLM tool-call audit (llm-tool-audit-rollout — closes the originating
M-4 gap).** The single `digest_narrative` LLM call in `_generate_narrative`
writes one row to `mailing.tool_call_audits` (best-effort; never breaks
the user-facing debrief). Redaction applied per the `mailing.campaign_debrief`
feature in `app/.../services/ai_consent_features.py` — only `campaign_id`
survives in `arguments`, the narrative body is dropped from `result`. See
`KB § PATTERNS/llm-tool-audit.md` for the canonical pattern.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.ai import get_feature
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    apply_feature_redaction,
    now_utc,
)
from noctusai_lib.domain.digest import (
    BaseDigestService,
    DigestResult,
    DigestWindow,
    build_and_send,
    email_template_dir,
    narrative as digest_narrative,
    render_digest_pair,
)
from noctusai_lib.integrations.email.digest import Digest

from app.modules.email_marketing.services.audit_hook import get_audit_writer

logger = logging.getLogger(__name__)


def _record_audit(
    feature_key: str,
    tool_name: str,
    *,
    arguments: Any,
    result: Any,
    status: str,
    duration_ms: int,
    error: Optional[str] = None,
    org_id: Optional[str] = None,
    audit_writer_factory: Optional[Callable[[], Callable[[Any], None]]] = None,
) -> None:
    """Best-effort: build AuditRecord, apply the feature's LGPD redactors,
    write via the lazy audit hook. Never raises — a redactor bug or
    audit-DB outage cannot break the user-facing debrief. Same canonical
    shape as `ai_service._record_audit` / `segmentation_service._record_audit`
    (mailing keeps one thin copy per LLM-dispatching service module rather
    than a cross-service helper for a 3-consumer surface).

    ``audit_writer_factory`` is the Class-E DI seam: defaults to the
    module-level ``get_audit_writer`` (the lazy noop hook in production);
    tests inject a real seed-backed / capturing writer factory through the
    kwarg instead of ``patch.object(cds, "get_audit_writer", ...)``. Per
    ``KB § PATTERNS/di-test-seam.md``."""
    _writer_factory = audit_writer_factory or get_audit_writer
    try:
        record = AuditRecord(
            tool_name=tool_name,
            status=status,  # "success" | "failure"
            duration_ms=duration_ms,
            started_at=now_utc(),
            arguments=arguments,
            result=result,
            error=error,
            conversation_id=org_id,  # no per-conversation surface; org_id stands in.
        )
        feature = get_feature(feature_key)
        if feature is not None:
            record = apply_feature_redaction(
                record,
                redact_arguments=feature.redact_arguments,
                redact_result=feature.redact_result,
            )
        writer = _writer_factory()
        writer(record)
    except Exception:
        logger.exception(
            "mailing.campaign_debrief: audit write failed for feature=%s tool=%s",
            feature_key,
            tool_name,
        )

_TEMPLATE_DIR = email_template_dir(__file__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "mailing-campaign-debrief@v1"


def _pct(num: int, denom: int) -> float:
    return round((num / denom * 100.0), 2) if denom > 0 else 0.0


# accept-with-rationale: Per-product `_render_bodies` + `_generate_narrative` digest wrappers retained at N=4 in KB § PATTERNS/accept-with-rationale.md
async def _generate_narrative(
    *,
    campaign_name: str,
    metrics: dict[str, Any],
    top_links: list[tuple[str, int]],
    org_id: Optional[str],
    campaign_id: Optional[str] = None,
    narrator: Optional[Callable[..., Awaitable[str]]] = None,
    audit_writer_factory: Optional[Callable[[], Callable[[Any], None]]] = None,
) -> str:
    # DI seams: ``narrator`` defaults to the external LLM digest boundary
    # ``digest_narrative``; ``audit_writer_factory`` threads to
    # ``_record_audit``. Tests inject both via kwargs instead of
    # ``patch.object(cds, "digest_narrative"/"get_audit_writer", ...)``.
    # Per ``KB § PATTERNS/di-test-seam.md``.
    _narrate = narrator or digest_narrative
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
    # Audit (llm-tool-audit-rollout — closes the originating M-4 gap for the
    # absorbed email_marketing surface). `digest_narrative` never raises — it
    # returns `fallback` when the LLM is unavailable — so we infer status from
    # whether the fallback was returned. Args carry only `campaign_id` after
    # the `mailing.campaign_debrief` redactor; the narrative body is dropped
    # by `_drop_body` (see `ai_consent_features.py`).
    started = time.perf_counter()
    arguments = {"campaign_id": campaign_id, "org_id": org_id}
    text = await _narrate(
        system=system,
        user_prompt=user_prompt,
        model=MODEL,
        cache=True,
        org_id=org_id,
        fallback=fallback,
    )
    _record_audit(
        "mailing.campaign_debrief",
        "campaign_debrief",
        arguments=arguments,
        result=text,
        status="failure" if text == fallback else "success",
        duration_ms=int((time.perf_counter() - started) * 1000),
        error="LLM unavailable (fallback narrative)" if text == fallback else None,
        org_id=org_id,
        audit_writer_factory=audit_writer_factory,
    )
    return text


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


class _CampaignNotFound(Exception):
    """Internal sentinel raised by `_fetch_window` when the campaign id
    doesn't resolve. The top-level wrapper translates it back to a
    `None` return so the legacy public API shape stays intact."""


class CampaignDebriefService(BaseDigestService):
    """`BaseDigestService` subclass for the mailing campaign debrief.

    The campaign-debrief flow has a "campaign not found" branch that
    returns `None` from the public API. Inside the orchestrator we
    surface that as `_CampaignNotFound` raised from `_fetch_window`;
    `build_debrief` translates the exception back to `None`. This keeps
    the base's `run()` signature totally synchronous re the happy path
    while preserving the legacy Optional-return public shape.
    """

    def __init__(
        self,
        *,
        client: Any,
        campaign_id: str,
        org_id: Optional[str] = None,
    ) -> None:
        super().__init__(client=client, org_id=org_id)
        self.campaign_id = campaign_id

    async def _fetch_window(self, window: DigestWindow):
        fetched = await _fetch_window(
            self.client, campaign_id=self.campaign_id
        )
        if fetched is None:
            raise _CampaignNotFound(self.campaign_id)
        campaign, send_logs, link_clicks = fetched
        return {
            "campaign": campaign,
            "send_logs": send_logs,
            "link_clicks": link_clicks,
        }

    def _aggregate(self, raw):
        campaign = raw["campaign"]
        metrics, top_links = _aggregate(
            campaign, raw["send_logs"], raw["link_clicks"]
        )
        return {
            "campaign_id": campaign.get("id") or self.campaign_id,
            "campaign_name": campaign.get("nome") or "Campanha sem nome",
            "metrics": metrics,
            "top_links": top_links,
        }

    async def _generate_narrative(self, agg, window):
        return await _generate_narrative(
            campaign_name=agg["campaign_name"],
            metrics=agg["metrics"],
            top_links=agg["top_links"],
            org_id=self.org_id,
            campaign_id=agg.get("campaign_id"),
        )

    def _render_bodies(self, agg, narrative):
        return _render_bodies(
            campaign_name=agg["campaign_name"],
            metrics=agg["metrics"],
            top_links=agg["top_links"],
            narrative=narrative,
        )

    def _build_subject(self, agg, window):
        return f"[NoctusAI] Debrief da campanha — {agg['campaign_name']}"

    def _build_summary(self, agg, narrative, window):
        return {
            "campaign_id": agg["campaign_id"],
            "campaign_name": agg["campaign_name"],
            "metrics": agg["metrics"],
            "top_links": [
                {"url": u, "clicks": n}
                for u, n in agg["top_links"][:5]
            ],
            "narrative": narrative,
        }


async def build_debrief(
    db: Any, *, campaign_id: str, org_id: Optional[str] = None
) -> Optional[tuple[Digest, dict[str, Any]]]:
    """Compute aggregates + narrative + render. No DB writes, no email send.

    Returns `(Digest, summary)` or None if the campaign doesn't exist.
    Public API unchanged after the `seed-digest-base-class` refactor —
    internally now delegates to `CampaignDebriefService.run(...)`.
    """
    svc = CampaignDebriefService(
        client=db, campaign_id=campaign_id, org_id=org_id
    )
    try:
        result: DigestResult = await svc.run(DigestWindow(org_id=org_id))
    except _CampaignNotFound:
        logger.debug("build_debrief: campaign %s not found; returning None", campaign_id)
        return None
    return result.digest, result.summary


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
