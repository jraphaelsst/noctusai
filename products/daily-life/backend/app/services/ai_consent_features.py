"""Daily Life AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 4 (2026-04-27). 3 features, all
**high-risk** (personal narrative / clinical-adjacent text in prompt) and
therefore `default_granted=False` per §7.2 rubric — opt-in only. Users
must actively grant consent before any of these run.

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.

**LGPD redaction lambdas** (`llm-tool-audit-rollout` Phase 4 — Engineer
LLM-DL). Each feature ships per-feature `redact_arguments` / `redact_result`
callables that scrub personal narrative / journal / task content BEFORE the
`AuditRecord` lands in `daily_life.tool_call_audits`. The audit row keeps
structural fields (counters, status, prompt version) and discards the raw
prompt + LLM completion text. See `KB § PATTERNS/llm-tool-audit.md
§ LGPD redaction` and `projects/llm-tool-audit-rollout/PROJECT.md § 7 Q2`.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.ai import register_feature

# ---------------------------------------------------------------------------
# Redaction lambdas
# ---------------------------------------------------------------------------
#
# Daily Life features carry personal task / journal / habit / focus text. The
# strategy is "structural-keep, content-scrub":
#
#   - Keep aggregate counters, status, prompt version, time window, sample
#     COUNTS — anything that doesn't echo user-authored text back.
#   - Drop / replace the personal content fields (note body, prompt text,
#     LLM completion, sample titles, habit names, etc.) with a fixed redaction
#     marker so the audit row is still query-able by tool_name + status +
#     duration without leaking content.
#
# Per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`: redaction is
# best-effort — `app.services.audit_hook.build_audit_record` logs + falls
# back to raw on lambda failure rather than dropping the audit row entirely.

_REDACTED = "[REDACTED]"
_REDACTED_LIST_MARKER = ["[REDACTED]"]


def _scrub_daily_brief_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """daily_brief: keep counters + prompt_version; redact sample titles
    (task / event / habit names are user-authored personal content)."""
    scrubbed = dict(arguments)
    for key in ("task_samples", "event_samples", "habit_samples"):
        if key in scrubbed and scrubbed[key]:
            scrubbed[key] = _REDACTED_LIST_MARKER
    # Some call sites pass raw `messages=[{role, content}, ...]` — scrub the
    # content bodies but keep the role tags for shape visibility.
    if "messages" in scrubbed and isinstance(scrubbed["messages"], list):
        scrubbed["messages"] = [
            {"role": m.get("role"), "content": _REDACTED} if isinstance(m, dict) else _REDACTED
            for m in scrubbed["messages"]
        ]
    if "user_label" in scrubbed:
        scrubbed["user_label"] = _REDACTED
    return scrubbed


def _scrub_daily_brief_result(result: Any) -> Any:
    """daily_brief result: keep numeric counters; drop the narrative text."""
    if isinstance(result, dict):
        scrubbed = dict(result)
        for key in ("summary", "chip"):
            if key in scrubbed:
                scrubbed[key] = _REDACTED
        return scrubbed
    if isinstance(result, str):
        return _REDACTED
    return result


def _scrub_weekly_review_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """weekly_review: keep counter aggregates + period_label; redact habit
    streak names + user label (free-form, user-authored)."""
    scrubbed = dict(arguments)
    if "habit_streaks" in scrubbed and isinstance(scrubbed["habit_streaks"], list):
        # Each entry is (name, count) — keep the count, redact the name.
        scrubbed["habit_streaks"] = [
            (_REDACTED, entry[1])
            if isinstance(entry, (tuple, list)) and len(entry) >= 2
            else _REDACTED
            for entry in scrubbed["habit_streaks"]
        ]
    if "user_label" in scrubbed:
        scrubbed["user_label"] = _REDACTED
    if "messages" in scrubbed and isinstance(scrubbed["messages"], list):
        scrubbed["messages"] = [
            {"role": m.get("role"), "content": _REDACTED} if isinstance(m, dict) else _REDACTED
            for m in scrubbed["messages"]
        ]
    return scrubbed


def _scrub_weekly_review_result(result: Any) -> Any:
    """weekly_review result: 3-paragraph narrative — drop entirely."""
    if isinstance(result, dict):
        scrubbed = dict(result)
        if "narrative" in scrubbed:
            scrubbed["narrative"] = _REDACTED
        return scrubbed
    if isinstance(result, str):
        return _REDACTED
    return result


def _scrub_note_extract_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """note_extract: the entire note content goes to the LLM — drop note
    body verbatim. Keep only structural fields (org_id, prompt version)."""
    scrubbed = dict(arguments)
    for key in ("note_content", "content", "body", "note", "text"):
        if key in scrubbed and scrubbed[key]:
            scrubbed[key] = _REDACTED
    if "messages" in scrubbed and isinstance(scrubbed["messages"], list):
        scrubbed["messages"] = [
            {"role": m.get("role"), "content": _REDACTED} if isinstance(m, dict) else _REDACTED
            for m in scrubbed["messages"]
        ]
    return scrubbed


def _scrub_note_extract_result(result: Any) -> Any:
    """note_extract result: list of extracted task titles — redact titles
    (they're paraphrased from user-authored note content)."""
    if isinstance(result, list):
        return [
            {"title": _REDACTED, "due_hint": item.get("due_hint")}
            if isinstance(item, dict)
            else _REDACTED
            for item in result
        ]
    if isinstance(result, str):
        return _REDACTED
    return result


# ---------------------------------------------------------------------------
# Catalog registration
# ---------------------------------------------------------------------------

# D1 — Today's brief (HIGH-RISK: personal task / event / habit data in prompt)
register_feature(
    "daily_life.daily_brief",
    title="Resumo do dia por IA",
    rationale=(
        "A IA gera um resumo curto do seu dia (chip + summary) baseado nas "
        "tarefas pendentes, eventos do calendário e hábitos não checados. "
        "Esses dados pessoais transitam pelo provedor LLM. Opt-in: você "
        "precisa ativar explicitamente para que o resumo apareça no header."
    ),
    product="daily-life",
    default_granted=False,
    redact_arguments=_scrub_daily_brief_args,
    redact_result=_scrub_daily_brief_result,
)

# D6 — Weekly review (HIGH-RISK: personal narrative + clinical-adjacent metrics)
register_feature(
    "daily_life.weekly_review",
    title="Revisão semanal por IA",
    rationale=(
        "A IA gera uma narrativa de 3 parágrafos sobre sua semana — tarefas "
        "concluídas/pendentes, sequências de hábitos, anotações, sessões de "
        "foco. Inclui possíveis dados de saúde mental (humor, check-ins). "
        "Esses dados pessoais transitam pelo provedor LLM. Opt-in obrigatório."
    ),
    product="daily-life",
    default_granted=False,
    redact_arguments=_scrub_weekly_review_args,
    redact_result=_scrub_weekly_review_result,
)

# D4 — Note-to-task extraction (HIGH-RISK: full note body text in prompt)
register_feature(
    "daily_life.note_extract",
    title="Extração de tarefas de anotações",
    rationale=(
        "A IA lê o conteúdo completo da sua anotação e sugere tarefas a "
        "partir do texto. O conteúdo da anotação transita pelo provedor LLM "
        "para gerar as sugestões. Opt-in: ative manualmente quando quiser "
        "usar o botão de extração."
    ),
    product="daily-life",
    default_granted=False,
    redact_arguments=_scrub_note_extract_args,
    redact_result=_scrub_note_extract_result,
)
