"""agents channel-API client seam (POST /api/channels/turns, GET /api/channels/agents/{key}/status, threads, consent...).

Promoted from social-wiring at the 2nd consumer (`assistant`). Protocol + Fake + Http + `make_agents_client`; every
error row of the contract maps to a typed exception. The org-specs surface lives in the sibling
`noctusai_lib.integrations.agents`.  KB § PATTERNS/backend/seed-fake-real-adapter.md.
"""
from __future__ import annotations

from noctusai_lib.integrations.agents_channel import client as _client
from noctusai_lib.integrations.agents_channel.client import *  # noqa: F401,F403
from noctusai_lib.integrations.agents_channel.client import __all__ as _all
from noctusai_lib.integrations.agents_channel.client import _mensagem_wire  # noqa: F401  (SW tests pin the wire shape)

__all__ = list(_all)
