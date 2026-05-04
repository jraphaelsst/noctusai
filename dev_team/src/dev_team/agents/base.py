"""Shared scaffolding for every specialist agent.

Provides:
    AgentName  — Literal type for the 11 role names + "leader".
    load_charter(name)   -> str   read the role's charter markdown.
    load_shared_charter() -> str   read the universal layer-1 charter.
    build_agent(name, *, config, tools=None) -> Agent
        — generic factory used by every specialist module.

The actual specialist factories (`build_pm`, `build_backend_engineer`, …)
live in sibling modules and are thin wrappers over `build_agent` that
pass the role name + the tools the role is allowed to call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

AgentName = Literal[
    "leader",
    "product_manager",
    "ux_designer",
    "solution_architect",
    "backend_engineer",
    "frontend_engineer",
    "devops_engineer",
    "security_engineer",
    "qa_engineer",
    "code_reviewer",
    "technical_writer",
]

CHARTER_DIR = Path(__file__).resolve().parent.parent / "charters"
SHARED_CHARTER_FILE = CHARTER_DIR / "shared.md"


def load_charter(name: AgentName) -> str:
    """Return the role's charter markdown body.

    Raises FileNotFoundError if the charter file is missing — never silently
    return empty string (per `feedback_no_silent_errors`).
    """
    path = CHARTER_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"charter not found for role {name!r} at {path} — "
            "expected one of the 12 markdown files in dev_team/src/dev_team/charters/."
        )
    return path.read_text(encoding="utf-8")


def load_shared_charter() -> str:
    """Return the layer-1 shared charter body."""
    if not SHARED_CHARTER_FILE.exists():
        raise FileNotFoundError(
            f"shared charter not found at {SHARED_CHARTER_FILE} — "
            "every agent depends on this; B2 charters engineer must ship it."
        )
    return SHARED_CHARTER_FILE.read_text(encoding="utf-8")


def compose_instructions(name: AgentName) -> str:
    """Layer-1 shared + Layer-2 role, joined into one instructions string.

    Per the design at design-reference.md §4 — ~1.5K shared + ~1-2K role
    = ~3K tokens cached per agent.
    """
    return f"{load_shared_charter()}\n\n---\n\n{load_charter(name)}"


def build_agent(
    name: AgentName,
    *,
    config: Mapping[str, Any],
    tools: Iterable[Any] | None = None,
):
    """Generic agno Agent factory.

    Parameters
    ----------
    name
        Role name; selects the charter + tool allowlist + model.
    config
        Loaded YAML config (see :mod:`dev_team.configs`). Selects the
        provider + model id for this role.
    tools
        Iterable of tool callables / agno-tool objects. If None, resolve
        from :func:`dev_team.tools.allowlists.tools_for`.

    Returns
    -------
    agno.agent.Agent

    Notes
    -----
    Imports from agno are LOCAL so a missing API key (or even a missing
    agno install) doesn't blow up `import dev_team`. The smoke test
    exercises this path with mocked agno classes.
    """
    from agno.agent import Agent  # local import keeps top-level cheap
    from agno.models.anthropic import Claude

    role_config = config.get("agents", {}).get(name)
    if role_config is None:
        raise KeyError(
            f"no model assignment for role {name!r} in the loaded config — "
            f"check dev_team/src/dev_team/configs/<config>.yaml under `agents:`"
        )

    provider = role_config.get("provider", "anthropic")
    model_id = role_config["model"]

    if provider != "anthropic":
        raise NotImplementedError(
            f"provider {provider!r} not wired yet; current default is anthropic. "
            "Codex / Gemini configs ship as commented templates — wire the "
            "provider class here when activating a non-Anthropic eval."
        )

    if tools is None:
        from dev_team.tools.allowlists import tools_for

        tools = tools_for(name)

    return Agent(
        name=name,
        model=Claude(id=model_id),
        instructions=compose_instructions(name),
        tools=list(tools),
    )


__all__ = [
    "AgentName",
    "CHARTER_DIR",
    "SHARED_CHARTER_FILE",
    "load_charter",
    "load_shared_charter",
    "compose_instructions",
    "build_agent",
]
