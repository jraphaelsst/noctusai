"""Runtime specs changed on the Configurações do agente page reach the
runtime at USE time: broker timeout, max turns, pool isolation marker."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.runtime import build_legacy_chat_spec
from app.runtime.broker import StoreApprovalBroker
from app.runtime.slots import FakeSlotPool, RealSlotPool
from app.runtime.types import TurnContext
from app.services.runtime_settings import RuntimeSettingsService
from app.stores.approvals import FakeApprovalStore
from app.stores.runtime_settings import FakeRuntimeSettingsStore

_PERSONA = SimpleNamespace(
    nome="Bia", papel="assistente", tom=None, org_display_name=None,
    project_display_name=None, system_prompt_append=None,
    model="claude-sonnet-5", effort="medium",
)


def _settings(**overrides):
    base = dict(approval_timeout_seconds=300, legacy_chat_max_turns=None, messages_rate_limit="20/minute",
                turn_timeout_seconds=600, claude_cli_slots=3)
    base.update(overrides)
    return SimpleNamespace(**base)


def _ctx() -> TurnContext:
    return TurnContext(
        org_id=uuid4(), conversation_id=uuid4(), requested_by=uuid4(),
        instance_id="inst-1", sdk_session_id=None,
    )


class TestBrokerTimeoutProvider:
    @pytest.mark.asyncio
    async def test_the_provider_is_read_per_request(self):
        current = [0.05]
        broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=lambda: current[0])

        async def _noop(record):
            return None

        decision = await broker.request(
            _ctx(), tool_name="t", tool_input={}, resumo="r", diff=None, on_created=_noop
        )
        assert decision.via == "timeout"
        current[0] = 30  # a later change must not affect a request already waiting
        assert broker._current_timeout() == 30

    def test_plain_int_still_works(self):
        assert StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=7)._current_timeout() == 7


class TestMaxTurns:
    def test_spec_yaml_is_the_default(self):
        assert build_legacy_chat_spec(_PERSONA).max_turns == 40

    def test_override_wins(self):
        assert build_legacy_chat_spec(_PERSONA, max_turns=12).max_turns == 12

    def test_service_default_follows_env_then_db(self):
        store = FakeRuntimeSettingsStore()
        service = RuntimeSettingsService(store, _settings(legacy_chat_max_turns=25), ttl_seconds=0)
        assert service.max_turns() == 25
        service.update({"max_turns": 9}, updated_by=None)
        assert service.max_turns() == 9

    def test_cache_is_invalidated_by_own_write_only(self):
        store = FakeRuntimeSettingsStore()
        clock = [0.0]
        service = RuntimeSettingsService(store, _settings(), ttl_seconds=30, clock=lambda: clock[0])
        assert service.approval_timeout_seconds() == 300
        store.put("approval_timeout_seconds", 90, updated_by=None)  # another worker writes
        assert service.approval_timeout_seconds() == 300
        clock[0] = 31
        assert service.approval_timeout_seconds() == 90

    def test_invalid_db_row_falls_back_loudly(self, caplog):
        store = FakeRuntimeSettingsStore()
        store.put("max_turns", "many", updated_by=None)
        service = RuntimeSettingsService(store, _settings(), ttl_seconds=0)
        assert service.max_turns() == 40
        assert "runtime_setting_invalid_in_db" in caplog.text

    def test_get_build_legacy_chat_spec_dep_applies_the_override(self):
        from app.dependencies import get_build_legacy_chat_spec_dep
        from app.services import runtime_settings

        service = runtime_settings.get_runtime_settings_service(None)
        service.update({"max_turns": 17}, updated_by=None)
        assert get_build_legacy_chat_spec_dep()(_PERSONA).max_turns == 17


class TestPoolIsolationMarker:
    def test_markers(self):
        assert FakeSlotPool.isolated is False
        assert RealSlotPool.isolated is True


class TestOwnerNumberFromCore:
    """074 -> core 121: the hand-off number is the platform's ONE owner number, read from core (never an agents row)."""

    def test_reads_core_and_normalizes(self):
        service = RuntimeSettingsService(
            FakeRuntimeSettingsStore(), _settings(), ttl_seconds=0, owner_number=lambda: "(11) 90000-0000")
        assert service.numero_fallback_atendimento() == "+5511900000000"

    def test_an_agents_row_is_ignored(self):
        store = FakeRuntimeSettingsStore()
        store.put("numero_fallback_atendimento", "+5511911112222", updated_by=None)  # the old agents copy
        service = RuntimeSettingsService(store, _settings(), ttl_seconds=0, owner_number=lambda: None)
        assert service.numero_fallback_atendimento() is None

    def test_no_source_means_unset(self):
        assert RuntimeSettingsService(FakeRuntimeSettingsStore(), _settings(), ttl_seconds=0).numero_fallback_atendimento() is None

    def test_core_unreadable_is_unset_and_loud_not_a_crash(self, caplog):
        def boom() -> str | None:
            raise RuntimeError("core down")

        service = RuntimeSettingsService(FakeRuntimeSettingsStore(), _settings(), ttl_seconds=0, owner_number=boom)
        assert service.numero_fallback_atendimento() is None
        assert "agents.owner_number_read_failed" in caplog.text

    def test_not_editable_here(self):
        import pytest

        from app.services.runtime_settings import RuntimeSettingsError

        service = RuntimeSettingsService(
            FakeRuntimeSettingsStore(), _settings(), ttl_seconds=0, owner_number=lambda: "+5511900000000")
        with pytest.raises(RuntimeSettingsError):
            service.update({"numero_fallback_atendimento": "+5511911112222"}, updated_by=None)
        view = {v.key: v for v in service.view()}["numero_fallback_atendimento"]
        assert (view.source, view.editable) == ("core", False)
