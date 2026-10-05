"""Tool registry for the Telegram connector MCP. Names: `telegram.<service>.<action>`.

- `diagnostics` — connection_status, me (READ)
- `dialogs`     — list (READ)
- `messages`    — list, search, export (READ); send (WRITE, confirm-gated)
- `media`       — download (WRITE-to-disk, confirm-gated)

8 tools total.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import dialogs, diagnostics, media, messages

LEAF_MODULES = (diagnostics, dialogs, messages, media)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)

__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
