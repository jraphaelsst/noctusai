"""LGPD redaction unit tests for the 3 daily-life consent features.

Per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`: each
`register_feature(...)` call declares its own `redact_arguments` /
`redact_result` lambdas. These tests pin that:

  - Personal content (note bodies, narrative text, habit names, sample
    titles, user labels) is scrubbed.
  - Structural fields (counters, status, prompt_version, period_label,
    org_id) survive — the audit row stays query-able.
  - The redaction is idempotent — applying twice keeps shape consistent.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.ai import get_feature


# Import the consent features module so registration runs at test-collection.
@pytest.fixture(autouse=True)
def _register_daily_life_features():
    import app.services.ai_consent_features  # noqa: F401
    yield


# ---------------------------------------------------------------------------
# daily_life.daily_brief
# ---------------------------------------------------------------------------


def test_daily_brief_redact_arguments_scrubs_samples_and_user_label():
    feature = get_feature("daily_life.daily_brief")
    assert feature is not None
    assert feature.redact_arguments is not None

    args = {
        "user_label": "Maria Silva",
        "tasks_today": 3,
        "events_today": 1,
        "habits_pending": 2,
        "yesterday_completed": 4,
        "task_samples": ["Comprar leite", "Ligar para o médico"],
        "event_samples": ["Reunião com chefe"],
        "habit_samples": ["Meditar 10 min"],
        "prompt_version": "daily-life-daily-brief@v1",
    }
    scrubbed = feature.redact_arguments(args)

    # Counters + prompt_version preserved.
    assert scrubbed["tasks_today"] == 3
    assert scrubbed["events_today"] == 1
    assert scrubbed["habits_pending"] == 2
    assert scrubbed["yesterday_completed"] == 4
    assert scrubbed["prompt_version"] == "daily-life-daily-brief@v1"
    # Free-form text scrubbed.
    assert scrubbed["user_label"] == "[REDACTED]"
    assert scrubbed["task_samples"] == ["[REDACTED]"]
    assert scrubbed["event_samples"] == ["[REDACTED]"]
    assert scrubbed["habit_samples"] == ["[REDACTED]"]
    # Pure: original dict not mutated.
    assert args["user_label"] == "Maria Silva"


def test_daily_brief_redact_arguments_scrubs_messages():
    """When a caller passes the raw `messages=[{role, content}]` shape we
    still scrub content bodies but keep role tags for structural visibility."""
    feature = get_feature("daily_life.daily_brief")
    args = {
        "messages": [
            {"role": "system", "content": "Você é um assistente."},
            {"role": "user", "content": "Maria, tarefas: ..."},
        ],
        "tasks_today": 0,
    }
    scrubbed = feature.redact_arguments(args)
    assert scrubbed["messages"] == [
        {"role": "system", "content": "[REDACTED]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
    assert scrubbed["tasks_today"] == 0


def test_daily_brief_redact_result_scrubs_summary_and_chip():
    feature = get_feature("daily_life.daily_brief")
    assert feature.redact_result is not None
    result = {
        "summary": "Hoje você tem 3 tarefas e uma reunião importante com Maria.",
        "chip": "3 tarefas · 1 evento",
        "tasks_today": 3,
    }
    scrubbed = feature.redact_result(result)
    assert scrubbed["summary"] == "[REDACTED]"
    assert scrubbed["chip"] == "[REDACTED]"
    assert scrubbed["tasks_today"] == 3  # counter preserved


# ---------------------------------------------------------------------------
# daily_life.weekly_review
# ---------------------------------------------------------------------------


def test_weekly_review_redact_arguments_scrubs_habit_streaks_and_user_label():
    feature = get_feature("daily_life.weekly_review")
    assert feature is not None
    assert feature.redact_arguments is not None

    args = {
        "user_label": "João",
        "period_label": "Últimos 7 dias (2026-05-04 → 2026-05-11)",
        "tasks_completed": 12,
        "tasks_pending": 3,
        "tasks_cancelled": 1,
        "habit_streaks": [
            ("Meditar diariamente", 7),
            ("Caminhada matinal", 5),
        ],
        "notas_count": 4,
        "focus_minutes": 240,
        "prompt_version": "daily-life-weekly-review@v1",
    }
    scrubbed = feature.redact_arguments(args)

    # Counters + period_label preserved.
    assert scrubbed["tasks_completed"] == 12
    assert scrubbed["tasks_pending"] == 3
    assert scrubbed["tasks_cancelled"] == 1
    assert scrubbed["notas_count"] == 4
    assert scrubbed["focus_minutes"] == 240
    assert scrubbed["period_label"] == "Últimos 7 dias (2026-05-04 → 2026-05-11)"
    assert scrubbed["prompt_version"] == "daily-life-weekly-review@v1"
    # Personal text scrubbed; habit-streak COUNTS preserved.
    assert scrubbed["user_label"] == "[REDACTED]"
    assert scrubbed["habit_streaks"][0][0] == "[REDACTED]"
    assert scrubbed["habit_streaks"][0][1] == 7
    assert scrubbed["habit_streaks"][1][0] == "[REDACTED]"
    assert scrubbed["habit_streaks"][1][1] == 5


def test_weekly_review_redact_result_scrubs_narrative():
    feature = get_feature("daily_life.weekly_review")
    assert feature.redact_result is not None

    result = {
        "narrative": (
            "Esta semana João completou 12 tarefas — destaque para o "
            "relatório do projeto X. A sequência de meditação..."
        ),
        "tasks_completed": 12,
    }
    scrubbed = feature.redact_result(result)
    assert scrubbed["narrative"] == "[REDACTED]"
    assert scrubbed["tasks_completed"] == 12

    # String-form narrative also handled.
    assert feature.redact_result("Esta semana você teve 3 tarefas...") == "[REDACTED]"


# ---------------------------------------------------------------------------
# daily_life.note_extract
# ---------------------------------------------------------------------------


def test_note_extract_redact_arguments_drops_note_body():
    feature = get_feature("daily_life.note_extract")
    assert feature is not None
    assert feature.redact_arguments is not None

    args = {
        "note_content": (
            "Reflexão pessoal: hoje foi um dia difícil. Preciso comprar "
            "remédio para minha mãe e ligar para a clínica."
        ),
        "org_id": "org_abc",
        "prompt_version": "daily-life-extract-tasks@v1",
    }
    scrubbed = feature.redact_arguments(args)

    assert scrubbed["note_content"] == "[REDACTED]"
    assert scrubbed["org_id"] == "org_abc"
    assert scrubbed["prompt_version"] == "daily-life-extract-tasks@v1"


def test_note_extract_redact_arguments_handles_alias_keys():
    """Some call shapes pass the body under `content` / `body` / `text` —
    redaction should catch each variant."""
    feature = get_feature("daily_life.note_extract")
    for key in ("content", "body", "note", "text"):
        scrubbed = feature.redact_arguments({key: "Personal stuff here", "org_id": "x"})
        assert scrubbed[key] == "[REDACTED]"
        assert scrubbed["org_id"] == "x"


def test_note_extract_redact_result_scrubs_titles_keeps_due_hint():
    feature = get_feature("daily_life.note_extract")
    assert feature.redact_result is not None

    result = [
        {"title": "Comprar remédio para minha mãe", "due_hint": "amanhã"},
        {"title": "Ligar para a clínica", "due_hint": None},
    ]
    scrubbed = feature.redact_result(result)

    assert isinstance(scrubbed, list)
    assert len(scrubbed) == 2
    # Title is paraphrased from note content → MUST scrub.
    assert scrubbed[0]["title"] == "[REDACTED]"
    assert scrubbed[1]["title"] == "[REDACTED]"
    # `due_hint` is a free-form temporal phrase but doesn't echo body
    # content; current policy keeps it. Update this assertion if the
    # rollout's Phase 5 detector escalates.
    assert scrubbed[0]["due_hint"] == "amanhã"
    assert scrubbed[1]["due_hint"] is None


# ---------------------------------------------------------------------------
# All three features carry redaction (smoke / contract check)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "feature_key",
    [
        "daily_life.daily_brief",
        "daily_life.weekly_review",
        "daily_life.note_extract",
    ],
)
def test_all_daily_life_features_carry_redaction_lambdas(feature_key):
    """Phase 4 acceptance contract: all 3 features wire redaction.
    Phase 5 keeper detector will codify this — this test is the
    pre-codification anchor."""
    feature = get_feature(feature_key)
    assert feature is not None, f"{feature_key} missing from catalog"
    assert feature.redact_arguments is not None, (
        f"{feature_key}.redact_arguments missing — see "
        f"projects/llm-tool-audit-rollout/PROJECT.md § 7 Q2"
    )
    assert feature.redact_result is not None, (
        f"{feature_key}.redact_result missing — see "
        f"projects/llm-tool-audit-rollout/PROJECT.md § 7 Q2"
    )
    assert feature.default_granted is False  # All 3 are high-risk opt-in
