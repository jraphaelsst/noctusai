"""The agent runtime builds its onboarding tool group without a channel in hand (prod 500, 2026-11-28).

``get_sw_settings`` takes the channel bound to who is acting (``SwCanal.como(org, ator)``), so the runtime cannot
resolve it at build time: the onboarding factory binds it per turn, to the turn's org and requester, the same
binding the onboarding router uses (``canal.como(ctx.org_id, ctx.user_id)``)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.onboarding.fabrica import make_onboarding_tools_factory
from app.onboarding.sw_settings import FakeSwSettings
from app.runtime.types import TurnContext


def test_the_runtime_builds_the_onboarding_factory():
    from app.config import settings
    from app.runtime import make_onboarding_tools_factory as runtime_factory

    assert callable(runtime_factory(settings))


def test_the_channel_is_bound_per_turn_to_the_turn_org_and_requester():
    chamadas: list[tuple] = []

    def sw_fn(org_id, ator):
        chamadas.append((org_id, ator))
        return FakeSwSettings()

    factory = make_onboarding_tools_factory(
        store=object(), messages=object(), definitions=object(), grants=object(), sw_fn=sw_fn, config_fn=dict,
    )
    assert chamadas == []  # nothing is resolved when the runtime is built
    ctx = TurnContext(org_id=uuid4(), conversation_id=uuid4(), requested_by=uuid4(), instance_id="i", sdk_session_id=None)
    assert factory(SimpleNamespace(ferramentas_grupo=()), ctx) is not None
    assert chamadas == [(ctx.org_id, ctx.requested_by)]
