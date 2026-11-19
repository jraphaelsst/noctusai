"""Tool registry for the ElevenLabs connector MCP (`elevenlabs.<service>.<action>`).

LEAF_MODULES: `account` (user.usage, model.list), `voices` (voice.list/get/
clone_instant/delete), `tts` (tts.synthesize). All talk to the API through
the `elevenlabs.api` seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import account, tts, voices

LEAF_MODULES = (account, tts, voices)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)

__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
