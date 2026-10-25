"""Readiness x document suggestions: the one-click "Aplicar" on a `faltando`.

A `faltando` whose field already has a pending document reading (a certidao
de casamento that states the genero, a ficha that states the profissao...)
used to be a dead end: the operator was told to SEND a document the card
already holds. The reading is deliberately never auto-written (a derived
value is a suggestion, `identidade_extracao_service.sugestoes_pendentes`), so
the readiness carries it as `faltando[].sugestao` and the UI applies it through
the existing confirm endpoint (`POST .../documentos/{id}/extracao/confirmar`)
-- ONE mechanism for every identity field, never per-field wiring.
"""
from __future__ import annotations

from typing import Any, Callable

from app.modules.card_hub.contrato_gerador.dados import DadosContrato

#: Only party-qualification faltas are backed by `clientes` columns.
_PREFIXO = "qualificacao."


def anexar_sugestoes(
    dados: DadosContrato,
    faltando: list[dict],
    sugestoes_do_cliente: Callable[[str], dict],
) -> None:
    """Add `sugestao` to every `faltando` item whose field has a pending,
    uncompromised document reading on that party's record (mutates in place).

    `sugestoes_do_cliente(cliente_id)` is `identidade_extracao_service.
    sugestoes_pendentes` (injected so this stays pure/testable)."""
    pessoas = [*dados.vendedores, *dados.compradores]
    por_parte: dict[Any, str] = {}
    for p in pessoas:
        # The titular has no parte row (`parte_id=None`); first one wins.
        por_parte.setdefault(p.parte_id, p.cliente_id)
    cache: dict[str, dict] = {}
    for item in faltando:
        campo = item.get("campo") or ""
        if item.get("onde") != "partes" or not campo.startswith(_PREFIXO):
            continue
        cliente_id = por_parte.get(item.get("parte_id"))
        if not cliente_id:
            continue
        if cliente_id not in cache:
            cache[cliente_id] = sugestoes_do_cliente(cliente_id) or {}
        item_key = campo[len(_PREFIXO):]
        s = cache[cliente_id].get(item_key)
        if not s or s.get("leitura_comprometida") or not s.get("valor"):
            continue
        item["sugestao"] = {
            "cliente_id": cliente_id,
            "item_key": item_key,
            "documento_id": str(s["documento_id"]),
            "documento_nome": s.get("documento_nome"),
            "tipo_documento": s.get("tipo_documento"),
            "valor": s["valor"],
            "confianca": s.get("confianca"),
        }
