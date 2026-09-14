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
from uuid import uuid4

import yaml

from noctusai_lib.config.deploy_config import require_prod_config

from app.runtime import gate
from app.runtime.broker import StoreApprovalBroker
from app.runtime.fake_runtime import FakeAgentRuntime
from app.runtime.types import AgentRuntime, AgentSpec, ApprovalBroker

__all__ = ["get_agent_runtime", "get_approval_broker", "build_julia_spec"]

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

        store = get_approval_store(settings)
        timeout = int(getattr(settings, "approval_timeout_seconds", 900) or 900)
        _broker_singleton = StoreApprovalBroker(
            store, timeout_seconds=timeout, instance_id=_resolve_instance_id()
        )
    return _broker_singleton


def get_agent_runtime(settings: Any) -> AgentRuntime:
    """``ClaudeAgentSdkRuntime`` when ``ANTHROPIC_API_KEY`` is configured,
    ``FakeAgentRuntime`` in tests/dev. In a deploy context an unconfigured
    key (or a missing ``APPROVAL_ASSERTION_SECRETS`` /
    ``ACADEMIA_API_TOKEN``) raises at startup — there is no silent Fake
    in prod (contract §E.9)."""
    require_prod_config(
        ["ANTHROPIC_API_KEY", "APPROVAL_ASSERTION_SECRETS", "ACADEMIA_API_TOKEN", "JULIA_AGENT_ID"]
    )

    anthropic_key = getattr(settings, "anthropic_api_key", "") or ""
    if not anthropic_key:
        return FakeAgentRuntime([])

    from app.runtime.academia_api import make_academia_api
    from app.runtime.claude_runtime import ClaudeAgentSdkRuntime
    from noctusai_lib.config.product_urls import resolve_product_url

    secrets = getattr(settings, "approval_assertion_secrets", []) or []
    academia_api = make_academia_api(
        base_url=resolve_product_url("academia-de-reciclagem"),
        token=getattr(settings, "academia_api_token", "") or "",
    )

    return ClaudeAgentSdkRuntime(
        academia_api=academia_api,
        agent_id=_julia_agent_id(settings),
        approval_secret=secrets[0],
        plugin_path=_JULIA_PLUGIN_PATH,
    )


def _julia_agent_id(settings: Any) -> Any:
    """The `agents.agents` row id for the `julia` key — contract §D `sub`.

    A process-WIDE constant, not per-org: `agents` holds exactly ONE
    `ACADEMIA_API_TOKEN` (contract §B.0 — a single product token, not
    minted per-org), and that token's `principal_agent_id` was set once
    when it was minted. `settings.julia_agent_id` must equal it exactly.
    `require_prod_config` above already refuses to start in a deploy
    context without `JULIA_AGENT_ID` set, so reaching this line with an
    empty value only happens in dev/test — the deterministic nil UUID
    there is a visibly-fake placeholder, never mistaken for a real id.
    """
    from uuid import UUID

    raw = getattr(settings, "julia_agent_id", "") or ""
    if raw:
        return UUID(raw)
    return UUID("00000000-0000-0000-0000-000000000000")


def build_julia_spec(persona_row: Any) -> AgentSpec:
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
        max_turns=int(spec_data.get("max_turns", 40)),
    )
