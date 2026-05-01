"""Unit tests for the audit-log digest service (ai-expansion Phase 9)."""
import pytest
from unittest.mock import AsyncMock, patch

from noctusai_lib.integrations.email.digest import DigestSendResult


class TestAggregate:

    def test_counts_actions_users_and_picks_high_priority(self):
        from app.services.audit_digest_service import _aggregate
        rows = [
            {"action": "user.login", "user_id": "u1"},
            {"action": "user.login", "user_id": "u1"},
            {"action": "user.login", "user_id": "u2"},
            {"action": "user.role_changed", "user_id": "u1", "resource_type": "user"},
            {"action": "license.revoked", "user_id": "u3"},
            {"action": "settings.changed", "user_id": None},
        ]
        actions, users, high = _aggregate(rows)
        action_dict = dict(actions)
        assert action_dict["user.login"] == 3
        assert action_dict["user.role_changed"] == 1
        # Top user by count is u1 with 3 events.
        assert users[0][0] == "u1"
        assert users[0][1] == 3
        # Privileged actions captured.
        high_actions = sorted(h["action"] for h in high)
        assert high_actions == ["license.revoked", "user.role_changed"]


class TestGenerateNarrative:

    @pytest.mark.asyncio
    async def test_returns_llm_text_when_available(self):
        from app.services.audit_digest_service import _generate_narrative
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="Resumo da semana...\n\nAnomalias...\n\nChecklist...",
        ):
            text = await _generate_narrative(
                org_name="Org",
                period_days=7,
                total_events=10,
                actions_by_count=[("login", 5), ("logout", 5)],
                top_users=[("u1", 5)],
                high_priority=[],
                org_id="org-1",
            )
        assert "Resumo" in text
        assert "Anomalias" in text

    @pytest.mark.asyncio
    async def test_falls_back_when_llm_unavailable(self):
        from app.services.audit_digest_service import _generate_narrative
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM not configured"),
        ):
            text = await _generate_narrative(
                org_name="Acme",
                period_days=7,
                total_events=12,
                actions_by_count=[("user.login", 10), ("user.logout", 2)],
                top_users=[],
                high_priority=[],
                org_id=None,
            )
        assert "Acme" in text
        assert "LLM indisponível" in text


class TestRender:

    def test_html_includes_org_period_actions(self):
        from app.services.audit_digest_service import _render_bodies
        html, _ = _render_bodies(
            org_name="Acme Real Estate",
            narrative="Tudo bem por aqui.\n\nNada incomum.\n\nNenhum item para revisão.",
            actions_by_count=[("user.login", 12), ("billing.subscribed", 1)],
            top_users=[("u1234567890", 5)],
            period_days=7,
            total_events=13,
        )
        assert "Acme Real Estate" in html
        assert "Últimos 7 dias" in html
        assert "user.login" in html
        assert "13 eventos" in html

    def test_text_has_three_sections(self):
        from app.services.audit_digest_service import _render_bodies
        _, text = _render_bodies(
            org_name="Acme",
            narrative="Resumo qualquer.",
            actions_by_count=[("a", 1)],
            top_users=[("u1", 1)],
            period_days=7,
            total_events=1,
        )
        assert "RESUMO" in text
        assert "AÇÕES POR VOLUME" in text
        assert "USUÁRIOS MAIS ATIVOS" in text


class TestBuildDigest:

    @pytest.mark.asyncio
    async def test_builds_subject_html_text_and_summary(self):
        from app.services import audit_digest_service

        # Mock DB hits in audit_digest_service._fetch_audit_window.
        async def _fake_fetch(db, *, org_id, period_days):
            audit = [
                {"action": "user.login", "user_id": "u1", "resource_type": "user", "resource_id": None},
                {"action": "user.login", "user_id": "u2", "resource_type": "user", "resource_id": None},
                {"action": "user.role_changed", "user_id": "u1", "resource_type": "user", "resource_id": "u9"},
            ]
            recipients = [{"id": "a1", "email": "admin@org.com", "role": "admin"}]
            org_record = {"id": org_id, "nome": "Org Test"}
            return audit, recipients, org_record

        with patch(
            "app.services.audit_digest_service._fetch_audit_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="Narrativa.",
        ):
            built = await audit_digest_service.build_digest(
                db=object(), org_id="org-1", period_days=7
            )
        assert built is not None
        digest, recipients, summary = built
        assert "Org Test" in digest.subject
        assert "Narrativa." in digest.html
        assert "Narrativa." in digest.text
        assert summary["total_events"] == 3
        assert summary["high_priority_count"] == 1
        assert summary["actions_top"][0] == ("user.login", 2)


class TestSendWeeklyAuditDigest:

    @pytest.mark.asyncio
    async def test_sends_to_each_admin_and_counts(self):
        from app.services import audit_digest_service

        async def _fake_fetch(db, *, org_id, period_days):
            return (
                [{"action": "user.login", "user_id": "u1"}],
                [
                    {"id": "a1", "email": "a@org.com", "role": "admin"},
                    {"id": "a2", "email": "b@org.com", "role": "admin"},
                ],
                {"id": org_id, "nome": "Org"},
            )

        async def _fake_send_digest(digest, *, recipient, org_id, log_prefix):
            return DigestSendResult(
                sent=True, external_id=f"id-{recipient}", subject=digest.subject
            )

        with patch(
            "app.services.audit_digest_service._fetch_audit_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="x",
        ), patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
            side_effect=_fake_send_digest,
        ):
            result = await audit_digest_service.send_weekly_audit_digest(
                db=object(), org_id="org-1", period_days=7
            )
        assert result["sent"] == 2
        assert {r["recipient"] for r in result["results"]} == {"a@org.com", "b@org.com"}

    @pytest.mark.asyncio
    async def test_dry_run_keeps_count_zero(self):
        from app.services import audit_digest_service

        async def _fake_fetch(db, *, org_id, period_days):
            return (
                [],
                [{"id": "a1", "email": "a@org.com", "role": "admin"}],
                {"id": org_id, "nome": "Org"},
            )

        async def _fake_send_digest(digest, *, recipient, org_id, log_prefix):
            return DigestSendResult(sent=False, dry_run=True, subject=digest.subject)

        with patch(
            "app.services.audit_digest_service._fetch_audit_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="x",
        ), patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
            side_effect=_fake_send_digest,
        ):
            result = await audit_digest_service.send_weekly_audit_digest(
                db=object(), org_id="org-1"
            )
        assert result["sent"] == 0
        assert result["results"][0]["dry_run"] is True

    @pytest.mark.asyncio
    async def test_skips_recipients_without_email(self):
        from app.services import audit_digest_service

        async def _fake_fetch(db, *, org_id, period_days):
            return (
                [],
                [
                    {"id": "a1", "email": None, "role": "admin"},
                    {"id": "a2", "email": "", "role": "admin"},
                    {"id": "a3", "email": "ok@org.com", "role": "admin"},
                ],
                {"id": org_id, "nome": "Org"},
            )

        send_mock = AsyncMock(return_value=DigestSendResult(sent=True, external_id="x"))
        with patch(
            "app.services.audit_digest_service._fetch_audit_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="x",
        ), patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            send_mock,
        ):
            result = await audit_digest_service.send_weekly_audit_digest(
                db=object(), org_id="org-1"
            )
        assert send_mock.call_count == 1
        assert result["sent"] == 1
