"""Unit tests for the Daily Life today's brief service (Phase 13 D1)."""
import pytest
from unittest.mock import AsyncMock, patch


class TestAggregate:
    def test_passes_through_counts_and_samples(self):
        from app.services.daily_brief_service import _aggregate
        agg = _aggregate({
            "today_tasks": [
                {"id": "t1", "titulo": "Reunião com cliente", "status": "pendente"},
                {"id": "t2", "titulo": "Revisar contrato", "status": "em_progresso"},
            ],
            "today_events": [{"id": "e1", "titulo": "Almoço", "inicio": "2026-04-25T12:00:00+00:00"}],
            "pending_habits": [
                {"id": "m1", "titulo": "Correr"},
                {"id": "m2", "titulo": "Ler"},
            ],
            "yesterday_completed": 5,
        })
        assert agg["tasks_today"] == 2
        assert agg["events_today"] == 1
        assert agg["habits_pending"] == 2
        assert agg["yesterday_completed"] == 5
        assert "Reunião com cliente" in agg["task_samples"]
        assert "Correr" in agg["habit_samples"]


class TestBuildChip:
    def test_combines_buckets(self):
        from app.services.daily_brief_service import _build_chip
        chip = _build_chip({
            "tasks_today": 3, "habits_pending": 2, "events_today": 1,
            "yesterday_completed": 0, "task_samples": [], "event_samples": [], "habit_samples": [],
        })
        assert "3 tarefas" in chip
        assert "2 hábitos" in chip
        assert "1 evento" in chip

    def test_singular_forms(self):
        from app.services.daily_brief_service import _build_chip
        chip = _build_chip({
            "tasks_today": 1, "habits_pending": 1, "events_today": 1,
            "yesterday_completed": 0, "task_samples": [], "event_samples": [], "habit_samples": [],
        })
        assert "1 tarefa" in chip and "1 hábito" in chip and "1 evento" in chip

    def test_empty_falls_back_to_friendly_text(self):
        from app.services.daily_brief_service import _build_chip
        chip = _build_chip({
            "tasks_today": 0, "habits_pending": 0, "events_today": 0,
            "yesterday_completed": 0, "task_samples": [], "event_samples": [], "habit_samples": [],
        })
        assert chip == "tudo livre hoje"

    def test_truncates_to_32_chars(self):
        from app.services.daily_brief_service import _build_chip
        chip = _build_chip({
            "tasks_today": 999, "habits_pending": 999, "events_today": 999,
            "yesterday_completed": 0, "task_samples": [], "event_samples": [], "habit_samples": [],
        })
        assert len(chip) <= 32


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_returns_llm_text_truncated_to_200_chars(self):
        from app.services.daily_brief_service import _generate_summary
        long_text = "a" * 250
        with patch(
            "app.services.daily_brief_service.chat_completion",
            new_callable=AsyncMock,
            return_value=long_text,
        ):
            text = await _generate_summary(
                user_label="Ana",
                agg={
                    "tasks_today": 1, "habits_pending": 0, "events_today": 0,
                    "yesterday_completed": 0, "task_samples": ["x"], "habit_samples": [], "event_samples": [],
                },
                org_id="org-1",
            )
        # Truncated to ≤201 chars (200 + ellipsis).
        assert len(text) <= 201
        assert text.endswith("…") or len(text) == 200

    @pytest.mark.asyncio
    async def test_llm_failure_uses_data_template(self):
        from app.services.daily_brief_service import _generate_summary
        with patch(
            "app.services.daily_brief_service.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            text = await _generate_summary(
                user_label="Ana",
                agg={
                    "tasks_today": 3, "habits_pending": 1, "events_today": 0,
                    "yesterday_completed": 4, "task_samples": [], "habit_samples": [], "event_samples": [],
                },
                org_id=None,
            )
        assert "3 tarefas" in text
        assert "concluiu 4" in text

    @pytest.mark.asyncio
    async def test_empty_day_friendly_fallback(self):
        from app.services.daily_brief_service import _generate_summary
        with patch(
            "app.services.daily_brief_service.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            text = await _generate_summary(
                user_label="X",
                agg={
                    "tasks_today": 0, "habits_pending": 0, "events_today": 0,
                    "yesterday_completed": 0, "task_samples": [], "habit_samples": [], "event_samples": [],
                },
                org_id=None,
            )
        assert "Sem itens" in text


class TestBuildBrief:
    @pytest.mark.asyncio
    async def test_assembles_chip_summary_and_counters(self):
        from app.services import daily_brief_service

        async def _fake_fetch(db, *, user_id):
            return {
                "today_tasks": [{"id": "t1", "titulo": "X"}],
                "today_events": [],
                "pending_habits": [{"id": "m1", "titulo": "Correr"}],
                "yesterday_completed": 4,
            }

        with patch(
            "app.services.daily_brief_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.daily_brief_service.chat_completion",
            new_callable=AsyncMock,
            return_value="Resumo do dia.",
        ):
            result = await daily_brief_service.build_brief(
                db=object(), user_id="u1", user_label="Ana"
            )
        assert result["tasks_today"] == 1
        assert result["habits_pending"] == 1
        assert result["events_today"] == 0
        assert result["yesterday_completed"] == 4
        assert "1 tarefa" in result["chip"]
        assert "1 hábito" in result["chip"]
        assert result["summary"].startswith("Resumo")
        assert result["prompt_version"] == "daily-life-daily-brief@v1"
