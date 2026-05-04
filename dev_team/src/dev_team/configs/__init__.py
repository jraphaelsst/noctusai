"""dev_team configuration loader — provider-agnostic YAML.

Public surface (contract):
    load_config(name: str = "default") -> dict
    list_configs() -> list[str]
    save_config(name: str, content: dict) -> None      # for the API/dashboard

Configs live as YAML at ``dev_team/src/dev_team/configs/<name>.yaml``.
Schema (per design-reference.md §9):

    agents:
      <role_name>:
        provider: anthropic
        model: claude-opus-4-7
    eval:
      sample_tasks: [...]    # optional — for the eval harness

Stub behavior (until engineer ships loader.py): returns a minimal
default config so the team factory can stub-instantiate without
crashing.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover — flips to real impl when engineer ships
    from dev_team.configs.loader import (  # type: ignore
        list_configs,
        load_config,
        save_config,
    )
except ImportError:

    def load_config(name: str = "default") -> dict[str, Any]:  # type: ignore[no-redef]
        """Stub — returns a minimal valid config until D engineer ships."""
        opus = {"provider": "anthropic", "model": "claude-opus-4-7"}
        sonnet = {"provider": "anthropic", "model": "claude-sonnet-4-6"}
        return {
            "agents": {
                "leader": opus,
                "product_manager": opus,
                "ux_designer": sonnet,
                "solution_architect": opus,
                "backend_engineer": sonnet,
                "frontend_engineer": sonnet,
                "devops_engineer": sonnet,
                "security_engineer": opus,
                "qa_engineer": sonnet,
                "code_reviewer": opus,
                "technical_writer": sonnet,
            }
        }

    def list_configs() -> list[str]:  # type: ignore[no-redef]
        return ["default"]

    def save_config(name: str, content: dict[str, Any]) -> None:  # type: ignore[no-redef]
        raise NotImplementedError(
            "save_config not wired yet — D engineer ships configs/loader.py"
        )


__all__ = ["load_config", "list_configs", "save_config"]
