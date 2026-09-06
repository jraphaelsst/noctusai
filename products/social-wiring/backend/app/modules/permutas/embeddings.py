"""Vectorises what each ativo IS and what it WANTS.

Two vectors per ativo, and both are required for a pair to score semantically:

    embedding             the profile — what is on offer
    embedding_interesses  the wants — what would be accepted

🔴 BOTH, OR NEITHER COUNTS. The lib's bilateral similarity needs all four
vectors across a pair and returns 0.0 if any is missing, so writing only the
profile — which is what erp effectively did — buys nothing at all. This module
therefore always writes them as a pair, and records `embedding_atualizado_em`
so a half-written row is distinguishable from an unprocessed one.

🔴 AN ATIVO THAT STATED NO INTEREST GETS NO INTEREST VECTOR.
`texto_interesses_para_embedding` returns "" when the person wrote nothing,
and embedding an empty (or a generic stand-in) string would place that ativo
at roughly equal distance from every listing — which the composite would then
read as moderate compatibility with the entire catalog. Those rows keep
scoring on rules alone, which is the honest answer for someone who has not
said what they want.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.llm import generate_embeddings_batch

from app.modules.permutas import adapter

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
ATIVOS = "permuta_ativos"

#: 1536 dims — must match the `extensions.vector(1536)` columns in migration
#: 101. Changing this is a migration, not a config edit.
MODELO = "text-embedding-3-small"

#: How many texts go in one provider round-trip. The whole registry is a few
#: hundred rows, so this is about staying under the provider's request-size
#: cap rather than about throughput.
LOTE = 64


async def embutir_ativos(
    client: Any,
    org_id: UUID,
    *,
    apenas_pendentes: bool = True,
    ativo_ids: Optional[list[UUID]] = None,
) -> dict:
    """Generate and store both vectors for the org's ativos.

    `apenas_pendentes` (the default) skips rows that already have both — an
    edit clears them (see `service.atualizar_ativo`), so "pending" genuinely
    means "changed or never done" rather than "we forgot".
    """
    projetados, nao_resolvidos = adapter.listar_ativos_para_scorer(client, str(org_id))
    por_id = {p["id"]: p for p in projetados}

    q = (
        client.schema(SCHEMA)
        .table(ATIVOS)
        .select("id,observacoes,embedding,embedding_interesses")
        .eq("org_id", str(org_id))
        .eq("status", "ativo")
    )
    if ativo_ids:
        q = q.in_("id", [str(i) for i in ativo_ids])
    linhas = (q.execute()).data or []

    interesses_rows = (
        client.schema(SCHEMA)
        .table("permuta_interesses")
        .select(adapter.INTERESSE_FIELDS)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    interesses_por_ativo: dict[str, list[dict]] = {}
    for row in interesses_rows:
        interesses_por_ativo.setdefault(row["ativo_id"], []).append(row)

    pendentes: list[tuple[str, str, str]] = []  # (id, texto_perfil, texto_interesses)
    for linha in linhas:
        if apenas_pendentes and linha.get("embedding") and linha.get("embedding_interesses"):
            continue
        projetado = por_id.get(linha["id"])
        if projetado is None:
            # Unresolvable against the catalog — already reported by the
            # adapter. Embedding it would vectorise an empty property.
            continue

        perfil = adapter.texto_para_embedding(projetado)
        desejo = adapter.texto_interesses_para_embedding(
            linha, interesses_por_ativo.get(linha["id"], [])
        )
        if not perfil or not desejo:
            continue
        pendentes.append((linha["id"], perfil, desejo))

    if not pendentes:
        return {
            "processados": 0,
            "pendentes": 0,
            "sem_texto": len(linhas),
            "nao_resolvidos": len(nao_resolvidos),
        }

    processados = 0
    agora = datetime.now(timezone.utc).isoformat()
    for inicio in range(0, len(pendentes), LOTE):
        fatia = pendentes[inicio:inicio + LOTE]
        # One call for both texts of every ativo in the slice — the batch
        # endpoint takes an array, and a per-text loop is what turns a few
        # hundred rows into a few hundred HTTP requests and a rate-limit storm.
        textos = [t for _, perfil, desejo in fatia for t in (perfil, desejo)]
        vetores = await generate_embeddings_batch(
            textos, model=MODELO, org_id=str(org_id)
        )

        for indice, (ativo_id, _perfil, _desejo) in enumerate(fatia):
            perfil_vec = vetores[indice * 2]
            desejo_vec = vetores[indice * 2 + 1]
            (
                client.schema(SCHEMA)
                .table(ATIVOS)
                .update({
                    "embedding": perfil_vec,
                    "embedding_interesses": desejo_vec,
                    "embedding_atualizado_em": agora,
                })
                .eq("org_id", str(org_id))
                .eq("id", ativo_id)
                .execute()
            )
            processados += 1

    logger.info(
        "permutas.embutir_ativos org=%s processados=%d de %d candidatos",
        org_id, processados, len(pendentes),
    )
    return {
        "processados": processados,
        "pendentes": len(pendentes) - processados,
        "sem_texto": len(linhas) - len(pendentes),
        "nao_resolvidos": len(nao_resolvidos),
    }


__all__ = ["LOTE", "MODELO", "embutir_ativos"]
