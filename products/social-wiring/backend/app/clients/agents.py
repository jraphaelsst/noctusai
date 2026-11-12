"""Thin re-export: the agents channel-API client lives in the seed (`noctusai_lib.integrations.agents_channel`).

Kept so social-wiring's importers keep one stable path; no logic here.
"""
from __future__ import annotations

from noctusai_lib.integrations.agents_channel import *  # noqa: F401,F403
from noctusai_lib.integrations.agents_channel import __all__  # noqa: F401
from noctusai_lib.integrations.agents_channel import _mensagem_wire  # noqa: F401
