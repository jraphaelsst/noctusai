"""``catalogo_para(chave)``: the ONE place a catalogue key becomes an adapter. An unknown key raises -- there is no
silent fallback to another catalogue (a lead must never be offered options from a catalogue nobody chose)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.catalogos.fixture import FixtureCatalogo
from app.catalogos.imoveis_sw import ImoveisSwCatalogo
from app.catalogos.protocolo import CatalogoOpcoes

__all__ = ["CATALOGOS", "CatalogoDesconhecido", "CatalogoIndisponivel", "catalogo_para", "chaves_de_catalogo"]

#: The closed set of catalogue keys a standard's ``parametros.catalogo`` may name.
CATALOGOS: tuple[str, ...] = ("imoveis_sw", "fixture")


class CatalogoDesconhecido(ValueError):
    """The key names no catalogue."""


class CatalogoIndisponivel(RuntimeError):
    """The key is valid but this turn lacks what the adapter needs (e.g. the SW client)."""


def chaves_de_catalogo() -> tuple[str, ...]:
    return CATALOGOS


def catalogo_para(
    chave: str | None, *, sw: Any | None = None, itens: Sequence[Mapping[str, Any]] | None = None,
) -> CatalogoOpcoes:
    if chave == "imoveis_sw":
        if sw is None:
            raise CatalogoIndisponivel("imoveis_sw needs the social-wiring client of the turn")
        return ImoveisSwCatalogo(sw)
    if chave == "fixture":
        return FixtureCatalogo(itens)
    raise CatalogoDesconhecido(f"unknown catalogue {chave!r}; known: {', '.join(CATALOGOS)}")
