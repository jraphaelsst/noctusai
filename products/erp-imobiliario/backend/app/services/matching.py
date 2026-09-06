"""Matching — scoring lives in the seed lib; persistence lives here.

🔴 THE ALGORITHM MOVED. 2026-09-06, when social-wiring became the second
consumer, the 500 lines of scoring that used to sit in this file were promoted
verbatim to ``noctusai_lib.domain.real_estate.matching``. Copying them into
social-wiring instead would have produced two scorers that drift apart on the
first weight change — the fork the seed-first rule exists to prevent.

What stayed: :func:`upsert_matches`, which touches this product's own
``matches`` table and therefore cannot be shared.

Every name this module used to export still resolves, including the
underscore-prefixed ones the tests reach for, so nothing that imported from
``app.services.matching`` had to change. New code should import from
``noctusai_lib.domain.real_estate.matching`` directly.

🔴 THE BILATERAL EMBEDDING PATH IS DEAD IN THIS PRODUCT and the promotion did
not resurrect it — that is a migration, not a refactor. Two independent causes:

  1. ``erp.ativos`` has no ``embedding_interesses`` column. Migration
     ``012_bilateral_embeddings.sql`` adds it and has never been applied.
  2. ``_MATCHING_FIELDS`` in ``app/routers/matching.py`` does not SELECT that
     column, so fixing (1) alone changes nothing.

Until both are closed, ``calcular_bilateral_similarity`` returns 0.0 for every
pair and every score erp produces is the pure rule score. The lib exposes
:func:`falta_vetor_bilateral` so this is assertable rather than inferred from
a suspiciously round number.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.domain.real_estate.matching import (
    MIN_PRECO as _MIN_PRECO,
    MIN_REGIAO as _MIN_REGIAO,
    MIN_SPECS as _MIN_SPECS,
    SCORE_MINIMO_PADRAO,
    SIM_THRESHOLD as _SIM_THRESHOLD,
    _imovel_atende_permuta,
    _permuta_atende_interesse,
    calcular_alinhamento_interesses,
    calcular_bilateral_similarity as _calcular_bilateral_similarity,
    calcular_compatibilidade_preco,
    calcular_compatibilidade_regiao,
    calcular_compatibilidade_specs,
    calcular_qualidade_anuncio,
    calcular_score_total,
    falta_vetor_bilateral,
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
    passa_filtros_minimos as _passa_filtros_minimos,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SCORE_MINIMO_PADRAO",
    "calcular_alinhamento_interesses",
    "calcular_compatibilidade_preco",
    "calcular_compatibilidade_regiao",
    "calcular_compatibilidade_specs",
    "calcular_qualidade_anuncio",
    "calcular_score_total",
    "falta_vetor_bilateral",
    "gerar_matches_para_imovel",
    "gerar_matches_para_permuta",
    "upsert_matches",
]


def upsert_matches(matches: list[dict], db: Any) -> None:
    """Persist matches in one bulk upsert, protecting human decisions.

    A pair whose status a person already moved off ``pendente`` is skipped
    entirely — re-running the generator must never overwrite "rejeitado" with
    a fresh "pendente" and put a discarded match back in front of someone.
    """
    if not matches:
        return

    origin_ids = list({m["ativo_origem_id"] for m in matches})
    existing = (
        db.table("matches")
        .select("ativo_origem_id,ativo_destino_id,status")
        .in_("ativo_origem_id", origin_ids)
        .neq("status", "pendente")
        .execute()
    )

    protected = {
        (r["ativo_origem_id"], r["ativo_destino_id"])
        for r in (existing.data or [])
        if "ativo_origem_id" in r and "ativo_destino_id" in r
    }

    all_upsert_data = []
    for match in matches:
        if (match["ativo_origem_id"], match["ativo_destino_id"]) in protected:
            continue

        upsert_data = {
            "ativo_origem_id": match["ativo_origem_id"],
            "ativo_destino_id": match["ativo_destino_id"],
            "score": match["score"],
            "justificativa": match["justificativa"],
            "detalhes": match["detalhes"],
            "status": "pendente",
        }
        if "score_breakdown" in match:
            upsert_data["score_breakdown"] = match["score_breakdown"]
        all_upsert_data.append(upsert_data)

    if not all_upsert_data:
        logger.info("No new matches to upsert (all protected)")
        return

    db.table("matches").upsert(
        all_upsert_data,
        on_conflict="ativo_origem_id,ativo_destino_id",
    ).execute()

    logger.info(
        "Bulk upserted %d matches (skipped %d protected)",
        len(all_upsert_data),
        len(protected),
    )
