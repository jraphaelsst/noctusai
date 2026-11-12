"""The catalogue seam: what an agent can OFFER to a lead, behind one Protocol.

The generic tools ``oferecer_opcoes`` / ``detalhes_opcao`` / ``registrar_reacao_opcao`` never know where options
come from: they ask a :class:`CatalogoOpcoes`. The real-estate agent's catalogue (social-wiring's ``buscar_imoveis``
family) is one adapter; the synthetic catalogue of the eval world and of templates with no business is another.

NOC-REMEDIATE[catalogo-fornecedor-seed]: this Protocol + its Fake/Real/factory are an IO seam in the shape the seed
mandates (``noctusai_lib.integrations.<name>``). It lives in the product while ONE product (agents) consumes it;
at N=2 consumers it is lifted to the seed -- 2026-11-11
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

#: The catalogue a lead-event row belongs to when nothing else is said (the real-estate catalogue; migration 081).
CATALOGO_PADRAO = "imoveis_sw"


@dataclass(frozen=True)
class Busca:
    """One answer of a catalogue: the raw items as the catalogue returned them, plus the sibling facts the model must
    see next to them (``relaxado``, ``itens_nao_verificaveis``, ...: the ADAPTER's allowlist, never a pass-through)."""

    itens: tuple[Mapping[str, Any], ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class CatalogoOpcoes(Protocol):
    """A catalogue of offerable options. Every network call returns ``None`` when the catalogue is unavailable (never
    raises): the tool answers ``indisponivel`` and the turn goes on."""

    #: The key the standard's ``parametros.catalogo`` names and the lead-event rows are tagged with.
    chave: str

    def origem(self, estado: Any) -> str | None:
        """The code of the option the lead ARRIVED with (an ad's property...), from the turn's operational state;
        ``None`` = the lead has no origin option."""
        ...

    async def buscar_origem(self, org_id: UUID, codigo: str, *, interacao_id: str | None = None) -> Busca | None:
        """The origin option itself (``itens`` holds 0 or 1 item); ``None`` = the catalogue is unavailable."""
        ...

    async def buscar(
        self, org_id: UUID, *, perfil: Mapping[str, Any], excluir: Sequence[str], limite: int,
        similar_a: str | None = None, interacao_id: str | None = None,
    ) -> Busca | None:
        """Up to ``limite`` options matching the lead's computed ``perfil``, never one of ``excluir``."""
        ...

    async def detalhar(
        self, org_id: UUID, codigo: str, *, interacao_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """The raw detail of one option (``{"encontrado": False}`` when it does not exist); ``None`` = unavailable."""
        ...

    def perfil_texto(self, perfil: Mapping[str, Any]) -> str:
        """The lead's computed profile as the catalogue's search text (``chave=valor`` pairs, stable order)."""
        ...

    def opcao(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """One raw item as the generic option the model reads: ``{codigo, titulo, resumo, link?, atributos{}}``."""
        ...


def codigo_origem_do_estado(estado: Any) -> str | None:
    """The origin code of ``contexto.estado`` (``estado.origem.codigo_imovel_campanha`` -- the only origin kind the
    channel owner sends today)."""
    codigo = getattr(getattr(estado, "origem", None), "codigo_imovel_campanha", None)
    return str(codigo) if codigo else None


def perfil_como_texto(perfil: Mapping[str, Any]) -> str:
    return "; ".join(f"{k}={perfil[k]}" for k in sorted(perfil) if perfil[k] not in (None, "", [], {}))


#: Keys of a raw item that are the generic option's headline; every other scalar becomes an ``atributos`` entry.
_CABECALHO = frozenset({"codigo", "titulo", "descricao", "resumo", "link"})
#: The fields a real-estate card summarises its option with (``resumo`` is these, joined).
_RESUMO_IMOVEL = ("tipo", "bairro", "cidade")


def opcao_de_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """The generic shape of one raw catalogue item (any catalogue): ``codigo`` / ``titulo`` / ``resumo`` / ``link``
    verbatim when present, the rest of the item's scalars and lists under ``atributos``. Safety shaping (text length,
    contacts, extraction attempts) is applied by the tool, not here."""
    out: dict[str, Any] = {"codigo": str(item.get("codigo") or "").strip()}
    if item.get("titulo") is not None:
        out["titulo"] = item["titulo"]
    resumo = item.get("resumo") or item.get("descricao")
    if not resumo:
        resumo = ", ".join(str(item[k]) for k in _RESUMO_IMOVEL if item.get(k)) or None
    if resumo:
        out["resumo"] = resumo
    if item.get("link"):
        out["link"] = item["link"]
    atributos = {k: v for k, v in item.items() if k not in _CABECALHO and v not in (None, "")}
    out["atributos"] = atributos
    return out
