"""``build_launch_options`` — asserts every §E.5/§E.11 field WITHOUT
spawning the CLI, plus the allowed_tools/escrita-shadow regression guard
(the contract defect flagged in ``app/runtime/claude_runtime.py``)."""
from uuid import uuid4

from app.runtime import gate
from app.runtime.academia_api import FakeAcademiaApi
from app.runtime.claude_runtime import (
    BASE_TOOLS,
    DISALLOWED_TOOLS,
    _HANDOFF_APPEND_FILENAME,
    build_launch_options,
)
from app.runtime.slots import FakeSlotPool
from app.runtime.transcript_mirror import ConversationTranscriptMirror
from app.runtime.types import AgentSpec, TurnContext
from app.stores.approvals import FakeApprovalStore
from app.stores.transcripts import FakeTranscriptStore


def _spec(**overrides) -> AgentSpec:
    defaults = dict(
        key="julia",
        model="claude-sonnet-5",
        effort="medium",
        prompt_append="be helpful",
        skills=("ar-capturar",),
        tools=tuple(gate.LEITURA) + tuple(gate.ESCRITA),
        max_turns=40,
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def _ctx(**overrides) -> TurnContext:
    defaults = dict(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id="inst-1",
        sdk_session_id=None,
    )
    defaults.update(overrides)
    return TurnContext(**defaults)


def _slot(**overrides):
    """A real, leased :class:`~app.runtime.slots.TurnSlot` from a
    single-capacity :class:`~app.runtime.slots.FakeSlotPool` — same
    convention ``tests/runtime/test_slots.py`` uses; this factory just
    saves each test the boilerplate."""
    slot = FakeSlotPool(1).try_reserve()
    assert slot is not None
    for name, value in overrides.items():
        setattr(slot, name, value)
    return slot


def _mirror(**overrides) -> ConversationTranscriptMirror:
    defaults = dict(
        store=FakeTranscriptStore(),
        org_id=uuid4(),
        conversation_id=uuid4(),
        expected_session_id=None,
    )
    defaults.update(overrides)
    return ConversationTranscriptMirror(**defaults)


async def _stub_can_use_tool(name, args, context):
    return None


def _build(**overrides):
    kwargs = dict(
        spec=_spec(),
        ctx=_ctx(),
        academia_api=FakeAcademiaApi(),
        agent_id=uuid4(),
        approval_secret="s3cr3t",
        can_use_tool=_stub_can_use_tool,
        approvals=FakeApprovalStore(),
        slot=_slot(),
        mirror=_mirror(),
        resume=None,
        plugin_path="/app/agents/julia/plugin",
    )
    kwargs.update(overrides)
    return build_launch_options(**kwargs)


class TestBuildLaunchOptions:
    def test_cli_path_is_the_wrapper(self):
        opts = _build()
        assert opts.cli_path == "/app/bin/julia-cli-exec"

    def test_cli_path_is_overridable_for_tests(self):
        opts = _build(cli_path="/tmp/fake-cli")
        assert opts.cli_path == "/tmp/fake-cli"

    def test_base_tools_is_websearch_and_skill_only(self):
        opts = _build()
        assert opts.tools == list(BASE_TOOLS)
        assert opts.tools == ["WebSearch", "Skill"]

    def test_setting_sources_is_empty(self):
        assert _build().setting_sources == []

    def test_system_prompt_is_preset_claude_code_with_no_append_key(self):
        """Contract §E.11 "Launch options": `system_prompt={"type":"preset",
        "preset":"claude_code"}` with NO `append` — the persona moves to
        the slot's own handoff file, never argv nor the system prompt."""
        opts = _build(spec=_spec(prompt_append="MY PROMPT"))
        assert opts.system_prompt == {"type": "preset", "preset": "claude_code"}
        assert "append" not in opts.system_prompt

    def test_plugins_is_one_local_plugin_at_the_given_path(self):
        opts = _build(plugin_path="/app/agents/julia/plugin")
        assert opts.plugins == [{"type": "local", "path": "/app/agents/julia/plugin"}]

    def test_skills_is_passed_through_from_spec(self):
        opts = _build(spec=_spec(skills=("ar-capturar", "ar-decisao")))
        assert opts.skills == ["ar-capturar", "ar-decisao"]

    def test_mcp_servers_has_exactly_one_academia_server(self):
        opts = _build()
        assert set(opts.mcp_servers.keys()) == {"academia"}

    def test_strict_mcp_config_is_true(self):
        assert _build().strict_mcp_config is True

    def test_disallowed_tools_is_every_dangerous_builtin(self):
        opts = _build()
        assert set(opts.disallowed_tools) == set(DISALLOWED_TOOLS)
        assert "Bash" in opts.disallowed_tools
        assert "Write" in opts.disallowed_tools
        # No MCP academia name belongs in the built-in disallow list.
        assert not any(name.startswith("mcp__") for name in opts.disallowed_tools)

    def test_can_use_tool_is_threaded_through_verbatim(self):
        opts = _build(can_use_tool=_stub_can_use_tool)
        assert opts.can_use_tool is _stub_can_use_tool

    def test_env_pins_the_slot_config_dir(self):
        slot = _slot()
        opts = _build(slot=slot)
        assert opts.env == {"CLAUDE_CONFIG_DIR": slot.config_dir}

    def test_resolved_anthropic_key_reaches_only_the_wrapper_env(self):
        """The key resolves DB-first now (Credenciais page); it is handed to
        the `env -i` wrapper through `options.env` — and nothing else is
        (contract §E.5: no other control-plane secret in the spawn env)."""
        slot = _slot()
        opts = _build(slot=slot, anthropic_api_key="sk-ant-api03-db-value")
        assert opts.env == {
            "CLAUDE_CONFIG_DIR": slot.config_dir,
            "ANTHROPIC_API_KEY": "sk-ant-api03-db-value",
        }
        assert "s3cr3t" not in repr(opts.env)  # the approval key never rides along

    def test_user_is_the_slot_user_name(self):
        slot = _slot()
        opts = _build(slot=slot)
        assert opts.user == slot.user_name

    def test_extra_args_points_at_the_slot_handoff_append_file(self):
        slot = _slot()
        opts = _build(slot=slot)
        assert opts.extra_args == {
            "append-system-prompt-file": f"{slot.handoff_dir}/{_HANDOFF_APPEND_FILENAME}"
        }

    def test_persona_text_never_appears_in_system_prompt_or_extra_args(self):
        """Regression guard: `/proc/<pid>/cmdline` is readable by every
        uid, so the persona must never reach argv nor `system_prompt`."""
        opts = _build(spec=_spec(prompt_append="SEKRIT PERSONA TEXT"))
        assert "SEKRIT PERSONA TEXT" not in str(opts.system_prompt)
        assert "SEKRIT PERSONA TEXT" not in str(opts.extra_args)

    def test_session_store_is_the_given_mirror(self):
        mirror = _mirror()
        opts = _build(mirror=mirror)
        assert opts.session_store is mirror

    def test_session_store_flush_is_batched(self):
        assert _build().session_store_flush == "batched"

    def test_include_partial_messages_is_true(self):
        assert _build().include_partial_messages is True

    def test_max_turns_comes_from_spec(self):
        opts = _build(spec=_spec(max_turns=7))
        assert opts.max_turns == 7

    def test_resume_is_threaded_through_from_the_resume_param(self):
        """Contract §E.11: `resume` is never a bare `ctx.sdk_session_id`
        passthrough — it is the caller's own transcript-usability
        decision, threaded through verbatim by this factory."""
        opts = _build(resume="sess-123")
        assert opts.resume == "sess-123"

        opts_none = _build(resume=None)
        assert opts_none.resume is None

    def test_model_comes_from_spec(self):
        opts = _build(spec=_spec(model="claude-opus-5"))
        assert opts.model == "claude-opus-5"


class TestAllowedToolsNeverShadowsTheGate:
    """Regression guard for the flagged contract defect: an ``allowed_tools``
    entry auto-approves BEFORE ``can_use_tool`` runs (verified live against
    the installed SDK — ``claude_agent_sdk/types.py::_whole_tool_allowed``).
    Every ESCRITA name must therefore fall through to ``can_use_tool``."""

    def test_no_escrita_tool_is_in_allowed_tools(self):
        opts = _build()
        leaked = set(opts.allowed_tools) & set(gate.ESCRITA)
        assert leaked == set(), f"escrita tools auto-approved, bypassing the gate: {leaked}"

    def test_every_leitura_academia_tool_is_in_allowed_tools(self):
        opts = _build()
        academia_leitura = {n for n in gate.LEITURA if n.startswith("mcp__academia__")}
        assert academia_leitura <= set(opts.allowed_tools)

    def test_base_builtins_are_in_allowed_tools(self):
        opts = _build()
        assert "WebSearch" in opts.allowed_tools
        assert "Skill" in opts.allowed_tools

    def test_allowed_tools_has_no_duplicates(self):
        opts = _build()
        assert len(opts.allowed_tools) == len(set(opts.allowed_tools))
