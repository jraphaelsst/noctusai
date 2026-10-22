"""Legacy channel agent keys.

NOC-REMEDIATE[drop-lead-imob-alias]: the SDR agent was keyed ``lead-imob`` before 2026-10-19. social-wiring (and any
token minted before the rename) still sends the old key for one release; every channel/token entry point maps it
onto the current key through :func:`canonical_channel_agent_key`. This is the ONLY agent-key knowledge left in the
code; remove it together with the social-wiring side -- 2026-10-22.
"""
from __future__ import annotations

__all__ = ["canonical_channel_agent_key"]

_LEGACY_KEY_ALIASES = {"lead-imob": "julia"}


def canonical_channel_agent_key(agent_key: str) -> str:
    """The current key for ``agent_key`` (``lead-imob`` is the pre-rename alias)."""
    return _LEGACY_KEY_ALIASES.get(agent_key, agent_key)
