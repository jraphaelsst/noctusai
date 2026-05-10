"""
Core C2 — weekly audit-log narrative digest (ai-expansion Phase 9).

Pipeline:
  1. Fetch the past 7 days of `public.audit_logs` for the org.
  2. Aggregate counts per `action` and per `user_id`; identify spikes
     (>20 events of one action in <1h) + privileged events.
  3. Ask `chat_completion(cache=True, temperature=0)` for a 3-paragraph
     PT narrative (whatever happened this week + anomalies + recommended
     review items).
  4. Render html + text bodies (inline f-strings — same shape as the
     metas digest reference adopter).
  5. Hand to `noctusai_lib.email.digest.send_digest` for delivery.

LGPD: audit metadata (action / resource_type / user_id) is workplace
operational data — no PII surfaces in the prompt. The digest is sent only
to organization admins (filtered via `noctus_users.role='admin'` AND
`org_id`-matching).

Trigger: cron / n8n posts to `POST /api/admin/audit-digest/{org_id}`
weekly (typically Monday morning).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

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

logger = logging.getLogger(__name__)

# `app/email_templates/` lives next to `app/services/` — resolved by the seed helper.
_TEMPLATE_DIR = email_template_dir(__file__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "core-audit-digest@v1"

# Privileged actions that always make it into the highlight list, even if
# rare.
_HIGH_PRIORITY_ACTIONS = {
    "user.role_changed",
    "user.deleted",
    "billing.subscription_canceled",
    "license.revoked",
    "api_key.revoked",
    "settings.security_changed",
}


# accept-with-rationale: Per-product `_render_bodies` + `_generate_narrative` digest wrappers retained at N=4 in KB § PATTERNS/accept-with-rationale.md
async def _generate_narrative(
    *,
    org_name: str,
    period_days: int,
    total_events: int,
    actions_by_count: list[tuple[str, int]],
    top_users: list[tuple[str, int]],
    high_priority: list[dict],
    org_id: Optional[str],
) -> str:
    """Ask the LLM for a 3-paragraph PT narrative summarizing the week.

    Returns plain text — the caller wraps it in html/text bodies.
    Falls back to a deterministic template on LLM unavailability.
    """
    bullets_actions = "\n".join(
        f"- {act}: {n} ocorrências" for act, n in actions_by_count[:8]
    ) or "- (nenhuma ação registrada)"
    bullets_users = "\n".join(
        f"- usuário {u[:8]}…: {n} ações" for u, n in top_users[:5]
    ) or "- (sem atividade de usuário)"
    bullets_high = "\n".join(
        f"- {h['action']} sobre {h.get('resource_type', '?')}"
        + (f" (recurso {h['resource_id']})" if h.get("resource_id") else "")
        for h in high_priority[:8]
    ) or "- (nenhuma ação privilegiada na janela)"

    system = (
        "Você é um analista de segurança/operação. Resuma a atividade "
        "operacional da última semana de uma organização em PORTUGUÊS BRASILEIRO, "
        "em três parágrafos curtos: (1) panorama geral, (2) anomalias dignas "
        "de atenção, (3) checklist sugerido para revisão. Não invente "
        "dados além dos fornecidos. Não use emojis."
    )
    user_prompt = (
        f"Organização: {org_name}\n"
        f"Período: últimos {period_days} dias\n"
        f"Total de eventos: {total_events}\n\n"
        f"Ações por contagem:\n{bullets_actions}\n\n"
        f"Usuários mais ativos:\n{bullets_users}\n\n"
        f"Ações privilegiadas detectadas:\n{bullets_high}"
    )
    fallback = (
        f"Resumo automático para {org_name} ({period_days} dias, "
        f"{total_events} eventos no total). "
        f"Ações de maior volume: "
        + ", ".join(f"{a} ({n})" for a, n in actions_by_count[:3])
        + ". Sem narrativa detalhada — LLM indisponível para esta janela."
    )
    return await digest_narrative(
        system=system,
        user_prompt=user_prompt,
        model=MODEL,
        cache=True,
        org_id=org_id,
        fallback=fallback,
    )


def _render_bodies(
    *,
    org_name: str,
    narrative: str,
    actions_by_count: list[tuple[str, int]],
    top_users: list[tuple[str, int]],
    period_days: int,
    total_events: int,
) -> tuple[str, str]:
    """Render `(html, text)` digest bodies via the shared seed helper."""
    return render_digest_pair(
        "audit_digest",
        narrative=narrative,
        context={
            "org_name": org_name,
            "actions_by_count": actions_by_count,
            "top_users": top_users,
            "period_days": period_days,
            "total_events": total_events,
        },
        search_paths=[_TEMPLATE_DIR],
        prompt_version=PROMPT_VERSION,
    )


async def _fetch_audit_window(
    db: Any, org_id: str, period_days: int
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Pull audit_logs + recipient list + org metadata.

    Returns:
        (audit_rows, admin_recipients, org_record)
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    audit_res = (
        db.table("audit_logs")
        .select("id, user_id, action, resource_type, resource_id, created_at")
        .eq("org_id", org_id)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    audit_rows = audit_res.data or []

    org_res = (
        db.table("organizations").select("id, nome").eq("id", org_id).single().execute()
    )
    org_record = org_res.data or {"id": org_id, "nome": "Organização"}

    admin_res = (
        db.table("noctus_users")
        .select("id, email, role")
        .eq("org_id", org_id)
        .eq("role", "admin")
        .execute()
    )
    admin_recipients = admin_res.data or []
    return audit_rows, admin_recipients, org_record


def _aggregate(
    audit_rows: list[dict],
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[dict]]:
    """Build the per-action counts, per-user counts, and high-priority list."""
    action_counter: Counter[str] = Counter()
    user_counter: Counter[str] = Counter()
    high_priority: list[dict] = []
    for row in audit_rows:
        action = row.get("action") or "unknown"
        action_counter[action] += 1
        if row.get("user_id"):
            user_counter[str(row["user_id"])] += 1
        if action in _HIGH_PRIORITY_ACTIONS:
            high_priority.append(row)
    return (
        action_counter.most_common(),
        user_counter.most_common(),
        high_priority,
    )


class AuditDigestService(BaseDigestService):
    """`BaseDigestService` subclass for the core weekly audit digest.

    Methods delegate to the module-level helpers (`_fetch_audit_window`,
    `_aggregate`, `_generate_narrative`, `_render_bodies`) so existing
    test imports keep working. Unlike the other three subclasses,
    audit_digest fans out to ALL admins of an org — handled via
    `_initial_recipients(raw)` returning the admin list pulled by
    `_fetch_audit_window`. The per-product `send_weekly_audit_digest`
    wrapper consumes `result.recipients` to drive the fan-out loop.
    """

    async def _fetch_window(self, window: DigestWindow):
        period_days = window.period_days or 7
        audit_rows, recipients, org_record = await _fetch_audit_window(
            self.client,
            org_id=self.org_id or "",
            period_days=period_days,
        )
        return {
            "audit_rows": audit_rows,
            "recipients": recipients,
            "org_record": org_record,
            "period_days": period_days,
        }

    def _aggregate(self, raw):
        actions_by_count, top_users, high_priority = _aggregate(
            raw["audit_rows"]
        )
        return {
            "org_name": raw["org_record"].get("nome") or "Organização",
            "period_days": raw["period_days"],
            "total_events": len(raw["audit_rows"]),
            "actions_by_count": actions_by_count,
            "top_users": top_users,
            "high_priority": high_priority,
        }

    async def _generate_narrative(self, agg, window):
        return await _generate_narrative(
            org_name=agg["org_name"],
            period_days=agg["period_days"],
            total_events=agg["total_events"],
            actions_by_count=agg["actions_by_count"],
            top_users=agg["top_users"],
            high_priority=agg["high_priority"],
            org_id=self.org_id,
        )

    def _render_bodies(self, agg, narrative):
        return _render_bodies(
            org_name=agg["org_name"],
            narrative=narrative,
            actions_by_count=agg["actions_by_count"],
            top_users=agg["top_users"],
            period_days=agg["period_days"],
            total_events=agg["total_events"],
        )

    def _build_subject(self, agg, window):
        return f"[NoctusAI] Digest semanal — {agg['org_name']}"

    def _build_summary(self, agg, narrative, window):
        return {
            "total_events": agg["total_events"],
            "period_days": agg["period_days"],
            "actions_top": agg["actions_by_count"][:10],
            "high_priority_count": len(agg["high_priority"]),
            "narrative_chars": len(narrative),
        }

    def _initial_recipients(self, raw):
        return raw["recipients"]


async def build_digest(
    db: Any,
    *,
    org_id: str,
    period_days: int = 7,
) -> Optional[tuple[Digest, list[dict], dict[str, Any]]]:
    """Build the digest payload (without sending). Useful for inspection
    endpoints + tests.

    Returns `(Digest, recipients, summary_dict)` or None when the org
    cannot be resolved. Public API unchanged after the
    `seed-digest-base-class` refactor — internally now delegates to
    `AuditDigestService.run(...)`.
    """
    svc = AuditDigestService(client=db, org_id=org_id)
    result: DigestResult = await svc.run(
        DigestWindow(org_id=org_id, period_days=period_days)
    )
    return result.digest, result.recipients, result.summary


async def send_weekly_audit_digest(
    db: Any,
    *,
    org_id: str,
    period_days: int = 7,
) -> dict[str, Any]:
    """Build the digest and send to every admin of the org.

    Returns a structured result with one `DigestSendResult` per recipient
    plus the aggregated summary. Never raises — fall-throughs become
    `error` strings on the per-recipient result.
    """
    built = await build_digest(db, org_id=org_id, period_days=period_days)
    if built is None:
        return {"sent": 0, "results": [], "summary": None, "error": "org_not_found"}

    digest, recipients, summary = built
    results: list[dict[str, Any]] = []
    sent_count = 0
    for admin in recipients:
        email = admin.get("email")
        if not email:
            continue
        outcome = await build_and_send(
            digest, recipient=email, org_id=org_id, log_prefix="AUDIT DIGEST",
        )
        results.append({
            "recipient": email,
            "sent": outcome["sent"],
            "dry_run": outcome["dry_run"],
            "external_id": outcome["external_id"],
            "error": outcome["error"],
        })
        if outcome["sent"]:
            sent_count += 1

    return {
        "sent": sent_count,
        "results": results,
        "summary": summary,
        "subject": digest.subject,
    }
