"""Studio branch of ``build_launch_options`` + the studio ``can_use_tool``
(Agent Studio §A5/§E3, security review of wave 1). Julia's branch is pinned
by the untouched ``tests/runtime/test_claude_runtime.py``."""
from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

from app.runtime import build_julia_spec
from app.runtime.academia_api import FakeAcademiaApi
from app.runtime.broker import StoreApprovalBroker
from app.runtime.claude_runtime import (
    DISALLOWED_TOOLS,
    STUDIO_DISALLOWED_TOOLS,
    ClaudeAgentSdkRuntime,
    _HANDOFF_APPEND_FILENAME,
    _TurnDriver,
    build_launch_options,
)
from app.runtime.slots import FakeSlotPool
from app.runtime.types import AgentSpec, TurnContext
from app.stores.approvals import FakeApprovalStore
from app.stores.errors import NotFound
from app.stores.transcripts import FakeTranscriptStore
from app.studio.tools import build_studio_tools, studio_allowed_tools
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from tests.runtime.test_run_turn_slots import _assistant, _result, _ScriptedTransport, _slot
from tests.studio.rt.fakes import FakeStudioStore
from app.stores.studio_knowledge import FakeStudioKnowledgeStore

STUDIO_FOUR = [
    "mcp__studio__abrir_skill",
    "mcp__studio__ler_arquivo_skill",
    "mcp__studio__kb_buscar",
    "mcp__studio__kb_ler",
]


def _studio_spec(**overrides) -> AgentSpec:
    text = overrides.pop("prompt_append", "# Identidade\n\nVocê é a Isa.")
    defaults = dict(
        key="isa",
        model="claude-opus-5",
        effort="high",
        prompt_append=text,
        skills=(),
        tools=tuple(STUDIO_FOUR) + ("WebSearch",),
        max_turns=12,
        prompt_mode="custom",
        toolset="studio",
        agent_id=uuid4(),
        version_id=uuid4(),
        compiled_hash="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        web_search=True,
        knowledge=True,
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def _ctx(**overrides) -> TurnContext:
    defaults = dict(org_id=uuid4(), conversation_id=uuid4(), requested_by=uuid4(), instance_id="i", sdk_session_id=None)
    defaults.update(overrides)
    return TurnContext(**defaults)


def _build(spec: AgentSpec, **overrides):
    slot = FakeSlotPool(1).try_reserve()
    kwargs = dict(
        spec=spec, ctx=_ctx(), academia_api=FakeAcademiaApi(), agent_id=uuid4(), approval_secret="s3cr3t",
        can_use_tool=None, approvals=FakeApprovalStore(), slot=slot, mirror=None, resume=None,
        plugin_path="/app/agents/julia/plugin", studio_tools={"type": "sdk", "name": "studio", "instance": object()},
        anthropic_api_key="sk-ant-test",
    )
    kwargs.update(overrides)
    return build_launch_options(**kwargs), slot


class TestStudioLaunchOptions:
    def test_no_claude_code_preset(self):
        opts, _ = _build(_studio_spec())
        # SDK `--system-prompt-file`: the compiled prompt IS the system prompt.
        assert opts.system_prompt["type"] == "file"
        assert "preset" not in repr(opts.system_prompt)

    def test_compiled_prompt_rides_the_handoff_file_never_argv(self):
        spec = _studio_spec(prompt_append="SEKRIT COMPILED PROMPT")
        opts, slot = _build(spec)
        assert opts.system_prompt == {"type": "file", "path": os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME)}
        # no append flag too — that would send the compiled prompt twice
        assert "append-system-prompt-file" not in (opts.extra_args or {})
        assert "SEKRIT" not in repr(opts.extra_args) and "SEKRIT" not in repr(opts.system_prompt)

    def test_no_plugins_no_skills_no_settings_only_the_studio_server(self):
        opts, _ = _build(_studio_spec())
        assert opts.plugins == []
        assert opts.skills == []
        assert opts.setting_sources == []
        assert set(opts.mcp_servers) == {"studio"}
        assert opts.strict_mcp_config is True
        assert opts.hooks is None

    def test_tools_is_websearch_iff_enabled(self):
        assert _build(_studio_spec(web_search=True))[0].tools == ["WebSearch"]
        assert _build(_studio_spec(web_search=False))[0].tools == []

    def test_allowed_tools_is_the_exact_allowlist(self):
        opts, _ = _build(_studio_spec())
        assert opts.allowed_tools == STUDIO_FOUR + ["WebSearch"]
        opts, _ = _build(_studio_spec(web_search=False, knowledge=False))
        assert opts.allowed_tools == STUDIO_FOUR[:2]

    def test_disallowed_is_julias_list_plus_skill_agent_todowrite(self):
        opts, _ = _build(_studio_spec())
        assert set(opts.disallowed_tools) == set(DISALLOWED_TOOLS) | {"Skill", "Agent", "TodoWrite"}
        for name in ("Skill", "WebFetch", "Task", "Agent", "Write", "Edit", "NotebookEdit", "TodoWrite", "Bash", "Read"):
            assert name in opts.disallowed_tools
        assert list(STUDIO_DISALLOWED_TOOLS) == opts.disallowed_tools

    def test_env_is_the_same_explicit_allowlist_as_julia(self):
        opts, slot = _build(_studio_spec())
        assert opts.env == {"CLAUDE_CONFIG_DIR": slot.config_dir, "ANTHROPIC_API_KEY": "sk-ant-test"}

    def test_model_effort_max_turns_from_the_spec(self):
        opts, _ = _build(_studio_spec(model="claude-sonnet-5", effort="low", max_turns=7))
        assert (opts.model, opts.effort, opts.max_turns) == ("claude-sonnet-5", "low", 7)

    def test_refuses_to_launch_without_the_studio_server(self):
        with pytest.raises(RuntimeError):
            _build(_studio_spec(), studio_tools=None)

    def test_julia_spec_keeps_the_legacy_defaults_explicitly(self):
        persona = {"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"}
        spec = build_julia_spec(persona)
        assert (spec.prompt_mode, spec.toolset, spec.compiled_hash) == ("preset_append", "academia", None)
        opts, _ = _build(spec, studio_tools=None)
        assert opts.system_prompt == {"type": "preset", "preset": "claude_code"}


def _driver(allow):
    broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=1, instance_id="i")
    return _TurnDriver(ctx=_ctx(), broker=broker, academia_api=FakeAcademiaApi(), allowlist=frozenset(allow))


class _Ctx:
    tool_use_id = "tu-1"


@pytest.mark.asyncio
class TestStudioCanUseTool:
    async def test_allowlisted_names_are_allowed(self):
        driver = _driver(studio_allowed_tools(knowledge=True, web_search=True))
        for name in STUDIO_FOUR + ["WebSearch"]:
            assert isinstance(await driver.can_use_tool(name, {}, _Ctx()), PermissionResultAllow)

    @pytest.mark.parametrize(
        "name",
        [
            "Bash", "Read", "Skill", "Write", "WebFetch", "Task", "Agent", "TodoWrite",
            "mcp__academia__kb_buscar", "mcp__academia__kb_escrever", "mcp__studio__kb_buscar_v2",
            "mcp__studio__", "mcp__other__abrir_skill", "",
        ],
    )
    async def test_everything_else_is_denied_by_default(self, name):
        driver = _driver(studio_allowed_tools(knowledge=True, web_search=True))
        assert isinstance(await driver.can_use_tool(name, {}, _Ctx()), PermissionResultDeny)

    async def test_disabled_families_are_denied_even_by_exact_name(self):
        driver = _driver(studio_allowed_tools(knowledge=False, web_search=False))
        for name in ("WebSearch", "mcp__studio__kb_buscar", "mcp__studio__kb_ler"):
            assert isinstance(await driver.can_use_tool(name, {}, _Ctx()), PermissionResultDeny)


def test_build_studio_tools_is_an_sdk_server_named_studio():
    cfg = build_studio_tools(
        org_id=uuid4(), agent_id=uuid4(), version_id=uuid4(), knowledge_enabled=True,
        definitions=FakeStudioStore(), knowledge=FakeStudioKnowledgeStore(),
    )
    assert cfg["type"] == "sdk" and cfg["name"] == "studio"


@pytest.mark.asyncio
async def test_ephemeral_studio_turn_writes_append_md_and_no_transcript(tmp_path):
    """An eval turn: the compiled text lands in append.md verbatim (so the
    stamped hash is the hash of what ran), the studio server factory gets the
    server-side spec, and nothing touches the durable transcript store."""
    spec = _studio_spec(prompt_append="COMPILED-TEXT")
    ctx = _ctx(ephemeral=True, sdk_session_id="would-be-ignored")
    transcripts = FakeTranscriptStore()
    factory_calls = []

    def tools_factory(s, c):
        factory_calls.append((s, c))
        return {"type": "sdk", "name": "studio", "instance": object()}

    slot = _slot(tmp_path)
    runtime = ClaudeAgentSdkRuntime(
        academia_api=FakeAcademiaApi(), agent_id=uuid4(), approval_secret="s", plugin_path="/p",
        approvals=FakeApprovalStore(), slot_pool=FakeSlotPool(1), transcripts=transcripts,
        transport_factory=lambda: _ScriptedTransport([_assistant("resposta", session_id="s1"), _result(session_id="s1")]),
        studio_tools_factory=tools_factory,
    )
    broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=1, instance_id="i")
    events = [e async for e in runtime.run_turn(spec, ctx, "oi", broker, slot=slot)]

    append = open(os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME), encoding="utf-8").read()
    assert append == "COMPILED-TEXT"
    assert spec.compiled_hash == "sha256:" + hashlib.sha256(append.encode("utf-8")).hexdigest()
    assert factory_calls == [(spec, ctx)]
    assert [e["event"] for e in events if e["event"] == "message.new"] == ["message.new"]
    assert not any(e["event"] == "session.resume_fallback" for e in events)
    # The durable transcript store never heard of this (row-less) conversation.
    with pytest.raises(NotFound):
        transcripts.get_estado(ctx.org_id, ctx.conversation_id)


@pytest.mark.asyncio
async def test_studio_spec_without_a_tools_factory_is_refused(tmp_path):
    runtime = ClaudeAgentSdkRuntime(
        academia_api=FakeAcademiaApi(), agent_id=uuid4(), approval_secret="s", plugin_path="/p",
        approvals=FakeApprovalStore(), slot_pool=FakeSlotPool(1), transcripts=FakeTranscriptStore(),
        transport_factory=lambda: _ScriptedTransport([]),
    )
    broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=1, instance_id="i")
    agen = runtime.run_turn(_studio_spec(), _ctx(), "oi", broker, slot=_slot(tmp_path))
    with pytest.raises(RuntimeError):
        await agen.__anext__()
