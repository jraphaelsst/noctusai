"""Permutas — registry reads/writes, match generation, funnel moves.

🔴 EVERY CALL TAKES A USER-SCOPED CLIENT. Migration 101 gives all three tables
a `FOR ALL TO authenticated` policy predicated on `current_org_id()`, so RLS is
what scopes the rows; the `.eq("org_id", ...)` predicates below are
belt-and-braces against a future caller handing in an admin client.

WHERE THE SCORING IS
────────────────────
Not here. `noctusai_lib.domain.real_estate.permuta` scores two dicts as a
SWAP (does each owner get what they asked for?) and `adapter.py` produces
them. Vehicle offers still go through `matching`, the similarity engine — the
swap scorer models property-for-property only. This module is the part that cannot be shared: the
queries, the upsert, and the rule about which rows a re-run is allowed to
touch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.real_estate.matching import (
    falta_vetor_bilateral,
    gerar_matches_para_imovel,
)
from noctusai_lib.domain.real_estate.permuta import (
    SCORE_MINIMO_PERMUTA,
    emitir_permuta,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_ as ValidationError

from app.modules.permutas import adapter

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
ATIVOS = "permuta_ativos"
INTERESSES = "permuta_interesses"
MATCHES = "permuta_matches"

#: The one stage a re-run may overwrite. Everything else is a human decision.
ETAPA_INICIAL = "sugerido"
ETAPAS = ("sugerido", "avaliacao", "negociacao", "fechado", "rejeitado")

#: Why a broker rejects a match — the tuning labels for the swap scorer. The
#: ONE vocabulary: migration 310's CHECK mirrors it (parity pinned by a test)
#: and `GET /api/permutas/motivos-rejeicao` serves it to the UI.
MOTIVOS_REJEICAO: tuple[dict, ...] = (
    {"codigo": "valor", "rotulo": "Valor / diferença incompatível", "exige_detalhe": False},
    {"codigo": "tipo", "rotulo": "Tipo de imóvel não interessa", "exige_detalhe": False},
    {"codigo": "localizacao", "rotulo": "Localização não interessa", "exige_detalhe": False},
    {"codigo": "caracteristicas", "rotulo": "Características (tamanho, quartos, estrutura)", "exige_detalhe": False},
    {"codigo": "proprietario_sem_interesse", "rotulo": "Proprietário não quis seguir", "exige_detalhe": False},
    {"codigo": "indisponivel", "rotulo": "Imóvel indisponível ou já negociado", "exige_detalhe": False},
    {"codigo": "documentacao", "rotulo": "Documentação / situação jurídica", "exige_detalhe": False},
    {"codigo": "duplicado", "rotulo": "Mesmo proprietário ou par duplicado", "exige_detalhe": False},
    {"codigo": "outro", "rotulo": "Outro", "exige_detalhe": True},
)
MOTIVOS_CODIGOS = tuple(m["codigo"] for m in MOTIVOS_REJEICAO)
MOTIVO_LADOS = ("origem", "destino", "ambos")
ETAPA_REJEITADO = "rejeitado"

#: Columns a caller may set on an ativo. `id`, `org_id`, the embeddings and the
#: audit columns are derived here, never accepted.
ATIVO_EDITAVEL = (
    "natureza", "imovel_codigo", "codigo", "corretor_id",
    "proprietario_nome", "proprietario_telefone", "proprietario_email",
    "tipo_imovel", "cep", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "zona", "condominio_nome",
    "valor", "area_total", "area_privativa", "quartos", "suites", "vagas",
    "faixa_preco_min", "faixa_preco_max", "regiao_preferida",
    "aceita_completar_diferenca", "limite_complemento",
    "percentual_min", "percentual_max",
    "observacoes", "status",
)

INTERESSE_EDITAVEL = (
    "tipo", "tipo_imovel", "zona", "cidade", "bairro",
    "valor_minimo", "valor_maximo", "percentual_min", "percentual_max",
    "marca", "modelo", "ano_min", "ano_max", "observacoes",
)


def _t(client: Any, table: str):
    return client.schema(SCHEMA).table(table)


# ── Registry ────────────────────────────────────────────────────────────────


def listar_ativos(
    client: Any,
    org_id: UUID,
    *,
    natureza: Optional[str] = None,
    corretor_id: Optional[UUID] = None,
    incluir_inativos: bool = False,
) -> dict:
    """The swap registry, newest first, with each ativo's interests attached."""
    q = _t(client, ATIVOS).select(adapter.ATIVO_FIELDS).eq("org_id", str(org_id))
    if natureza:
        q = q.eq("natureza", natureza)
    if corretor_id:
        q = q.eq("corretor_id", str(corretor_id))
    if not incluir_inativos:
        q = q.eq("status", "ativo")
    rows = (q.order("created_at", desc=True).execute()).data or []
    if not rows:
        return {"items": [], "total": 0}

    interesses = (
        _t(client, INTERESSES)
        .select(adapter.INTERESSE_FIELDS)
        .in_("ativo_id", [r["id"] for r in rows])
        .execute()
    ).data or []
    por_ativo: dict[str, list[dict]] = {}
    for i in interesses:
        por_ativo.setdefault(i["ativo_id"], []).append(i)

    catalogo = _catalogo_por_codigo(
        client, org_id, [r["imovel_codigo"] for r in rows if r.get("imovel_codigo")]
    )

    itens = []
    for row in rows:
        # The vectors are 1536 floats each. Returning them would put ~24KB of
        # numbers on the wire per row for a list nobody plots — the UI needs to
        # know only WHETHER semantic scoring is available.
        item = {k: v for k, v in row.items() if not k.startswith("embedding")}
        item["tem_embedding"] = bool(row.get("embedding"))
        item["tem_embedding_interesses"] = bool(row.get("embedding_interesses"))
        item["interesses"] = por_ativo.get(row["id"], [])
        # 🔴 A SEPARATE KEY, never folded over the row's own columns. A
        # natureza='imovel' row is a pointer whose own bairro/valor are mostly
        # empty, so the registry list needs the catalog's — but the edit form
        # is prefilled from THIS payload, and merging would write catalog data
        # back into the intent row on the next save. `None` = the código is
        # not (or no longer) in the catalog, which the page says out loud.
        imovel = catalogo.get(row.get("imovel_codigo") or "")
        item["catalogo"] = (
            {
                "titulo": imovel.get("titulo"),
                "categoria": imovel.get("categoria"),
                "bairro": imovel.get("bairro"),
                "cidade": imovel.get("cidade"),
                "uf": imovel.get("uf"),
                "valor_venda": imovel.get("valor_venda"),
            }
            if imovel
            else None
        )
        itens.append(item)

    return {"items": itens, "total": len(itens)}


def _catalogo_por_codigo(client: Any, org_id: UUID, codigos: list[str]) -> dict[str, dict]:
    """Catalog listings for a set of códigos, in one query (never per row)."""
    if not codigos:
        return {}
    linhas = (
        _t(client, "imoveis")
        .select("codigo,titulo,categoria,bairro,cidade,uf,valor_venda")
        .eq("org_id", str(org_id))
        .in_("codigo", sorted(set(codigos)))
        .execute()
    ).data or []
    return {i["codigo"]: i for i in linhas}


def obter_ativo(client: Any, org_id: UUID, ativo_id: UUID) -> dict:
    rows = (
        _t(client, ATIVOS)
        .select(adapter.ATIVO_FIELDS)
        .eq("org_id", str(org_id))
        .eq("id", str(ativo_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("Permuta não encontrada.")
    row = {k: v for k, v in rows[0].items() if not k.startswith("embedding")}
    row["interesses"] = (
        _t(client, INTERESSES)
        .select(adapter.INTERESSE_FIELDS)
        .eq("ativo_id", str(ativo_id))
        .execute()
    ).data or []
    return row


def criar_ativo(
    client: Any,
    org_id: UUID,
    *,
    dados: dict,
    user_id: Optional[UUID] = None,
) -> dict:
    """Register a swap intent, with its interests, in one call.

    Interests arrive nested rather than through a second endpoint: an intent
    with no stated interest is matchable against nearly everything, so making
    them separate round-trips would leave a window where the engine can run
    against a half-declared row and produce noise that outlives the mistake.
    """
    row = {k: dados[k] for k in ATIVO_EDITAVEL if k in dados}
    if not row.get("natureza"):
        raise ValidationError("natureza é obrigatória.")
    if row["natureza"] == "imovel" and not row.get("imovel_codigo"):
        # The DB CHECK enforces this too; the message is what makes it
        # actionable instead of a constraint name.
        raise ValidationError(
            "Uma intenção de permuta sobre um imóvel do catálogo precisa do "
            "código do imóvel."
        )

    row["id"] = str(uuid4())
    row["org_id"] = str(org_id)
    row.setdefault("status", "ativo")
    row.setdefault("origem", "manual")
    if user_id:
        row["created_por"] = str(user_id)

    _t(client, ATIVOS).insert(row).execute()

    interesses = dados.get("interesses") or []
    if interesses:
        _inserir_interesses(client, org_id, UUID(row["id"]), interesses)

    return obter_ativo(client, org_id, UUID(row["id"]))


def _inserir_interesses(
    client: Any, org_id: UUID, ativo_id: UUID, interesses: list[dict]
) -> None:
    linhas = []
    for item in interesses:
        linha = {k: item[k] for k in INTERESSE_EDITAVEL if k in item}
        linha["id"] = str(uuid4())
        linha["org_id"] = str(org_id)
        linha["ativo_id"] = str(ativo_id)
        linha.setdefault("tipo", "imovel")
        linhas.append(linha)
    if linhas:
        _t(client, INTERESSES).insert(linhas).execute()


def atualizar_ativo(
    client: Any,
    org_id: UUID,
    ativo_id: UUID,
    *,
    dados: dict,
    user_id: Optional[UUID] = None,
) -> dict:
    """Patch an ativo. `interesses`, when present, REPLACES the set.

    🔴 REPLACE, NOT MERGE, and the reason is that an interest has no stable
    client-side identity — the UI edits a list of criteria, not a set of
    addressable rows. Merging would need the caller to send ids it does not
    have, and the failure mode of getting that wrong is a duplicate criterion
    that silently widens what the engine will match. Omitting the key leaves
    the existing interests untouched; sending `[]` clears them, deliberately.
    """
    obter_ativo(client, org_id, ativo_id)  # 404 before writing, not after

    updates = {k: dados[k] for k in ATIVO_EDITAVEL if k in dados}
    if updates:
        if user_id:
            updates["updated_por"] = str(user_id)
        # Any edit can change what this ativo IS or WANTS, so the vectors are
        # now stale. Clearing them is the honest move: a stale vector scores
        # confidently against the wrong text, and `falta_vetor_bilateral`
        # then reports the pair as semantically covered when it is not.
        updates["embedding"] = None
        updates["embedding_interesses"] = None
        updates["embedding_atualizado_em"] = None
        (
            _t(client, ATIVOS)
            .update(updates)
            .eq("org_id", str(org_id))
            .eq("id", str(ativo_id))
            .execute()
        )

    if "interesses" in dados:
        _t(client, INTERESSES).delete().eq("org_id", str(org_id)).eq(
            "ativo_id", str(ativo_id)
        ).execute()
        _inserir_interesses(client, org_id, ativo_id, dados["interesses"] or [])

    return obter_ativo(client, org_id, ativo_id)


def remover_ativo(client: Any, org_id: UUID, ativo_id: UUID) -> None:
    """Delete an intent. Its interests and matches go with it (FK CASCADE)."""
    obter_ativo(client, org_id, ativo_id)
    _t(client, ATIVOS).delete().eq("org_id", str(org_id)).eq("id", str(ativo_id)).execute()


# ── Matching ────────────────────────────────────────────────────────────────


def gerar_matches(
    client: Any,
    org_id: UUID,
    *,
    ativo_id: Optional[UUID] = None,
    score_minimo: float = SCORE_MINIMO_PERMUTA,
) -> dict:
    """Run the engine and persist what it finds.

    With no `ativo_id` this is a full scan. With one, it is that ativo against
    everything it could pair with.

    Returns counts AND `sem_semantica` — how many scored pairs ran without
    embeddings. See the note on the return for why that number is reported
    rather than logged.
    """
    todos, nao_resolvidos = adapter.listar_ativos_para_scorer(client, str(org_id))

    imoveis = [a for a in todos if a["natureza"] == "imovel"]
    permutas = [a for a in todos if a["natureza"] != "imovel"]

    # Narrowing to one ativo has to narrow the CORRECT side, and for a
    # registered permuta that means keeping every imóvel as a driver while
    # letting nothing else into the candidate pool. Leaving the imóvel list
    # whole without also emptying the offer-views would score every unrelated
    # imóvel×imóvel pair under the guise of "matches for this permuta".
    alvo_e_permuta = False
    if ativo_id:
        alvo = str(ativo_id)
        if any(a["id"] == alvo for a in imoveis):
            imoveis = [a for a in imoveis if a["id"] == alvo]
        elif any(a["id"] == alvo for a in permutas):
            permutas = [a for a in permutas if a["id"] == alvo]
            alvo_e_permuta = True
        else:
            raise NotFoundError("Permuta não encontrada ou sem imóvel no catálogo.")

    # ── Build the ordered pair list, then score each pair exactly once ──
    #
    # 🔴 TWO MATCH SHAPES, and the second is 94% of the real corpus.
    #
    #   imóvel × permuta   a listing against a property someone brought as
    #                      currency. The ONLY shape erp models — 5 of the 82
    #                      legacy matches.
    #   imóvel × imóvel    two listings whose owners each accept a swap,
    #                      trading with each other. 77 of 82. Pairing only
    #                      against the first pool would silently return 6% of
    #                      the answer: no error, just far fewer matches.
    #
    # 🔴 ONE CANONICAL ORIENTATION PER PAIR: origem is always the
    # lexicographically smaller id. A→B and B→A are NOT the same match —
    # `calcular_qualidade_anuncio` scores the ORIGEM side only — so without a
    # fixed rule the unique index turns the second into an upsert that
    # overwrites the first with the reverse score, and a legacy human decision
    # imported under the other orientation stops protecting the pair.
    pares: list[tuple[dict, dict]] = []
    for imovel in imoveis:
        for permuta in permutas:
            pares.append((imovel, permuta))

    if not alvo_e_permuta:
        por_ordem = sorted(imoveis, key=lambda a: a["id"])
        for i, a in enumerate(por_ordem):
            for b in por_ordem[i + 1:]:
                pares.append((a, b))
        if ativo_id:
            # Narrowed to one imóvel: keep only the pairs it belongs to. The
            # canonical orientation still holds — the target may end up as
            # destino, which is correct, and is what makes this run write rows
            # identical to the ones a full scan would.
            alvo = str(ativo_id)
            pares = [p for p in pares if alvo in (p[0]["id"], p[1]["id"])]

    # 🔴 THE SWAP SCORER, NOT THE SIMILARITY ONE. `matching` rewards two
    # properties for being alike (same city, close price, same type); a swap
    # needs each to be what the OTHER owner asked for. On the 2026-10-26
    # corpus the similarity engine broke an owner's stated ceiling in 73% of
    # its matches and recovered 1 of the 7 pairs brokers had kept; the swap
    # scorer breaks none and recovers all 7. See `permuta.py`'s header.
    matches: list[dict] = []
    sem_semantica = 0
    for origem, destino in pares:
        if destino["natureza"] == "permuta_automovel":
            # A car is not a property: no type/place to cross-check, so it
            # keeps the vehicle branch of the similarity engine.
            encontrado = next(iter(gerar_matches_para_imovel(origem, [destino], score_minimo)), None)
        else:
            encontrado = emitir_permuta(origem, destino, score_minimo)
        if not encontrado:
            continue
        matches.append(encontrado)
        if falta_vetor_bilateral(origem, destino):
            sem_semantica += 1

    gravados = _upsert_matches(client, org_id, matches)

    # A full scan is the whole truth about which suggestions still hold; a
    # narrowed one (`ativo_id`) is not, so only a full scan prunes. Without
    # this, a pair the engine stopped producing (an owner now recognised as
    # the same on both sides, a de-listed imóvel, a score that fell under the
    # bar) stays in the "Sugerido" column forever — 128 → 193 on the
    # 2026-10-12 live smoke. Never prunes when nothing was evaluated (an empty
    # catalog read must not read as "every suggestion is stale").
    obsoletos = 0
    if not ativo_id and imoveis:
        obsoletos = _remover_sugestoes_obsoletas(client, org_id, matches)

    logger.info(
        "permutas.gerar_matches org=%s imoveis=%d permutas=%d encontrados=%d "
        "gravados=%d obsoletos=%d sem_semantica=%d nao_resolvidos=%d",
        org_id, len(imoveis), len(permutas), len(matches), gravados,
        obsoletos, sem_semantica, len(nao_resolvidos),
    )

    return {
        "encontrados": len(matches),
        "gravados": gravados,
        "protegidos": len(matches) - gravados,
        "removidos_obsoletos": obsoletos,
        "imoveis_avaliados": len(imoveis),
        "permutas_avaliadas": len(permutas),
        # 🔴 SURFACED, NOT LOGGED. A run with no embeddings still returns a
        # full list of plausible matches, so "the AI half never ran" is
        # invisible in the output — which is exactly how erp shipped a dead
        # composite path for months. The page renders this as a banner.
        "sem_semantica": sem_semantica,
        # Intents whose catalog listing has been de-listed. Silently dropping
        # them reads as "this property has no matches".
        "imoveis_nao_resolvidos": nao_resolvidos,
    }


def _upsert_matches(client: Any, org_id: UUID, matches: list[dict]) -> int:
    """Persist scored pairs; never touch one a person has decided.

    🔴 THE PROTECTION IS THE POINT. A re-run that reset `rejeitado` back to
    `sugerido` would put every discarded match back in front of the team on
    the next scan, and they would discard them again, forever. The legacy
    funnel closed 74 of 82 matches as rejected — that is the bulk of the
    table, and it is exactly the part a naive upsert would resurrect.
    """
    if not matches:
        return 0

    origem_ids = list({m["ativo_origem_id"] for m in matches})
    existentes = (
        _t(client, MATCHES)
        .select("ativo_origem_id,ativo_destino_id,etapa")
        .eq("org_id", str(org_id))
        .in_("ativo_origem_id", origem_ids)
        .neq("etapa", ETAPA_INICIAL)
        .execute()
    ).data or []
    protegidos = {
        (r["ativo_origem_id"], r["ativo_destino_id"]) for r in existentes
    }

    linhas = []
    for m in matches:
        if (m["ativo_origem_id"], m["ativo_destino_id"]) in protegidos:
            continue
        linhas.append({
            "org_id": str(org_id),
            "ativo_origem_id": m["ativo_origem_id"],
            "ativo_destino_id": m["ativo_destino_id"],
            "score": m["score"],
            "justificativa": m["justificativa"],
            "detalhes": m["detalhes"],
            "score_breakdown": m["score_breakdown"],
            "is_bilateral": bool(m["detalhes"].get("embedding_similarity")),
            "etapa": ETAPA_INICIAL,
            "origem": "motor",
        })

    if not linhas:
        return 0

    _t(client, MATCHES).upsert(
        linhas, on_conflict="org_id,ativo_origem_id,ativo_destino_id"
    ).execute()
    return len(linhas)


def _remover_sugestoes_obsoletas(client: Any, org_id: UUID, matches: list[dict]) -> int:
    """Delete engine suggestions this full scan no longer produced.

    Only `etapa='sugerido'` AND `origem='motor'` rows: a person's decision
    (any later etapa) and an imported legacy row are never touched — the same
    protection `_upsert_matches` gives them.
    """
    vigentes = {(m["ativo_origem_id"], m["ativo_destino_id"]) for m in matches}
    linhas = (
        _t(client, MATCHES)
        .select("id,ativo_origem_id,ativo_destino_id")
        .eq("org_id", str(org_id))
        .eq("etapa", ETAPA_INICIAL)
        .eq("origem", "motor")
        .execute()
    ).data or []
    ids = [
        r["id"] for r in linhas
        if (r["ativo_origem_id"], r["ativo_destino_id"]) not in vigentes
    ]
    for i in range(0, len(ids), 200):
        (
            _t(client, MATCHES)
            .delete()
            .eq("org_id", str(org_id))
            .in_("id", ids[i:i + 200])
            .execute()
        )
    return len(ids)


MATCH_FIELDS = (
    "id,ativo_origem_id,ativo_destino_id,score,justificativa,detalhes,"
    "score_breakdown,is_bilateral,etapa,observacoes,origem,created_at,"
    "updated_at,decidido_por,decidido_em,"
    "motivo_rejeicao,motivo_rejeicao_detalhe,motivo_lado"
)


def listar_matches(
    client: Any,
    org_id: UUID,
    *,
    etapa: Optional[str] = None,
    ativo_id: Optional[UUID] = None,
    score_minimo: Optional[float] = None,
) -> dict:
    """Matches for the page, best first, with both sides resolved for display.

    Both sides are batched (two queries, then one catalog query), never
    fetched per row — a 500-match list would otherwise be 1000 round-trips.
    """
    q = (
        _t(client, MATCHES)
        .select(MATCH_FIELDS)
        .eq("org_id", str(org_id))
        .order("score", desc=True)
    )
    if etapa:
        q = q.eq("etapa", etapa)
    if score_minimo is not None:
        q = q.gte("score", score_minimo)
    if ativo_id:
        # Either side — from the page, "matches for this property" means the
        # property in whichever role it holds.
        q = q.or_(
            f"ativo_origem_id.eq.{ativo_id},ativo_destino_id.eq.{ativo_id}"
        )

    matches = (q.execute()).data or []
    if not matches:
        return {"items": [], "total": 0}

    ids = {m["ativo_origem_id"] for m in matches} | {m["ativo_destino_id"] for m in matches}
    resumos = _resumos_de_ativos(client, org_id, list(ids))

    for m in matches:
        m["ativo_origem"] = resumos.get(m["ativo_origem_id"])
        m["ativo_destino"] = resumos.get(m["ativo_destino_id"])

    return {"items": matches, "total": len(matches)}


def _resumos_de_ativos(client: Any, org_id: UUID, ids: list[str]) -> dict[str, dict]:
    """Display summaries for a set of ativos, catalog data folded in."""
    rows = (
        _t(client, ATIVOS)
        .select(
            "id,natureza,imovel_codigo,codigo,valor,tipo_imovel,cidade,bairro,"
            "uf,zona,quartos,vagas,area_total,condominio_nome,observacoes,"
            "corretor_id,proprietario_nome"
        )
        .eq("org_id", str(org_id))
        .in_("id", ids)
        .execute()
    ).data or []

    codigos = [r["imovel_codigo"] for r in rows if r.get("imovel_codigo")]
    catalogo: dict[str, dict] = {}
    if codigos:
        catalogo = {
            i["codigo"]: i
            for i in (
                _t(client, "imoveis")
                .select(adapter.IMOVEL_FIELDS)
                .eq("org_id", str(org_id))
                .in_("codigo", codigos)
                .execute()
            ).data or []
        }

    saida: dict[str, dict] = {}
    for row in rows:
        imovel = catalogo.get(row.get("imovel_codigo") or "")
        if imovel:
            # The catalog wins on every field it owns — it is the synced
            # source of truth, and the intent row's copies are placeholders.
            row = {
                **row,
                "titulo": imovel.get("titulo"),
                "tipo_imovel": imovel.get("categoria") or row.get("tipo_imovel"),
                "cidade": imovel.get("cidade") or row.get("cidade"),
                "bairro": imovel.get("bairro") or row.get("bairro"),
                "uf": imovel.get("uf") or row.get("uf"),
                "valor": imovel.get("valor_venda") or row.get("valor"),
                "quartos": imovel.get("dormitorios") or row.get("quartos"),
                "vagas": imovel.get("vagas") or row.get("vagas"),
                "area_total": imovel.get("area_total") or row.get("area_total"),
                "condominio_nome": imovel.get("empreendimento") or row.get("condominio_nome"),
                "foto": imovel.get("foto_destaque"),
                "corretores": imovel.get("corretores") or [],
            }
        saida[row["id"]] = row
    return saida


def _validar_motivo(
    etapa: str,
    motivo: Optional[str],
    detalhe: Optional[str],
    lado: Optional[str],
) -> dict[str, Optional[str]]:
    """The three motivo columns to write for this move (all None unless rejecting)."""
    vazio: dict[str, Optional[str]] = {
        "motivo_rejeicao": None, "motivo_rejeicao_detalhe": None, "motivo_lado": None,
    }
    detalhe = (detalhe or "").strip() or None
    if etapa != ETAPA_REJEITADO:
        if motivo is not None or detalhe is not None or lado is not None:
            raise ValidationError("Motivo só se aplica a uma rejeição.")
        return vazio
    if not motivo:
        raise ValidationError("Informe o motivo da rejeição.")
    if motivo not in MOTIVOS_CODIGOS:
        raise ValidationError("Motivo de rejeição inválido.")
    if motivo == "outro" and not detalhe:
        raise ValidationError("Descreva o motivo da rejeição.")
    if lado is not None and lado not in MOTIVO_LADOS:
        raise ValidationError("Lado do motivo inválido. Use origem, destino ou ambos.")
    return {
        "motivo_rejeicao": motivo,
        "motivo_rejeicao_detalhe": detalhe,
        "motivo_lado": lado,
    }


def atualizar_etapa(
    client: Any,
    org_id: UUID,
    match_id: UUID,
    *,
    etapa: str,
    observacoes: Optional[str] = None,
    user_id: Optional[UUID] = None,
    motivo_rejeicao: Optional[str] = None,
    motivo_rejeicao_detalhe: Optional[str] = None,
    motivo_lado: Optional[str] = None,
) -> dict:
    """Move a match through the funnel.

    Rejecting requires a `motivo_rejeicao` (the tuning label); any other move
    clears the three motivo columns and refuses to accept them.

    Stamps `decidido_por`/`decidido_em` on anything leaving `sugerido`, which
    is what makes the row permanently exempt from the generator's upsert.
    """
    if etapa not in ETAPAS:
        raise ValidationError(
            f"Etapa inválida. Use uma de: {', '.join(ETAPAS)}."
        )

    motivo = _validar_motivo(
        etapa, motivo_rejeicao, motivo_rejeicao_detalhe, motivo_lado
    )

    atuais = (
        _t(client, MATCHES)
        .select("id,etapa")
        .eq("org_id", str(org_id))
        .eq("id", str(match_id))
        .limit(1)
        .execute()
    ).data or []
    if not atuais:
        raise NotFoundError("Match não encontrado.")

    updates: dict[str, Any] = {"etapa": etapa, **motivo}
    if observacoes is not None:
        updates["observacoes"] = observacoes
    if etapa != ETAPA_INICIAL:
        updates["decidido_por"] = str(user_id) if user_id else None
        # An ISO string, not the literal "now()" — this goes over PostgREST as
        # JSON, where a function name is just text and would fail the column's
        # timestamptz parse (or, worse on a lenient driver, land as a string).
        updates["decidido_em"] = datetime.now(timezone.utc).isoformat()
    else:
        # Moved back to sugerido — hand it back to the engine, including the
        # right to re-score it. Leaving the stamp would keep it protected
        # forever and quietly freeze a stale score.
        updates["decidido_por"] = None
        updates["decidido_em"] = None

    _t(client, MATCHES).update(updates).eq("org_id", str(org_id)).eq(
        "id", str(match_id)
    ).execute()

    rows = (
        _t(client, MATCHES)
        .select(MATCH_FIELDS)
        .eq("org_id", str(org_id))
        .eq("id", str(match_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else {}


__all__ = [
    "ATIVO_EDITAVEL",
    "MOTIVOS_REJEICAO",
    "ETAPAS",
    "INTERESSE_EDITAVEL",
    "atualizar_ativo",
    "atualizar_etapa",
    "criar_ativo",
    "gerar_matches",
    "listar_ativos",
    "listar_matches",
    "obter_ativo",
    "remover_ativo",
]
