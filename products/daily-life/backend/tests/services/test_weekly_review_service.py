"""Unit tests for the Daily Life weekly review service (Phase 11 D6)."""
import pytest
from unittest.mock import AsyncMock, patch

from noctusai_lib.email.digest import DigestSendResult


class TestAggregate:
    def test_counts_tasks_by_status_and_streaks(self):
        from app.services.weekly_review_service import _aggregate
        window = {
            "tarefas": [
                {"status": "concluida", "titulo": "a"},
                {"status": "concluida", "titulo": "b"},
                {"status": "pendente", "titulo": "c"},
                {"status": "em_progresso", "titulo": "d"},
                {"status": "cancelada", "titulo": "e"},
            ],
            "metas": [
                {"id": "m1", "titulo": "Correr 3x", "tipo": "habito", "status": "ativa"},
                {"id": "m2", "titulo": "Ler", "tipo": "habito", "status": "ativa"},
            ],
            "checkins": [
                {"meta_id": "m1", "data": "2026-04-21"},
                {"meta_id": "m1", "data": "2026-04-23"},
                {"meta_id": "m1", "data": "2026-04-25"},
                {"meta_id": "m2", "data": "2026-04-22"},
            ],
            "notas": [{"id": "n1"}, {"id": "n2"}],
            "focus_sessions": [
                {"duration_minutes": 30}, {"duration_minutes": 45}
            ],
        }
        agg = _aggregate(window)
        assert agg["tasks_completed"] == 2
        # pendente + em_progresso both count as "pending".
        assert agg["tasks_pending"] == 2
        assert agg["tasks_cancelled"] == 1
        assert agg["focus_minutes"] == 75
        assert agg["notas_count"] == 2
        # m1 has 3 check-ins → first in the streak list.
        assert agg["habit_streaks"][0] == ("Correr 3x", 3)
        assert agg["habit_streaks"][1] == ("Ler", 1)

    def test_unknown_meta_id_falls_back_to_default_label(self):
        from app.services.weekly_review_service import _aggregate
        agg = _aggregate({
            "tarefas": [],
            "metas": [],
            "checkins": [{"meta_id": "missing", "data": "2026-04-22"}],
            "notas": [],
            "focus_sessions": [],
        })
        assert agg["habit_streaks"][0] == ("Hábito sem nome", 1)


class TestBuildReview:
    @pytest.mark.asyncio
    async def test_assembles_digest_and_summary(self):
        from app.services import weekly_review_service

        async def _fake_fetch(db, *, user_id, period_days):
            return {
                "tarefas": [{"status": "concluida", "titulo": "x"}],
                "metas": [{"id": "m1", "titulo": "Correr", "tipo": "habito", "status": "ativa"}],
                "checkins": [{"meta_id": "m1", "data": "2026-04-22"}],
                "notas": [],
                "focus_sessions": [{"duration_minutes": 60}],
            }

        with patch(
            "app.services.weekly_review_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.weekly_review_service.chat_completion",
            new_callable=AsyncMock,
            return_value="Panorama.\n\nObservações.\n\nRecomendação.",
        ):
            digest, summary = await weekly_review_service.build_review(
                db=object(), user_id="u1", user_label="Ana", period_days=7
            )
        assert "Ana" in digest.subject
        assert "Panorama." in digest.html
        assert summary["tasks_completed"] == 1
        assert summary["focus_minutes"] == 60
        assert summary["habit_streaks"][0] == ("Correr", 1)

    @pytest.mark.asyncio
    async def test_llm_failure_uses_template_fallback(self):
        from app.services import weekly_review_service

        async def _fake_fetch(db, *, user_id, period_days):
            return {
                "tarefas": [],
                "metas": [],
                "checkins": [],
                "notas": [],
                "focus_sessions": [],
            }

        with patch(
            "app.services.weekly_review_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.weekly_review_service.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            _, summary = await weekly_review_service.build_review(
                db=object(), user_id="u1"
            )
        assert "LLM indisponível" in summary["narrative"]


class TestSendWeeklyReview:
    @pytest.mark.asyncio
    async def test_passes_through_send_digest_result(self):
        from app.services import weekly_review_service

        async def _fake_fetch(db, *, user_id, period_days):
            return {
                "tarefas": [], "metas": [], "checkins": [], "notas": [], "focus_sessions": [],
            }

        with patch(
            "app.services.weekly_review_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.weekly_review_service.chat_completion",
            new_callable=AsyncMock,
            return_value="x",
        ), patch(
            "app.services.weekly_review_service.send_digest",
            new_callable=AsyncMock,
            return_value=DigestSendResult(sent=True, external_id="abc", subject="x"),
        ):
            result = await weekly_review_service.send_weekly_review(
                db=object(), user_id="u1", recipient="u@x"
            )
        assert result["sent"] is True
        assert result["external_id"] == "abc"
        assert "summary" in result
