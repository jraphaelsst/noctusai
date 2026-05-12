"""
Daily Life D6 — Friday weekly review (ai-expansion Phase 11).

For a given user, aggregates the past 7 days:
  - Tasks (completed / pending / cancelled)
  - Habit check-ins per active goal/habit
  - Notas (just count — content stays personal, never enters the prompt)
  - Hours of focus sessions (sum of `sessoes_foco.duration_minutes`)

Asks `chat_completion(cache=False, temperature=0)` for a 3-paragraph PT
narrative — `cache=False` because Daily Life data is personal-narrative-
adjacent (matches D4 note-extraction posture in the same product).

Renders html + text inline (Jinja migration is the next cross-cutting
project). Sends via `noctusai_lib.email.digest.send_digest`.

Trigger: `GET /api/ai/weekly-review` returns the rendered narrative for
the Dashboard widget. (The historical `POST /api/ai/weekly-review/send`
email-delivery endpoint was retired in daily-life-wiring Phase 1.)
"""
from __future__ import annotations

import logging
import time as _time
from collections import Counter
from datetime import date, timedelta
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

_TEMPLATE_DIR = email_template_dir(__file__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "daily-life-weekly-review@v1"

# Tool / consent-feature identifiers — exposed for tests + audit-row joins.
TOOL_NAME_WEEKLY_REVIEW = "daily_life.weekly_review.generate_narrative"
FEATURE_KEY_WEEKLY_REVIEW = "daily_life.weekly_review"


def _write_audit(
    *,
    arguments: dict,
    result,
    status: str,
    duration_ms: int,
    error: Optional[str] = None,
) -> None:
    """Best-effort audit-row write — same posture as
    `daily_brief_service._write_audit`. Lazy import so missing SQLAlchemy
    stack never breaks the user-facing dispatch."""
    try:
        from app.services.audit_hook import build_audit_record, get_audit_writer

        writer = get_audit_writer()
        record = build_audit_record(
            feature_key=FEATURE_KEY_WEEKLY_REVIEW,
            tool_name=TOOL_NAME_WEEKLY_REVIEW,
            status=status,
            duration_ms=duration_ms,
            arguments=arguments,
            result=result,
            error=error,
        )
        writer(record)
    except Exception:  # noqa: BLE001 — audit is best-effort by contract
        logger.exception(
            "daily_life.weekly_review: audit-row write failed (best-effort, "
            "tool dispatch unaffected)"
        )


# accept-with-rationale: Per-product `_render_bodies` + `_generate_narrative` digest wrappers retained at N=4 in KB § PATTERNS/accept-with-rationale.md
async def _generate_narrative(
    *,
    user_label: str,
    period_label: str,
    tasks_completed: int,
    tasks_pending: int,
    tasks_cancelled: int,
    habit_streaks: list[tuple[str, int]],
    notas_count: int,
    focus_minutes: int,
    org_id: Optional[str],
) -> str:
    streak_lines = "\n".join(
        f"- {nome}: {streak} check-ins" for nome, streak in habit_streaks[:6]
    ) or "- (sem hábitos rastreados nesta semana)"
    system = (
        "Você é um coach pessoal brasileiro. Resuma a semana de uma pessoa "
        "em três parágrafos curtos: (1) panorama geral (tarefas concluídas, "
        "horas em foco, hábitos), (2) observação sobre padrões positivos ou "
        "preocupantes, (3) UMA recomendação concreta para a próxima semana. "
        "Tom direto, amigável, sem clichês motivacionais e sem emojis. Não "
        "invente dados além dos fornecidos."
    )
    user_prompt = (
        f"Pessoa: {user_label}\n"
        f"Período: {period_label}\n"
        f"Tarefas concluídas: {tasks_completed}\n"
        f"Tarefas pendentes: {tasks_pending}\n"
        f"Tarefas canceladas: {tasks_cancelled}\n"
        f"Notas escritas: {notas_count}\n"
        f"Tempo em foco: {focus_minutes} minutos ({focus_minutes // 60}h{focus_minutes % 60:02d})\n"
        f"Check-ins por hábito:\n{streak_lines}"
    )
    fallback = (
        f"Resumo automático ({period_label}): {tasks_completed} tarefas concluídas, "
        f"{tasks_pending} pendentes, {focus_minutes} min em foco, {notas_count} notas. "
        f"Sem narrativa detalhada — LLM indisponível para esta janela."
    )
    # Audit payload — `_scrub_weekly_review_args` keeps counters + period_label,
    # redacts user_label + habit-streak names (free-form, user-authored).
    audit_args = {
        "user_label": user_label,
        "period_label": period_label,
        "tasks_completed": tasks_completed,
        "tasks_pending": tasks_pending,
        "tasks_cancelled": tasks_cancelled,
        "habit_streaks": habit_streaks,
        "notas_count": notas_count,
        "focus_minutes": focus_minutes,
        "prompt_version": PROMPT_VERSION,
        "org_id": org_id,
    }
    started = _time.monotonic()
    try:
        narrative = await digest_narrative(
            system=system,
            user_prompt=user_prompt,
            model=MODEL,
            cache=False,  # Personal-narrative-adjacent (LGPD posture).
            org_id=org_id,
            fallback=fallback,
        )
    except Exception as exc:
        _write_audit(
            arguments=audit_args,
            result={"narrative": fallback, "fallback": True},
            status="failure",
            duration_ms=int((_time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    # `digest_narrative` returns the fallback string itself on LLM failure
    # (no exception raised). We can't distinguish success-with-LLM from
    # fallback-on-LLM-failure at this layer reliably — record as success
    # since narrative was produced. The redaction lambda drops the body
    # before storage regardless.
    _write_audit(
        arguments=audit_args,
        result={"narrative": narrative},
        status="success",
        duration_ms=int((_time.monotonic() - started) * 1000),
    )
    return narrative


async def _fetch_window(
    db: Any, user_id: str, period_days: int
) -> dict[str, Any]:
    """Pull all the user's daily_life data for the past `period_days`.

    Returns a dict shaped for `_aggregate` + `build_review`.
    """
    cutoff_date = (date.today() - timedelta(days=period_days)).isoformat()
    cutoff_ts = f"{cutoff_date}T00:00:00+00:00"

    tarefas = (
        db.table("tarefas")
        .select("id, status, prioridade, titulo, updated_at")
        .eq("user_id", user_id)
        .gte("updated_at", cutoff_ts)
        .limit(1000)
        .execute()
    ).data or []

    metas = (
        db.table("metas")
        .select("id, titulo, tipo, status")
        .eq("user_id", user_id)
        .eq("status", "ativa")
        .limit(50)
        .execute()
    ).data or []

    meta_ids = [m["id"] for m in metas]
    checkins = []
    if meta_ids:
        checkins = (
            db.table("checkins")
            .select("meta_id, data")
            .in_("meta_id", meta_ids)
            .gte("data", cutoff_date)
            .limit(500)
            .execute()
        ).data or []

    notas = (
        db.table("notas")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", cutoff_ts)
        .limit(500)
        .execute()
    ).data or []

    focus_sessions = (
        db.table("sessoes_foco")
        .select("duration_minutes")
        .eq("user_id", user_id)
        .gte("created_at", cutoff_ts)
        .limit(500)
        .execute()
    ).data or []

    return {
        "tarefas": tarefas,
        "metas": metas,
        "checkins": checkins,
        "notas": notas,
        "focus_sessions": focus_sessions,
    }


def _aggregate(window: dict[str, Any]) -> dict[str, Any]:
    """Compute the metrics surfaced to the LLM + the email."""
    status_counts: Counter[str] = Counter()
    for t in window["tarefas"]:
        status_counts[t.get("status") or "?"] += 1

    metas_by_id = {m["id"]: m for m in window["metas"]}
    checkins_by_meta: Counter[str] = Counter()
    for c in window["checkins"]:
        checkins_by_meta[c["meta_id"]] += 1
    habit_streaks = sorted(
        (
            (metas_by_id.get(mid, {}).get("titulo") or "Hábito sem nome", n)
            for mid, n in checkins_by_meta.items()
        ),
        key=lambda x: x[1],
        reverse=True,
    )

    focus_minutes = sum(
        int(s.get("duration_minutes") or 0) for s in window["focus_sessions"]
    )

    return {
        "tasks_completed": status_counts.get("concluida", 0),
        "tasks_pending": status_counts.get("pendente", 0)
        + status_counts.get("em_progresso", 0),
        "tasks_cancelled": status_counts.get("cancelada", 0),
        "habit_streaks": habit_streaks,
        "notas_count": len(window["notas"]),
        "focus_minutes": focus_minutes,
    }


def _render_bodies(
    *, user_label: str, period_label: str, agg: dict[str, Any], narrative: str
) -> tuple[str, str]:
    fm = agg["focus_minutes"]
    return render_digest_pair(
        "weekly_review",
        narrative=narrative,
        context={
            "user_label": user_label,
            "period_label": period_label,
            "tasks_completed": agg["tasks_completed"],
            "tasks_pending": agg["tasks_pending"],
            "notas_count": agg["notas_count"],
            "habit_streaks": agg["habit_streaks"],
            "focus_label": f"{fm // 60}h{fm % 60:02d}",
        },
        search_paths=[_TEMPLATE_DIR],
        prompt_version=PROMPT_VERSION,
    )


class WeeklyReviewService(BaseDigestService):
    """`BaseDigestService` subclass for the daily-life weekly review.

    Methods delegate to the module-level helpers (`_fetch_window`,
    `_aggregate`, `_generate_narrative`, `_render_bodies`) so existing
    test imports keep working. The class adds the orchestration shape
    + the user-scoped extras (user_id, user_label) that the abstract
    DigestWindow doesn't carry by default.
    """

    def __init__(
        self,
        *,
        client: Any,
        user_id: str,
        user_label: str = "Você",
        org_id: Optional[str] = None,
    ) -> None:
        super().__init__(client=client, org_id=org_id)
        self.user_id = user_id
        self.user_label = user_label

    async def _fetch_window(self, window: DigestWindow):
        period_days = window.period_days or 7
        raw = await _fetch_window(
            self.client, user_id=self.user_id, period_days=period_days
        )
        return {"window": raw, "period_days": period_days}

    def _aggregate(self, raw):
        agg = _aggregate(raw["window"])
        period_days = raw["period_days"]
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)
        period_label = (
            f"Últimos {period_days} dias "
            f"({start_date.isoformat()} → {end_date.isoformat()})"
        )
        return {**agg, "period_label": period_label}

    async def _generate_narrative(self, agg, window):
        return await _generate_narrative(
            user_label=self.user_label,
            period_label=agg["period_label"],
            tasks_completed=agg["tasks_completed"],
            tasks_pending=agg["tasks_pending"],
            tasks_cancelled=agg["tasks_cancelled"],
            habit_streaks=agg["habit_streaks"],
            notas_count=agg["notas_count"],
            focus_minutes=agg["focus_minutes"],
            org_id=self.org_id,
        )

    def _render_bodies(self, agg, narrative):
        # The module-level _render_bodies expects an `agg` dict that
        # carries a few derived display fields (focus_label is built
        # there). We reconstruct the original-shaped agg for delegation.
        derived_agg = {
            "tasks_completed": agg["tasks_completed"],
            "tasks_pending": agg["tasks_pending"],
            "notas_count": agg["notas_count"],
            "habit_streaks": agg["habit_streaks"],
            "focus_minutes": agg["focus_minutes"],
        }
        return _render_bodies(
            user_label=self.user_label,
            period_label=agg["period_label"],
            agg=derived_agg,
            narrative=narrative,
        )

    def _build_subject(self, agg, window):
        return f"[NoctusAI] Sua semana — {self.user_label}"

    def _build_summary(self, agg, narrative, window):
        # Keep the original summary shape: full agg + narrative +
        # period_label.
        return {
            "tasks_completed": agg["tasks_completed"],
            "tasks_pending": agg["tasks_pending"],
            "tasks_cancelled": agg["tasks_cancelled"],
            "habit_streaks": agg["habit_streaks"],
            "notas_count": agg["notas_count"],
            "focus_minutes": agg["focus_minutes"],
            "narrative": narrative,
            "period_label": agg["period_label"],
        }


async def build_review(
    db: Any,
    *,
    user_id: str,
    user_label: str = "Você",
    org_id: Optional[str] = None,
    period_days: int = 7,
) -> tuple[Digest, dict[str, Any]]:
    """Compute aggregates + narrative + render. No DB writes, no email send.

    Public API unchanged after the `seed-digest-base-class` refactor —
    internally now delegates to `WeeklyReviewService.run(...)`.
    """
    svc = WeeklyReviewService(
        client=db, user_id=user_id, user_label=user_label, org_id=org_id
    )
    result: DigestResult = await svc.run(
        DigestWindow(org_id=org_id, period_days=period_days)
    )
    return result.digest, result.summary


async def send_weekly_review(
    db: Any,
    *,
    user_id: str,
    recipient: str,
    user_label: str = "Você",
    org_id: Optional[str] = None,
    period_days: int = 7,
) -> dict[str, Any]:
    """Build + send via Resend. Returns DigestSendResult-shaped dict."""
    digest, summary = await build_review(
        db,
        user_id=user_id,
        user_label=user_label,
        org_id=org_id,
        period_days=period_days,
    )
    result = await build_and_send(
        digest, recipient=recipient, org_id=org_id, log_prefix="WEEKLY REVIEW"
    )
    return {**result, "summary": summary}
