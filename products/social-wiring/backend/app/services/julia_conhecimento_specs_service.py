"""Julia > Conhecimento as an EDITOR of agents org specs (Lais study S8, owner decision 2026-11-17).

The knowledge form used to be copied once into an undeclared spec key (`julia_conhecimento_backfill`, now removed). The three
declared keys (contract shared with the agents slice, type `texto_longo`) are written directly instead:

  conhecimento_venda       how the agency sells (documents, financing, process)
  conhecimento_locacao     how the agency rents (documents, guarantees, process)
  conhecimento_politicas   general policies (signing, keys, phones by sector, recess)

SW stores nothing: `GET` reads the org's values from agents, `PUT` writes ONLY these three keys through the channel client with
the acting user as `ator`. `sugestao` is the old form's saved sections rendered by the existing deterministic renderer and split
per key, so an editor with empty fields can offer "preencher a partir do formulário antigo" (nothing is written until the person
saves). Each save records one `configuracao_alterada` event (keys + sizes, never the text).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_conhecimento_service as legado
from app.services import julia_eventos_service as eventos

CHAVES: tuple[str, ...] = ("conhecimento_venda", "conhecimento_locacao", "conhecimento_politicas")
ROTULOS: dict[str, str] = {
    "conhecimento_venda": "Vendas",
    "conhecimento_locacao": "Locação",
    "conhecimento_politicas": "Políticas e informações gerais",
}
#: agents' cap for a `texto_longo` value (`org_spec.valor.texto_longo`).
MAX_CHARS = 4000
_TITULO_PARA_CHAVE = {"vendas": "conhecimento_venda", "locação": "conhecimento_locacao", "locacao": "conhecimento_locacao"}
_H2 = re.compile(r"^## (.+)$", re.MULTILINE)


def validar(valores: dict[str, str]) -> dict[str, str]:
    """Only the three keys, each within agents' cap. A blank value clears the spec (agents' rule). 422 pt-BR otherwise."""
    if not valores:
        raise AppException("sem_alteracao", "Nada para salvar.", status_code=422)
    desconhecidas = sorted(set(valores) - set(CHAVES))
    if desconhecidas:
        raise AppException("chave_invalida", "Só é possível editar vendas, locação e políticas.", status_code=422)
    out: dict[str, str] = {}
    for chave, texto in valores.items():
        t = (texto or "").strip()
        if len(t) > MAX_CHARS:
            raise AppException(
                "texto_longo_demais", f"{ROTULOS[chave]}: no máximo {MAX_CHARS} caracteres (hoje {len(t)}).", status_code=422,
            )
        out[chave] = t
    return out


def dividir_por_chave(markdown: str) -> dict[str, str]:
    """Split the legacy renderer's markdown (`## Aviso de recesso` / `## Informações gerais` / `## Vendas` / `## Locação`) into the
    three keys; recess and general information go to the policies key. Empty chunks are omitted."""
    partes: dict[str, list[str]] = {c: [] for c in CHAVES}
    achados = list(_H2.finditer(markdown or ""))
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(markdown)
        chave = _TITULO_PARA_CHAVE.get(m.group(1).strip().lower(), "conhecimento_politicas")
        partes[chave].append(markdown[m.start():fim].strip())
    return {c: "\n\n".join(p) for c, p in partes.items() if p}


def sugestao(client: Any, org_id: UUID | str, *, hoje: Optional[date] = None) -> dict[str, str]:
    """The old form's saved sections, split per key (empty when the org never saved any). A read failure answers `{}`."""
    try:
        return dividir_por_chave(legado.render_md(client, org_id, hoje=hoje))
    except Exception:  # noqa: BLE001 -- a convenience only; the editor works without it
        return {}


def montar(valores_agents: list[dict[str, Any]], declaradas: list[dict[str, Any]], sug: dict[str, str]) -> dict[str, Any]:
    por_chave = {v.get("chave"): v for v in valores_agents or []}
    declaradas_set = {d.get("chave") for d in declaradas or []}
    itens = []
    for chave in CHAVES:
        v = por_chave.get(chave) or {}
        itens.append({
            "chave": chave, "rotulo": ROTULOS[chave], "valor": v.get("valor") or "", "declarada": chave in declaradas_set,
            "updated_at": v.get("updated_at"), "updated_by_nome": v.get("updated_by_nome"),
            "sugestao": sug.get(chave) or None,
        })
    return {"itens": itens, "max_chars": MAX_CHARS}


def registrar_evento(client: Any, org_id: UUID | str, ator_id: str, valores: dict[str, str]) -> None:
    eventos.emitir(client, org_id, "configuracao_alterada", None, {
        "area": "conhecimento", "chaves": sorted(valores), "tamanhos": {k: len(v) for k, v in sorted(valores.items())},
        "ator": ator_id,
    })


__all__ = ["CHAVES", "MAX_CHARS", "ROTULOS", "dividir_por_chave", "montar", "registrar_evento", "sugestao", "validar"]
