"""``noctus.team.configure`` — patch an agent's model / provider.

Wraps :func:`dev_team.mcp_facade.set_agent_config`. Loads the named YAML
config, patches ``agents.<name>.{model, provider}`` if provided, saves,
and returns the resulting config dict so callers can verify the change
landed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConfigureInput(BaseModel):
    name: str = Field(
        description=(
            "Agent role name to patch (e.g. 'leader', 'backend_engineer', "
            "'code_reviewer'). Matches the keys under `agents:` in the YAML."
        )
    )
    model: str | None = Field(
        default=None,
        description=(
            "Optional new model id (e.g. 'claude-opus-4-7', 'claude-sonnet-4-6'). "
            "When None, the existing model is left untouched."
        ),
    )
    provider: str | None = Field(
        default=None,
        description=(
            "Optional new provider (e.g. 'anthropic', 'openai'). When None, "
            "the existing provider is left untouched."
        ),
    )
    config_name: str = Field(
        default="default",
        description=(
            "Named YAML config to mutate. Defaults to 'default' "
            "(dev_team/src/dev_team/configs/default.yaml)."
        ),
    )


class ConfigureOutput(BaseModel):
    config: dict[str, Any] = Field(
        description=(
            "Resulting config dict after the patch — passthrough from "
            "set_agent_config. Top-level keys: agents (dict of role -> "
            "{provider, model, ...}), eval (optional)."
        )
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.configure",
        description=(
            "Patch an agno dev-team agent's model and/or provider in a named "
            "YAML config. Loads -> patches -> saves -> returns the new config. "
            "Use to swap an agent (e.g. Leader: Opus -> Codex) without "
            "code changes. Note: save_config is currently a stub until "
            "engineer D ships configs/loader.py."
        ),
    )
    def _handler(payload: ConfigureInput) -> ConfigureOutput:
        from dev_team.mcp_facade import set_agent_config

        cfg = set_agent_config(
            name=payload.name,
            model=payload.model,
            provider=payload.provider,
            config_name=payload.config_name,
        )
        return ConfigureOutput(config=cfg)
