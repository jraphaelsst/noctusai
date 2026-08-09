"""Contracts for the channel-integration setup surface."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = ["ConectarCanal", "IntegracaoStatus"]


class ConectarCanal(StrictHttpModel):
    token: str = Field(min_length=1, max_length=4000)
    #: The handle/page the token authorises. Display only, not a secret.
    conta_externa: str | None = Field(default=None, max_length=200)


class IntegracaoStatus(BaseModel):
    """Connection status for one channel.

    There is deliberately NO token field. The setup screen needs to know
    whether a channel is connected, from where, and whether it needs
    reconnecting — never the credential itself.
    """

    canal: str
    conectado: bool
    #: Where the credential came from: a per-org record, an env fallback, or
    #: nothing at all. Shown so an operator knows what they are editing.
    origem: Literal["org", "env", "nenhuma"] = "nenhuma"
    conta_externa: str | None = None
    conectado_em: str | None = None
    #: Set after an auth failure — the UI turns this into "reconectar".
    ultimo_erro: str | None = None
