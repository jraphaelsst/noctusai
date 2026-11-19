"""Which agents may run on the ``app`` channel (the in-product chat), declared in ONE place.

The ``app`` channel is NOT open to every agent: the turn route accepts it only for a key listed here, and refuses a listed
key on any other channel (the Diretor de Criacao has no lead, no WhatsApp line and none of Julia's machinery). A new
in-product agent is added by adding its key here, in the same change as its tests."""
from __future__ import annotations

CANAL_APP = "app"

#: The platform definitions' keys that run on the ``app`` channel. The key alone is the declared capability; it is matched
#: on the CANONICAL key, so a legacy alias cannot slip past it.
AGENTES_CANAL_APP: frozenset[str] = frozenset({"diretor-de-criacao"})


def agente_aceita_canal_app(agent_key: str) -> bool:
    return agent_key in AGENTES_CANAL_APP


__all__ = ["AGENTES_CANAL_APP", "CANAL_APP", "agente_aceita_canal_app"]
