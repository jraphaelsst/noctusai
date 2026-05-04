"""dev_team configs loader — provider-agnostic YAML.

Public surface (consumed via ``dev_team.configs``):
    load_config(name: str = "default") -> dict
    list_configs() -> list[str]
    save_config(name: str, content: dict) -> None

Configs live as ``dev_team/src/dev_team/configs/<name>.yaml``. Schema:

    agents:
      <role_name>:
        provider: anthropic | openai | google
        model: <provider-specific model id>

Every config MUST have an ``agents:`` mapping with at least one entry,
and every entry MUST have ``provider`` + ``model`` as non-empty strings.
``save_config`` validates BEFORE the atomic write so a malformed dict
never lands on disk.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

CONFIGS_DIR = Path(__file__).resolve().parent


class ConfigSchemaError(ValueError):
    """Raised when a config dict fails schema validation."""


def _config_path(name: str) -> Path:
    """Resolve ``<name>`` to ``configs/<name>.yaml``.

    The lookup is intentionally strict — no walking, no fallback. If the
    caller passes ``"default"`` we return ``configs/default.yaml`` and
    nothing else.
    """
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(
            f"Invalid config name {name!r} — must be a bare slug "
            "(no slashes, no leading dots, non-empty)."
        )
    return CONFIGS_DIR / f"{name}.yaml"


def _validate_schema(content: Any, *, source: str) -> None:
    """Raise :class:`ConfigSchemaError` if ``content`` is not a valid config.

    A valid config is a mapping with an ``agents`` key holding a mapping
    of at least one agent. Each agent entry must be a mapping with
    ``provider`` and ``model`` as non-empty strings.
    """
    if not isinstance(content, dict):
        raise ConfigSchemaError(
            f"{source}: top-level must be a mapping, got {type(content).__name__}."
        )
    agents = content.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ConfigSchemaError(
            f"{source}: missing or empty 'agents:' mapping (need at least one agent)."
        )
    for agent_name, entry in agents.items():
        if not isinstance(entry, dict):
            raise ConfigSchemaError(
                f"{source}: agents.{agent_name} must be a mapping, "
                f"got {type(entry).__name__}."
            )
        provider = entry.get("provider")
        model = entry.get("model")
        if not isinstance(provider, str) or not provider.strip():
            raise ConfigSchemaError(
                f"{source}: agents.{agent_name}.provider must be a non-empty string."
            )
        if not isinstance(model, str) or not model.strip():
            raise ConfigSchemaError(
                f"{source}: agents.{agent_name}.model must be a non-empty string."
            )


def load_config(name: str = "default") -> dict[str, Any]:
    """Load + validate ``configs/<name>.yaml`` and return it as a dict.

    Raises :class:`FileNotFoundError` with a clear message if the file
    is absent, and :class:`ConfigSchemaError` if the YAML parses but
    violates the schema.
    """
    path = _config_path(name)
    if not path.exists():
        available = ", ".join(list_configs()) or "<none>"
        raise FileNotFoundError(
            f"dev_team config {name!r} not found at {path}. "
            f"Available configs: {available}."
        )
    with path.open("r", encoding="utf-8") as fh:
        content = yaml.safe_load(fh)
    if content is None:
        raise ConfigSchemaError(f"{path}: file is empty.")
    _validate_schema(content, source=str(path))
    return content


def list_configs() -> list[str]:
    """Return alphabetically-sorted slugs for every ``*.yaml`` in the dir."""
    if not CONFIGS_DIR.exists():
        return []
    return sorted(p.stem for p in CONFIGS_DIR.glob("*.yaml"))


def save_config(name: str, content: dict[str, Any]) -> None:
    """Atomically write ``content`` to ``configs/<name>.yaml`` after validation.

    Atomic via temp-file-in-same-dir + rename so a crash mid-write never
    leaves a half-written config on disk.
    """
    _validate_schema(content, source=f"save_config({name!r})")
    path = _config_path(name)
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".yaml.tmp", dir=str(CONFIGS_DIR)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(content, fh, sort_keys=False, default_flow_style=False)
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup of the temp file on failure; never mask
        # the underlying exception.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


__all__ = ["load_config", "list_configs", "save_config", "ConfigSchemaError"]
