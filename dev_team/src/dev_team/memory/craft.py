"""Per-agent craft memory — terse craft notes per specialist.

Per design-reference §5.2: each agent owns its own ``<agent>.md``
under ``store/agents/<agent>/``. Cross-agent reads are explicitly
opt-in (not implemented in v1; agents read only their own).

The :class:`MemoryStore` from :mod:`dev_team.memory.shared` delegates
``read("self", agent_name)`` / ``write("self", agent_name, body)``
to :func:`read_craft` / :func:`append_craft` here.
"""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.primitives.timeutil import now_utc

# Defaults to the same on-disk root as the project memory; overridden
# by :func:`set_store_root` (called by ``shared.set_store_root`` so
# both halves stay in sync).
_DEFAULT_STORE_ROOT = Path(__file__).resolve().parent / "store"
_store_root: Path = _DEFAULT_STORE_ROOT


def set_store_root(path: Path | str) -> None:
    """Override the on-disk store root (mirrors shared.set_store_root)."""
    global _store_root
    _store_root = Path(path)


def get_store_root() -> Path:
    return _store_root


def _agent_dir(agent: str) -> Path:
    if not agent:
        raise ValueError("agent name is required for craft memory")
    path = _store_root / "agents" / agent
    path.mkdir(parents=True, exist_ok=True)
    return path


def _craft_path(agent: str) -> Path:
    return _agent_dir(agent) / f"{agent}.md"


def read_craft(agent: str) -> str:
    """Return the agent's craft markdown body (empty string if none)."""
    path = _craft_path(agent)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def append_craft(agent: str, body: str) -> None:
    """Append a timestamped craft note to the agent's markdown."""
    path = _craft_path(agent)
    ts = now_utc().isoformat()
    with path.open("a", encoding="utf-8") as fh:
        if path.stat().st_size == 0:
            fh.write(f"# {agent} craft notes\n")
        fh.write(f"\n## {ts}\n\n{body}")
        if not body.endswith("\n"):
            fh.write("\n")


__all__ = ["read_craft", "append_craft", "set_store_root", "get_store_root"]
