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

Trigger: cron (Friday afternoon) posts to `POST /api/ai/weekly-review/send`
with the user's id + recipient.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from noctusai_lib.domain.digest import (
    build_and_send,
    narrative as digest_narrative,
    render_with_narrative,
)
from noctusai_lib.integrations.email.digest import Digest

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "email_templates"

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "daily-life-weekly-review@v1"


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
    return await digest_narrative(
        system=system,
        user_prompt=user_prompt,
        model=MODEL,
        cache=False,  # Personal-narrative-adjacent (LGPD posture).
        org_id=org_id,
        fallback=fallback,
    )


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
    return render_with_narrative(
        html_template="weekly_review.html.j2",
        text_template="weekly_review.txt.j2",
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


async def build_review(
    db: Any,
    *,
    user_id: str,
    user_label: str = "Você",
    org_id: Optional[str] = None,
    period_days: int = 7,
) -> tuple[Digest, dict[str, Any]]:
    """Compute aggregates + narrative + render. No DB writes, no email send."""
    window = await _fetch_window(db, user_id=user_id, period_days=period_days)
    agg = _aggregate(window)

    end_date = date.today()
    start_date = end_date - timedelta(days=period_days)
    period_label = f"Últimos {period_days} dias ({start_date.isoformat()} → {end_date.isoformat()})"

    narrative = await _generate_narrative(
        user_label=user_label,
        period_label=period_label,
        tasks_completed=agg["tasks_completed"],
        tasks_pending=agg["tasks_pending"],
        tasks_cancelled=agg["tasks_cancelled"],
        habit_streaks=agg["habit_streaks"],
        notas_count=agg["notas_count"],
        focus_minutes=agg["focus_minutes"],
        org_id=org_id,
    )

    html, text = _render_bodies(
        user_label=user_label, period_label=period_label, agg=agg, narrative=narrative
    )
    digest = Digest(
        subject=f"[NoctusAI] Sua semana — {user_label}",
        text=text,
        html=html,
    )
    summary = {**agg, "narrative": narrative, "period_label": period_label}
    return digest, summary


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
