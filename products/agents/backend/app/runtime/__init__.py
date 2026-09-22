"""The three §E.9 factories: :func:`get_agent_runtime`,
:func:`get_approval_broker`, :func:`build_julia_spec`.

Nothing in this module imports :mod:`claude_agent_sdk` at module scope —
that import happens ONLY inside :func:`get_agent_runtime`'s real-runtime
branch, so importing ``app.runtime`` (e.g. from ``app.dependencies`` or a
test that only wants :class:`~app.runtime.fake_runtime.FakeAgentRuntime`)
never requires the package to be installed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml

from app.runtime import gate
from app.runtime.broker import StoreApprovalBroker
from app.runtime.fake_runtime import FakeAgentRuntime
from app.runtime.types import AgentRuntime, AgentSpec, ApprovalBroker

__all__ = [
    "get_agent_runtime",
    "get_approval_broker",
    "build_julia_spec",
    "make_studio_tools_factory",
]

_JULIA_DIR = Path(__file__).resolve().parent.parent / "agents" / "julia"
_JULIA_PLUGIN_PATH = str(_JULIA_DIR / "plugin")

_ACADEMIA_AUD = "academia-de-reciclagem"

# Process-singleton cache for get_approval_broker — one broker per process
# (contract §E.9: "a process singleton").
_broker_singleton: ApprovalBroker | None = None


def _resolve_instance_id() -> str:
    """Best-effort STABLE per-deployment-slot identifier.

    ``expire_orphans_on_startup`` (contract §E.2 / security finding 5)
    only sweeps rows this exact value created — that is only meaningful
    if the SAME container/slot reports the SAME value across a
    crash-restart. Prefers an explicit ``AGENTS_INSTANCE_ID`` (a deploy
    can set this to a stable per-replica name), falls back to
    ``HOSTNAME`` (Docker sets this to the container id — stable within
    one container's life, but a fresh container on redeploy gets a new
    one; that's a genuinely NEW instance, so a fresh id there is
    correct, not a bug). Only when NEITHER is set does this fall back to
    a random id — flagged here because a random fallback means the
    startup sweep can never find a previous life's rows; a real deploy
    should set one of the two env vars above.
    """
    explicit = os.environ.get("AGENTS_INSTANCE_ID", "").strip()
    if explicit:
        return explicit
    hostname = os.environ.get("HOSTNAME", "").strip()
    if hostname:
        return hostname
    return uuid4().hex


def get_approval_broker(settings: Any) -> ApprovalBroker:
    """Process singleton. Backed by ``get_approval_store(settings)``
    (Fake in dev/test, Real when a Supabase service-role key is
    configured — same signal every other agents store factory uses)."""
    global _broker_singleton
    if _broker_singleton is None:
        from app.stores.approvals import get_approval_store

        from app.services.runtime_settings import get_runtime_settings_service

        store = get_approval_store(settings)
        runtime_settings = get_runtime_settings_service(settings)
        # A provider, not a number: the admin override (Configurações do
        # agente) applies to the next approval without a restart.
        _broker_singleton = StoreApprovalBroker(
            store,
            timeout_seconds=runtime_settings.approval_timeout_seconds,
            instance_id=_resolve_instance_id(),
        )
    return _broker_singleton


def get_agent_runtime(settings: Any) -> AgentRuntime:
    """``ClaudeAgentSdkRuntime`` when the Anthropic key resolves,
    ``FakeAgentRuntime`` in tests/dev. In a deploy context an unresolvable
    key (or approval signing key / ``ACADEMIA_API_TOKEN`` /
    ``JULIA_AGENT_ID``) raises — there is no silent Fake in prod (contract
    §E.9).

    Built per request (``get_agent_runtime_dep``), so every secret below is
    resolved at USE time, DB-first with env fallback
    (``app/credentials/resolver.py``) — a value changed on the Credenciais
    page reaches the next turn without a redeploy."""
    from app.credentials.resolver import get_credential_resolver, require_resolved_prod_config

    credentials = get_credential_resolver(settings)
    require_resolved_prod_config(credentials)

    anthropic_key = credentials.anthropic_api_key() or ""
    if not anthropic_key:
        return FakeAgentRuntime([])

    from app.runtime.academia_api import make_academia_api
    from app.runtime.claude_runtime import DEFAULT_CLI_PATH, ClaudeAgentSdkRuntime
    from app.runtime.slots import get_slot_pool
    from app.stores.approvals import get_approval_store
    from app.stores.transcripts import get_transcript_store
    from noctusai_lib.config.product_urls import resolve_product_url

    slot_pool = get_slot_pool(settings)
    if not slot_pool.isolated:
        # The pool was chosen before any key resolved (dev process that got
        # a key later). Never run the REAL CLI without per-slot isolation
        # (contract §E.11) — refuse loudly; a restart picks the real pool.
        raise RuntimeError(
            "Julia slot pool was created without isolation; restart the "
            "agents process after configuring the Anthropic key."
        )

    signing_secret = credentials.approval_signing_secret()
    if not signing_secret:
        raise RuntimeError("no active approval assertion key (contract §D)")
    academia_api = make_academia_api(
        base_url=resolve_product_url("academia-de-reciclagem"),
        token=credentials.academia_api_token() or "",
    )

    return ClaudeAgentSdkRuntime(
        academia_api=academia_api,
        agent_id=credentials.julia_agent_id() or _NIL_AGENT_ID,
        approval_secret=signing_secret,
        anthropic_api_key=anthropic_key,
        plugin_path=_JULIA_PLUGIN_PATH,
        # Contract §E.10 — the escrita handler (app/runtime/tools.py) needs
        # the SAME approvals store the broker decides against; both read
        # `get_approval_store(settings)`, which is stateless over the
        # shared Supabase table in every real deploy (see
        # `get_approval_broker`'s identical call, just above).
        approvals=get_approval_store(settings),
        # Contract §E.11 — both process singletons (mirrors
        # `get_approval_broker`'s shape): the SAME SlotPool leases every
        # turn this process serves, and the SAME TranscriptStore both
        # writes durable transcripts (session_store) and reads them back
        # (the resume decision), like the approval broker's store.
        slot_pool=slot_pool,
        transcripts=get_transcript_store(settings),
        approval_use_window_seconds=int(
            getattr(settings, "approval_use_window_seconds", 120) or 120
        ),
        # Config-wired (roadmap D1) — see `SeedSettings.julia_cli_path`'s
        # docstring for why this must not be a second hardcoded literal.
        cli_path=getattr(settings, "julia_cli_path", "") or DEFAULT_CLI_PATH,
        # Agent Studio §E3 — the per-turn read-only `studio` MCP server.
        studio_tools_factory=make_studio_tools_factory(settings),
    )


def make_studio_tools_factory(settings: Any):
    """``(spec, ctx) -> McpSdkServerConfig`` over the studio stores (Agent
    Studio §E3). Every id the tools use comes from the SERVER-built spec +
    the route-resolved ``TurnContext`` — never from the model."""
    from app.stores.studio_definitions import get_studio_definition_store
    from app.stores.studio_knowledge import get_studio_knowledge_store

    definitions = get_studio_definition_store(settings)
    knowledge = get_studio_knowledge_store(settings)

    def _factory(spec: AgentSpec, ctx: Any) -> Any:
        from app.studio.tools import build_studio_tools

        if spec.agent_id is None or spec.version_id is None:
            raise RuntimeError("a studio spec must carry agent_id and version_id")
        return build_studio_tools(
            org_id=ctx.org_id,
            agent_id=spec.agent_id,
            version_id=spec.version_id,
            knowledge_enabled=spec.knowledge,
            definitions=definitions,
            knowledge=knowledge,
        )

    return _factory


#: `JULIA_AGENT_ID` — the `agents.agents` row id for the `julia` key,
#: contract §D `sub`. A process-WIDE constant, not per-org: `agents` holds
#: exactly ONE `ACADEMIA_API_TOKEN` (contract §B.0) whose
#: `principal_agent_id` was set when it was minted, and the resolved value
#: must equal it exactly. `require_resolved_prod_config` refuses a deploy
#: context without it, so this visibly-fake nil UUID only ever reaches a
#: dev/test runtime.
_NIL_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")


def build_julia_spec(persona_row: Any, *, max_turns: int | None = None) -> AgentSpec:
    """Merge Julia's static spec (``agents/julia/spec.yaml`` + ``JULIA.md``)
    with the active persona row into one :class:`AgentSpec` (contract
    §E.9). ``persona_row`` is anything with the
    :class:`app.stores.personas.PersonaRecord` fields (attribute access;
    a dict-shaped row also works via ``_field``)."""

    def _field(name: str, *, required: bool = True) -> Any:
        try:
            value = getattr(persona_row, name) if hasattr(persona_row, name) else persona_row[name]
        except (KeyError, AttributeError):
            value = None
        if required and value in (None, ""):
            raise ValueError(f"persona_row is missing required field {name!r}")
        return value

    julia_md = (_JULIA_DIR / "JULIA.md").read_text(encoding="utf-8")
    spec_data = yaml.safe_load((_JULIA_DIR / "spec.yaml").read_text(encoding="utf-8")) or {}

    persona_lines = [
        "",
        "---",
        "",
        "## Seu perfil neste projeto",
        "",
        f"- **Nome de exibição:** {_field('nome')}",
        f"- **Papel:** {_field('papel')}",
    ]
    tom = _field("tom", required=False)
    if tom:
        persona_lines.append(f"- **Tom:** {tom}")
    org_display_name = _field("org_display_name", required=False)
    if org_display_name:
        persona_lines.append(f"- **Organização:** {org_display_name}")
    project_display_name = _field("project_display_name", required=False)
    if project_display_name:
        persona_lines.append(f"- **Projeto:** {project_display_name}")
    system_prompt_append = _field("system_prompt_append", required=False)
    if system_prompt_append:
        persona_lines.extend(["", system_prompt_append])

    prompt_append = julia_md + "\n" + "\n".join(persona_lines) + "\n"

    tools = tuple(gate.LEITURA) + tuple(gate.ESCRITA)

    return AgentSpec(
        key="julia",
        model=_field("model"),
        effort=_field("effort"),
        prompt_append=prompt_append,
        skills=tuple(spec_data.get("skills", [])),
        tools=tools,
        # An admin override (Configurações do agente) wins over spec.yaml.
        max_turns=int(max_turns) if max_turns else int(spec_data.get("max_turns", 40)),
        # Agent Studio §E1: Julia's defaults, stated explicitly — the
        # claude_code preset + JULIA.md appended, the academia toolset.
        prompt_mode="preset_append",
        toolset="academia",
    )
