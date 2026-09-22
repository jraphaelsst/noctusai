"""A studio turn must never depend on Julia-only config (formerly
remediation class ``studio-runtime-julia-coupling``, now resolved).

The approval signing key, the academia API client (+ its URL) and
``JULIA_AGENT_ID`` are the inputs of an ``academia``-toolset turn only.
``get_agent_runtime`` used to resolve them eagerly, so a missing value
refused EVERY turn — studio chats and eval runs included. They now resolve
through :func:`app.runtime.make_academia_launch_provider`, called by the
runtime only when an academia turn launches, and still fail closed there
with the original errors. Everything here is composed through constructors
(DI) — no patching of our own code; env vars are the external boundary.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

from noctusai_lib.config.deploy_config import MissingProdConfigError
from noctusai_lib.security.app_config import FakeAppConfigStore

from app.credentials.resolver import (
    CredentialResolver,
    require_resolved_prod_config,
    require_resolved_runtime_config,
)
from app.runtime import build_julia_spec, make_academia_launch_provider
from app.runtime.academia_api import FakeAcademiaApi, HttpAcademiaApi
from app.runtime.claude_runtime import AcademiaLaunchConfig, ClaudeAgentSdkRuntime
from app.runtime.slots import FakeSlotPool
from app.stores.approvals import FakeApprovalStore
from app.stores.transcripts import FakeTranscriptStore
from tests.credentials.conftest import ANTHROPIC, OLD_ACADEMIA, make_settings
from tests.runtime.test_run_turn_slots import (
    _assistant,
    _broker,
    _ctx,
    _result,
    _ScriptedTransport,
    _slot,
)
from tests.studio.rt.test_launch_options import _studio_spec

_ACADEMIA_URL_ENV = "PRODUCT_URL_ACADEMIA_DE_RECICLAGEM"
_JULIA_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def no_academia_url(monkeypatch):
    """No way to resolve academia's URL (env is the external boundary)."""
    monkeypatch.delenv(_ACADEMIA_URL_ENV, raising=False)
    monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)


def _resolver(**settings) -> CredentialResolver:
    return CredentialResolver(FakeAppConfigStore(), make_settings(anthropic_api_key=ANTHROPIC, **settings))


def _julia_spec():
    return build_julia_spec(
        {"nome": "Julia", "papel": "Assistente", "model": "claude-opus-5", "effort": "high"}
    )


def _runtime(*, academia_config=None, studio_tools_factory=None, **legacy) -> ClaudeAgentSdkRuntime:
    return ClaudeAgentSdkRuntime(
        plugin_path="/app/agents/julia/plugin",
        approvals=FakeApprovalStore(),
        slot_pool=FakeSlotPool(1),
        transcripts=FakeTranscriptStore(),
        transport_factory=lambda: _ScriptedTransport(
            [_assistant("resposta", session_id="s1"), _result(session_id="s1")]
        ),
        academia_config=academia_config,
        studio_tools_factory=studio_tools_factory,
        anthropic_api_key=ANTHROPIC,
        **legacy,
    )


def _studio_tools(spec, ctx):
    return {"type": "sdk", "name": "studio", "instance": object()}


# ── studio: builds + runs with no approval key and no academia URL ─────────


@pytest.mark.asyncio
async def test_studio_turn_runs_without_approval_key_or_academia_url(tmp_path, no_academia_url):
    resolver = _resolver()  # anthropic only: no ring, no academia token, no agent id
    assert resolver.approval_signing_secret() is None
    runtime = _runtime(
        academia_config=make_academia_launch_provider(resolver),
        studio_tools_factory=_studio_tools,
    )
    events = [
        e async for e in runtime.run_turn(_studio_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    ]
    assert [e["event"] for e in events if e["event"] == "message.new"] == ["message.new"]


@pytest.mark.asyncio
async def test_studio_turn_in_deploy_context_needs_only_the_anthropic_key(tmp_path, no_academia_url, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")  # external deploy signal
    resolver = _resolver()
    require_resolved_runtime_config(resolver)  # the per-turn guard passes
    runtime = _runtime(
        academia_config=make_academia_launch_provider(resolver),
        studio_tools_factory=_studio_tools,
    )
    events = [
        e async for e in runtime.run_turn(_studio_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    ]
    assert any(e["event"] == "message.new" for e in events)
    # The full four-key view is unchanged (Julia's completeness check).
    with pytest.raises(MissingProdConfigError) as exc:
        require_resolved_prod_config(resolver)
    assert exc.value.missing_keys == ["APPROVAL_ASSERTION_SECRETS", "ACADEMIA_API_TOKEN", "JULIA_AGENT_ID"]


def test_runtime_guard_still_refuses_a_deploy_without_the_anthropic_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    resolver = CredentialResolver(FakeAppConfigStore(), make_settings())
    with pytest.raises(MissingProdConfigError) as exc:
        require_resolved_runtime_config(resolver)
    assert exc.value.missing_keys == ["ANTHROPIC_API_KEY"]


# ── academia: still fails closed, with the original errors ────────────────


@pytest.mark.asyncio
async def test_academia_turn_without_approval_key_refuses(tmp_path, no_academia_url):
    runtime = _runtime(academia_config=make_academia_launch_provider(_resolver()))
    agen = runtime.run_turn(_julia_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    with pytest.raises(RuntimeError, match=r"no active approval assertion key \(contract §D\)"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_academia_turn_without_academia_url_refuses(tmp_path, no_academia_url):
    resolver = _resolver(approval_assertion_secrets="ring-secret-one")
    assert resolver.approval_signing_secret()
    runtime = _runtime(academia_config=make_academia_launch_provider(resolver))
    agen = runtime.run_turn(_julia_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    with pytest.raises(ValueError, match="Cannot resolve URL for product .academia-de-reciclagem."):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_academia_turn_in_deploy_context_refuses_on_missing_julia_keys(tmp_path, no_academia_url, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    runtime = _runtime(academia_config=make_academia_launch_provider(_resolver()))
    agen = runtime.run_turn(_julia_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    with pytest.raises(MissingProdConfigError) as exc:
        await agen.__anext__()
    assert exc.value.missing_keys == ["APPROVAL_ASSERTION_SECRETS", "ACADEMIA_API_TOKEN", "JULIA_AGENT_ID"]


@pytest.mark.asyncio
async def test_runtime_without_any_academia_config_refuses_academia_turns(tmp_path):
    runtime = _runtime(studio_tools_factory=_studio_tools)
    agen = runtime.run_turn(_julia_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=_slot(tmp_path))
    with pytest.raises(RuntimeError, match="without academia launch config"):
        await agen.__anext__()


def test_constructor_refuses_ambiguous_or_partial_academia_inputs():
    with pytest.raises(ValueError, match="not both"):
        _runtime(academia_config=lambda: None, approval_secret="s")
    with pytest.raises(ValueError, match="together"):
        _runtime(approval_secret="s")


# ── Julia: same launch inputs as before ────────────────────────────────────


def test_provider_resolves_the_same_julia_inputs_the_factory_used(monkeypatch):
    monkeypatch.setenv(_ACADEMIA_URL_ENV, "https://academia.example.com/")
    resolver = _resolver(
        approval_assertion_secrets="ring-secret-one",
        academia_api_token=OLD_ACADEMIA,
        julia_agent_id=_JULIA_ID,
    )
    config = make_academia_launch_provider(resolver)()
    assert isinstance(config, AcademiaLaunchConfig)
    assert config.approval_secret == resolver.approval_signing_secret()
    assert config.agent_id == UUID(_JULIA_ID)
    assert isinstance(config.academia_api, HttpAcademiaApi)
    assert config.academia_api._base_url == "https://academia.example.com"
    assert config.academia_api._token == OLD_ACADEMIA


@pytest.mark.asyncio
async def test_julia_turn_is_identical_through_the_provider_and_the_value_kwargs(tmp_path):
    api, agent_id = FakeAcademiaApi(), uuid4()
    calls: list[int] = []

    def provider() -> AcademiaLaunchConfig:
        calls.append(1)
        return AcademiaLaunchConfig(academia_api=api, agent_id=agent_id, approval_secret="s3cr3t")

    by_value = _runtime(academia_api=api, agent_id=agent_id, approval_secret="s3cr3t")
    by_provider = _runtime(academia_config=provider)
    runs = []
    for i, runtime in enumerate((by_value, by_provider)):
        slot = _slot(tmp_path / str(i))
        runs.append([e async for e in runtime.run_turn(_julia_spec(), _ctx(ephemeral=True), "oi", _broker(), slot=slot)])
    assert [e["event"] for e in runs[0]] == [e["event"] for e in runs[1]]
    assert any(e["event"] == "message.new" for e in runs[1])
    assert calls == [1]  # resolved once, at the academia turn's launch
