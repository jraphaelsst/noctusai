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
from app.services.api_keys_store import resolve_embedding_provider

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
ATIVOS = "permuta_ativos"

#: 🔴 THE COLUMN WIDTH, AND IT IS NOT NEGOTIABLE PER-PROVIDER.
#: `permuta_ativos.embedding` / `embedding_interesses` are
#: `extensions.vector(1536)` (migration 101). Every provider below must be
#: asked for EXACTLY this width. Changing it is a migration, not a config edit
#: — and re-embedding under a different width invalidates every stored vector,
#: because cosine similarity across two embedding spaces is noise rather than
#: a weaker signal.
DIMENSOES = 1536

#: Which model each provider uses for this corpus.
#:
#: 🔴 THE TWO ARE NOT INTERCHANGEABLE BY DEFAULT. OpenAI's
#: `text-embedding-3-small` is natively 1536. Gemini's `gemini-embedding-001`
#: returns **3072** unless asked otherwise — writing that into a
#: `vector(1536)` column fails at the INSERT, a layer away from the setting
#: that chose it. Gemini supports Matryoshka truncation, so the width is
#: requested explicitly below; that plumbing had to be added to the seed
#: provider (it accepted no config at all) before this switch could work.
MODELOS: dict[str, str] = {
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
}

#: Providers that need the width stated explicitly. OpenAI's parameter is
#: `dimensions` and its default already matches, so passing this vendor's
#: spelling to it would be an unknown kwarg reaching the OpenAI SDK.
_PRECISA_DIMENSAO = frozenset({"gemini"})

#: How many texts go in one provider round-trip. The whole registry is a few
#: hundred rows, so this is about staying under the provider's request-size
#: cap rather than about throughput.
LOTE = 64


def _conferir_dimensoes(vetores: list[list[float]], provedor: str, modelo: str) -> None:
    """Refuse a batch whose width does not match the column. Loudly.

    🔴 THE ALTERNATIVE IS SILENT CORRUPTION OF THE WHOLE SEMANTIC LAYER.
    A wrong-width vector either fails at the INSERT with a message about a
    column (nothing about the provider that caused it), or — if a future
    caller ever pads or truncates to make it fit — lands a vector that is
    numerically valid and semantically meaningless. Cosine similarity would
    keep returning plausible numbers forever, and the matches would quietly
    get worse with nothing to read in any log.
    """
    if not vetores:
        return
    largura = len(vetores[0])
    if largura != DIMENSOES:
        raise ValueError(
            f"{provedor}/{modelo} devolveu vetores de {largura} dimensões, mas as "
            f"colunas são vector({DIMENSOES}). Nenhum vetor foi gravado. "
            f"Ajuste o modelo/largura em MODELOS ou migre as colunas — nunca "
            f"trunque o vetor para caber."
        )


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

    # The operator's manual pick. Resolved ONCE per run, not per batch: a
    # setting changed mid-run would embed half the corpus in one space and
    # half in another, and the two halves would never be comparable again.
    provedor = resolve_embedding_provider(str(org_id))
    modelo = MODELOS.get(provedor)
    if modelo is None:
        raise ValueError(
            f"Provedor de embeddings {provedor!r} não tem modelo mapeado em "
            f"MODELOS ({sorted(MODELOS)})."
        )
    extra = {"output_dimensionality": DIMENSOES} if provedor in _PRECISA_DIMENSAO else {}
    logger.info(
        "permutas.embutir_ativos org=%s provedor=%s modelo=%s dims=%d candidatos=%d",
        org_id, provedor, modelo, DIMENSOES, len(pendentes),
    )

    processados = 0
    agora = datetime.now(timezone.utc).isoformat()
    for inicio in range(0, len(pendentes), LOTE):
        fatia = pendentes[inicio:inicio + LOTE]
        # One call for both texts of every ativo in the slice — the batch
        # endpoint takes an array, and a per-text loop is what turns a few
        # hundred rows into a few hundred HTTP requests and a rate-limit storm.
        textos = [t for _, perfil, desejo in fatia for t in (perfil, desejo)]
        vetores = await generate_embeddings_batch(
            textos, model=modelo, provider=provedor, org_id=str(org_id), **extra
        )
        _conferir_dimensoes(vetores, provedor, modelo)

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
        # Surfaced so the page can say WHICH vendor produced the layer — two
        # providers' vectors are not comparable, so "which one" is part of the
        # answer, not diagnostics.
        "provedor": provedor,
        "modelo": modelo,
        "dimensoes": DIMENSOES,
        "processados": processados,
        "pendentes": len(pendentes) - processados,
        "sem_texto": len(linhas) - len(pendentes),
        "nao_resolvidos": len(nao_resolvidos),
    }


__all__ = ["LOTE", "MODELO", "embutir_ativos"]
