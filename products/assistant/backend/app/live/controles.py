"""The agent's on/off + allow-list, read from `agents` -- ONE adapter, so the wire field names are one edit.

`agents` owns both: the agent's mode (`ligado | drenando | desligado`) and the list of numbers it may answer. This
module never caches and never decides a default: if the controls cannot be read, or the allow-list field is not there at
all (an older agents build), the answer is UNREADABLE and the caller fails CLOSED (no send)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from noctusai_lib.integrations.agents_channel import AgentsClient

#: The ControleInfo attribute that carries the allow-list (numbers, any format). ONE edit if agents names it differently.
CAMPO_LISTA = "contatos_permitidos"
#: Modes of `ControleInfo.modo` under which the agent answers new messages.
MODOS_LIGADO = ("ligado",)


class ControleIlegivel(RuntimeError):
    """The agent's controls could not be read (transport error, or a field the guard needs is absent)."""


@dataclass(frozen=True)
class Controles:
    ligado: bool
    numeros_permitidos: tuple[str, ...]  # empty = every number


def interpretar(info: Any) -> Controles:
    modo = getattr(info, "modo", None)
    if not isinstance(modo, str):
        raise ControleIlegivel("controles sem `modo`")
    lista: Optional[Any] = getattr(info, CAMPO_LISTA, None)
    if lista is None:
        raise ControleIlegivel(f"controles sem `{CAMPO_LISTA}`")
    if isinstance(lista, (str, bytes)) or not hasattr(lista, "__iter__"):
        raise ControleIlegivel(f"`{CAMPO_LISTA}` com formato inesperado")
    return Controles(ligado=modo in MODOS_LIGADO, numeros_permitidos=tuple(str(x) for x in lista))


async def ler_controles(client: AgentsClient, agent_key: str) -> Controles:
    """Fresh read (never cached). Any failure is `ControleIlegivel`."""
    try:
        return interpretar(await client.controle(agent_key))
    except ControleIlegivel:
        raise
    except Exception as exc:  # noqa: BLE001 - typed agents errors + transport: all mean "cannot verify" => closed
        raise ControleIlegivel(type(exc).__name__) from exc
