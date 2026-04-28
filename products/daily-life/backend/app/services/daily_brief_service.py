"""
Daily Life D1 — today's brief badge (ai-expansion Phase 13).

The P4 LayoutEnrichment.aiBadge surface is small (one line in the header
band), so this service produces TWO outputs side-by-side:

  - `chip` — ≤32 chars summary like "3 tarefas · 2 hábitos · 1 evento"
  - `summary` — 1-2 sentence PT narrative (≤200 chars) shown on hover

Aggregates the user's data for *today* (not the past week — that's D6's
weekly review):

  - Tarefas with `data_vencimento = today` and status in (pendente,
    em_progresso)
  - Eventos with `inicio` between today's 00:00 and 24:00
  - Active habits (`metas.tipo='habito'`, `status='ativa'`,
    `frequencia='diario'`) without a check-in for today
  - Yesterday completion stats (concluida count) for the comparison line

LGPD: same posture as D6 — `cache=False`. Personal-narrative-adjacent.

Trigger: `useLayoutEnrichment` calls `useDailyBrief` on every page load
that opts in. Hook is `staleTime`-cached for 15 minutes, then refreshed.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.llm import chat_completion

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "daily-life-daily-brief@v1"


def _aggregate(window: dict[str, Any]) -> dict[str, Any]:
    """Compute the chip-friendly counters from the fetched window."""
    today_tasks = window["today_tasks"]
    today_events = window["today_events"]
    pending_habits = window["pending_habits"]
    yesterday_completed = window["yesterday_completed"]

    return {
        "tasks_today": len(today_tasks),
        "events_today": len(today_events),
        "habits_pending": len(pending_habits),
        "yesterday_completed": yesterday_completed,
        # Surface a few sample titles so the LLM can be specific without
        # leaking long lists into the chip.
        "task_samples": [t.get("titulo") for t in today_tasks[:3] if t.get("titulo")],
        "event_samples": [e.get("titulo") for e in today_events[:3] if e.get("titulo")],
        "habit_samples": [h.get("titulo") for h in pending_habits[:3] if h.get("titulo")],
    }


async def _fetch_window(db: Any, user_id: str) -> dict[str, Any]:
    """Pull today/yesterday/active-habit data for `user_id`."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_iso = today.isoformat()
    yesterday_iso = yesterday.isoformat()
    today_start = f"{today_iso}T00:00:00+00:00"
    today_end = f"{today_iso}T23:59:59+00:00"

    today_tasks = (
        db.table("tarefas")
        .select("id, titulo, status")
        .eq("user_id", user_id)
        .eq("data_vencimento", today_iso)
        .in_("status", ["pendente", "em_progresso"])
        .limit(50)
        .execute()
    ).data or []

    today_events = (
        db.table("eventos")
        .select("id, titulo, inicio")
        .eq("user_id", user_id)
        .gte("inicio", today_start)
        .lte("inicio", today_end)
        .order("inicio")
        .limit(50)
        .execute()
    ).data or []

    daily_habits = (
        db.table("metas")
        .select("id, titulo")
        .eq("user_id", user_id)
        .eq("tipo", "habito")
        .eq("status", "ativa")
        .eq("frequencia", "diario")
        .limit(50)
        .execute()
    ).data or []

    pending_habits: list[dict] = []
    if daily_habits:
        habit_ids = [h["id"] for h in daily_habits]
        # Pull today's check-ins for these habits and exclude them from
        # the pending list. Single round-trip via .in_().
        todays_checkins = (
            db.table("checkins")
            .select("meta_id")
            .in_("meta_id", habit_ids)
            .eq("data", today_iso)
            .execute()
        ).data or []
        checked_in = {c["meta_id"] for c in todays_checkins}
        pending_habits = [h for h in daily_habits if h["id"] not in checked_in]

    yesterday_done = (
        db.table("tarefas")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "concluida")
        .gte("updated_at", f"{yesterday_iso}T00:00:00+00:00")
        .lte("updated_at", f"{yesterday_iso}T23:59:59+00:00")
        .execute()
    )
    yesterday_completed = yesterday_done.count if hasattr(yesterday_done, "count") and yesterday_done.count is not None else len(yesterday_done.data or [])

    return {
        "today_tasks": today_tasks,
        "today_events": today_events,
        "pending_habits": pending_habits,
        "yesterday_completed": yesterday_completed,
    }


def _build_chip(agg: dict[str, Any]) -> str:
    """Compact ≤32 char chip — `'3 tarefas · 2 hábitos · 1 evento'`."""
    parts: list[str] = []
    if agg["tasks_today"]:
        parts.append(f"{agg['tasks_today']} tarefa{'s' if agg['tasks_today'] != 1 else ''}")
    if agg["habits_pending"]:
        parts.append(f"{agg['habits_pending']} hábito{'s' if agg['habits_pending'] != 1 else ''}")
    if agg["events_today"]:
        parts.append(f"{agg['events_today']} evento{'s' if agg['events_today'] != 1 else ''}")
    chip = " · ".join(parts) if parts else "tudo livre hoje"
    return chip[:32]


async def _generate_summary(
    *,
    user_label: str,
    agg: dict[str, Any],
    org_id: Optional[str],
) -> str:
    """LLM 1-2 sentence PT summary. Falls back to deterministic template."""
    samples = []
    if agg["task_samples"]:
        samples.append("tarefas: " + ", ".join(agg["task_samples"][:3]))
    if agg["habit_samples"]:
        samples.append("hábitos: " + ", ".join(agg["habit_samples"][:3]))
    if agg["event_samples"]:
        samples.append("eventos: " + ", ".join(agg["event_samples"][:3]))
    samples_text = "\n".join(f"- {s}" for s in samples) or "- (nada planejado para hoje)"

    system = (
        "Você é um assistente pessoal brasileiro. Resuma o dia de uma "
        "pessoa em UMA OU DUAS frases curtas (máximo 200 caracteres no "
        "total). Seja específico quando houver dados; nunca invente. "
        "Tom direto, sem clichês motivacionais e sem emojis."
    )
    user_prompt = (
        f"Pessoa: {user_label}\n"
        f"Tarefas hoje: {agg['tasks_today']}\n"
        f"Eventos hoje: {agg['events_today']}\n"
        f"Hábitos pendentes: {agg['habits_pending']}\n"
        f"Tarefas concluídas ontem: {agg['yesterday_completed']}\n"
        f"Itens em destaque:\n{samples_text}"
    )
    try:
        text = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=120,
            cache=False,  # Personal-narrative-adjacent.
            org_id=org_id,
        )
        # Truncate to 200 chars at a word boundary.
        text = text.strip()
        if len(text) > 200:
            cut = text[:200].rsplit(" ", 1)[0]
            text = cut + "…"
        return text
    except Exception:
        logger.warning("daily_life.daily_brief: LLM unavailable — using template fallback")
        if agg["tasks_today"] == 0 and agg["habits_pending"] == 0 and agg["events_today"] == 0:
            return "Sem itens agendados para hoje."
        return (
            f"Hoje: {agg['tasks_today']} tarefas, {agg['habits_pending']} hábitos "
            f"e {agg['events_today']} eventos. Ontem você concluiu {agg['yesterday_completed']} tarefas."
        )


async def build_brief(
    db: Any,
    *,
    user_id: str,
    user_label: str = "Você",
    org_id: Optional[str] = None,
) -> dict[str, Any]:
    """Compute today's brief — `chip` + `summary` + raw counters."""
    window = await _fetch_window(db, user_id=user_id)
    agg = _aggregate(window)
    chip = _build_chip(agg)
    summary = await _generate_summary(
        user_label=user_label, agg=agg, org_id=org_id
    )
    return {
        "chip": chip,
        "summary": summary,
        "tasks_today": agg["tasks_today"],
        "events_today": agg["events_today"],
        "habits_pending": agg["habits_pending"],
        "yesterday_completed": agg["yesterday_completed"],
        "prompt_version": PROMPT_VERSION,
    }
