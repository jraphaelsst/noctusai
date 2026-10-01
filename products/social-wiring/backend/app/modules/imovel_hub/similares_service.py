"""Imóveis similar to one imóvel, by PROPERTY profile (contract §4.4, owner D5).

REUSE, NOT A SECOND MATCHER. The score comes from the shared permutas engine —
`noctusai_lib.domain.real_estate.matching.gerar_matches_para_imovel` over the
scorer dicts `permutas.adapter.ativo_para_scorer` builds (tipo, região/bairro,
faixa de preço, dormitórios, área). Nothing here weighs a field.

WHY NOT `adapter.listar_ativos_para_scorer`
-------------------------------------------
It lists only `permuta_ativos` — imóveis whose owner registered a swap intent —
not the catalog. "Similar" must range over the catalog, so the candidate pool is
the `imoveis` mirror rows in the target's uf+cidade (contract §11.8), mapped
through the SAME `ativo_para_scorer` and relabelled with `como_oferta` so the
scorer's specs comparison and region gate engage (their docstrings explain why
`natureza='permuta_imovel'` on the right-hand side matters).

* Pool: same `uf`+`cidade` as the target, target excluded, paged through the
  seed's `iter_paged_rows`, HARD CAP `LIMITE_CANDIDATOS` (2 000) — a catalog row
  count, not a result count, so a runaway city cannot turn a typeahead-grade
  request into an unbounded scan.
* The mirror's `status` is Vista's TRANSACTION TYPE (Venda / Aluguel / Venda e
  Aluguel), not a lifecycle flag: the mirror only holds currently-listed
  imóveis, so membership IS "active". No `status` filter is applied (filtering
  on `status='ativo'` would return nothing, ever).
* Nothing is persisted: no `permuta_matches` write, no embedding call.
* `sem_semantica` = scored pairs where `falta_vetor_bilateral` — the same
  meaning as `permutas.service.gerar_matches`, surfaced rather than hidden.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.real_estate.matching import (
    SCORE_MINIMO_PADRAO,
    falta_vetor_bilateral,
    gerar_matches_para_imovel,
)
from noctusai_lib.integrations.persistence import iter_paged_rows

from app.modules.imovel_hub import _relacionamentos as rel
from app.modules.imovel_hub import busca_service
from app.modules.permutas import adapter
from app.services import table_reads

logger = logging.getLogger(__name__)

LIMITE_CANDIDATOS = 2000
LIMITE_PADRAO = 10
LIMITE_MAXIMO = 50

AVISO_FORA_DO_CATALOGO = "Imóvel fora do catálogo — sem base para comparar."

Motor = Callable[[dict, list[dict], float], list[dict]]


def _linha_do_espelho(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    rows = (
        table_reads.table(client, busca_service.MIRROR_TABLE)
        .select(adapter.IMOVEL_FIELDS)
        .eq("org_id", str(org_id))
        .eq("codigo_norm", codigo)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _candidatos(client: Any, org_id: UUID, alvo: dict, codigo: str) -> list[dict]:
    filtros = {k: alvo[k] for k in ("uf", "cidade") if alvo.get(k)}

    def pagina(start: int, end: int):
        q = (
            table_reads.table(client, busca_service.MIRROR_TABLE)
            .select(adapter.IMOVEL_FIELDS)
            .eq("org_id", str(org_id))
        )
        for coluna, valor in filtros.items():
            q = q.eq(coluna, valor)
        return q.order("codigo").range(start, end).execute().data

    saida: list[dict] = []
    for row in iter_paged_rows(
        pagina,
        page_size=table_reads.PAGE_SIZE,
        id_key="codigo",
        label=f"imoveis similares to {codigo} for org_id={org_id}",
    ):
        if busca_service.canonical(str(row.get("codigo") or "")) == codigo:
            continue
        saida.append(row)
        if len(saida) >= LIMITE_CANDIDATOS:
            break
    return saida


def similares(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    limite: int = LIMITE_PADRAO,
    score_minimo: float = SCORE_MINIMO_PADRAO,
    motor: Motor = gerar_matches_para_imovel,
) -> dict:
    """§4.4 — `{items: [ImovelResumo + score…], total, sem_semantica[, aviso]}`.

    `motor` is the DI seam for the engine entrypoint (default: the real
    `gerar_matches_para_imovel`); a test substitutes a spy THROUGH the seam
    instead of patching this module.
    """
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)
    limite = max(1, min(int(limite), LIMITE_MAXIMO))

    espelho = _linha_do_espelho(client, org_id, canonico)
    if espelho is None or not (espelho.get("uf") or espelho.get("cidade")):
        return {
            "items": [],
            "total": 0,
            "sem_semantica": 0,
            "aviso": AVISO_FORA_DO_CATALOGO,
        }

    origem = adapter.ativo_para_scorer(
        {"id": canonico, "natureza": "imovel", "status": "ativo"}, imovel=espelho
    )
    if origem is None:  # pragma: no cover - guarded by the mirror check above
        return {"items": [], "total": 0, "sem_semantica": 0, "aviso": AVISO_FORA_DO_CATALOGO}

    pool: list[dict] = []
    for linha in _candidatos(client, org_id, espelho, canonico):
        id_candidato = busca_service.canonical(str(linha["codigo"]))
        projetado = adapter.ativo_para_scorer(
            {"id": id_candidato, "natureza": "imovel", "status": "ativo"}, imovel=linha
        )
        if projetado is not None:
            pool.append(adapter.como_oferta(projetado))

    encontrados = motor(origem, pool, score_minimo)
    por_id = {c["id"]: c for c in pool}
    sem_semantica = sum(
        1
        for m in encontrados
        if falta_vetor_bilateral(origem, por_id[m["ativo_destino_id"]])
    )

    encontrados = sorted(encontrados, key=lambda m: m["score"], reverse=True)[:limite]
    resumos = busca_service.enriquecer(
        client, org_id, [m["ativo_destino_id"] for m in encontrados]
    )
    itens = []
    for m in encontrados:
        resumo = resumos.get(busca_service.canonical(m["ativo_destino_id"]))
        if resumo is None:  # pragma: no cover - enriquecer answers every código
            continue
        justificativa = m.get("justificativa") or ""
        itens.append(
            {
                **resumo,
                "score": m["score"],
                "justificativa": justificativa,
                "reasons": [p for p in justificativa.split(". ") if p],
                "detalhes": m.get("detalhes") or {},
                "score_breakdown": m.get("score_breakdown") or {},
            }
        )
    return {"items": itens, "total": len(itens), "sem_semantica": sem_semantica}


__all__ = [
    "AVISO_FORA_DO_CATALOGO",
    "LIMITE_CANDIDATOS",
    "LIMITE_MAXIMO",
    "LIMITE_PADRAO",
    "similares",
]
