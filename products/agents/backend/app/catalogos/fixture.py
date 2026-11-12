"""The synthetic catalogue: the Fake of :class:`CatalogoOpcoes`.

Two users: the eval world (the roteiro's synthetic catalogue, so a run never reads a tenant's business) and a template
with no business of its own, which serves ``Opção A / B / C`` so the offer flow can be exercised end to end.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from app.catalogos.imoveis_sw import consulta_sw
from app.catalogos.protocolo import Busca, codigo_origem_do_estado, opcao_de_item, perfil_como_texto

__all__ = ["OPCOES_PADRAO", "FixtureCatalogo", "casa"]

#: What a catalogue with nothing configured serves: three options, no business behind them.
OPCOES_PADRAO: tuple[Mapping[str, Any], ...] = tuple(
    {"codigo": f"opcao-{letra.lower()}", "titulo": f"Opção {letra}", "resumo": f"Descrição da opção {letra}."}
    for letra in "ABC"
)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def casa(item: Mapping[str, Any], args: Mapping[str, Any]) -> bool:
    """Does a synthetic catalogue item satisfy the search args? A filter applies only to a field the item HAS:
    a fixture describes what it needs, the rest is not constrained."""
    for campo in ("operacao", "tipo", "cidade"):
        if args.get(campo) and campo in item and str(item[campo]).casefold() != str(args[campo]).casefold():
            return False
    if args.get("bairros") and "bairro" in item:
        if str(item["bairro"]).casefold() not in {str(b).casefold() for b in args["bairros"]}:
            return False
    preco = _num(item.get("preco"))
    if preco is not None:
        if args.get("preco_min") is not None and preco < float(args["preco_min"]):
            return False
        if args.get("preco_max") is not None and preco > float(args["preco_max"]):
            return False
    for campo, arg in (("quartos", "quartos_min"), ("vagas", "vagas_min")):
        valor = _num(item.get(campo))
        if valor is not None and args.get(arg) is not None and valor < float(args[arg]):
            return False
    return True


class FixtureCatalogo:
    """In-memory :class:`CatalogoOpcoes`. Records every call (``chamadas``); ``falhar`` makes it unavailable."""

    chave = "fixture"

    def __init__(self, itens: Sequence[Mapping[str, Any]] | None = None, *, falhar: bool = False) -> None:
        self._itens = [dict(i) for i in (OPCOES_PADRAO if not itens else itens)]
        self.falhar = falhar
        self.chamadas: list[tuple[str, dict[str, Any]]] = []

    def origem(self, estado: Any) -> str | None:
        return codigo_origem_do_estado(estado)

    async def buscar_origem(self, org_id: UUID, codigo: str, *, interacao_id: str | None = None) -> Busca | None:
        self.chamadas.append(("buscar_origem", {"codigo": codigo}))
        if self.falhar:
            return None
        return Busca(tuple(i for i in self._itens if str(i.get("codigo")) == str(codigo)))

    async def buscar(
        self, org_id: UUID, *, perfil: Mapping[str, Any], excluir: Sequence[str], limite: int,
        similar_a: str | None = None, interacao_id: str | None = None,
    ) -> Busca | None:
        self.chamadas.append(("buscar", {"perfil": dict(perfil), "excluir": list(excluir), "limite": limite, "similar_a": similar_a}))
        if self.falhar:
            return None
        vetados = {str(c) for c in excluir}
        args = consulta_sw(perfil)
        todos = [i for i in self._itens if str(i.get("codigo")) not in vetados and casa(i, args)]
        return Busca(tuple(todos[: max(1, limite)]), {"restantes_estimados": max(0, len(todos) - max(1, limite))})

    async def detalhar(
        self, org_id: UUID, codigo: str, *, interacao_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        self.chamadas.append(("detalhar", {"codigo": codigo}))
        if self.falhar:
            return None
        achado = next((i for i in self._itens if str(i.get("codigo")) == str(codigo)), None)
        return achado if achado is not None else {"encontrado": False}

    def perfil_texto(self, perfil: Mapping[str, Any]) -> str:
        return perfil_como_texto(perfil)

    def opcao(self, item: Mapping[str, Any]) -> dict[str, Any]:
        return opcao_de_item(item)
