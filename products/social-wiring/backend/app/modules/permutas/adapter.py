"""Projects this product's rows into the shared scorer's vocabulary.

🔴 THIS FILE IS THE WHOLE REASON THE ENGINE COULD BE SHARED.

``noctusai_lib.domain.real_estate.matching`` scores two plain dicts and knows
nothing about either product's storage. erp hands it rows straight out of one
wide ``ativos`` table. This product cannot: the property data lives in
``social_wiring.imoveis``, which is Vista's mirror — 2065 rows, resynced on a
schedule, and NOT ours to write. The swap intent lives in
``permuta_ativos``/``permuta_interesses``, which are ours.

So the ``imovel`` side of every pair is assembled at read time from two rows,
and this module is where the two vocabularies are reconciled. Getting it wrong
is silent: a mis-mapped field does not raise, it just scores zero forever and
the matches quietly get worse.

THE MAPPING, AND THE FOUR PLACES THE NAMES DISAGREE
───────────────────────────────────────────────────
    scorer            social_wiring.imoveis        why it differs
    ─────────────────────────────────────────────────────────────────────
    valor             valor_venda                  Vista splits venda/locação
    estado            uf                           Vista's own column name
    quartos           dormitorios                  Vista's own column name
    tipo_imovel       categoria                    Vista's own column name
    titulo_anuncio    titulo
    descricao_seo     descricao_web
    tour_virtual_url  tour_360
    condominio_nome   empreendimento               Vista has no condo entity

Everything else lines up by name. `pontos_de_interesse` has no Vista
equivalent and is left absent rather than faked from `caracteristicas` — the
scorer gives it one listing-quality point, and inventing a value to collect it
would flatter every listing equally, which is the same as scoring nobody.

🔴 `aceita_permutas` IS DERIVED, NOT READ.
``imoveis.aceita_permuta`` exists and is NULL on all 2065 rows — Vista has
never populated it. Reading it would make `gerar_matches_para_permuta` skip
every listing (it hard-requires the flag) and return zero matches while
reporting success. The truthful source is this product's own registry: a
listing has an intent row in `permuta_ativos`, therefore its owner accepts a
swap. That is what the flag means and it is the only place we actually know it.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"

#: Only what the scorer reads, plus `codigo` to join on. Explicit rather than
#: `*` so widening `imoveis` (69 columns and growing) cannot silently widen
#: every matching query.
IMOVEL_FIELDS = (
    "codigo,titulo,categoria,status,cidade,bairro,uf,zona,regiao,empreendimento,"
    "valor_venda,area_total,area_privativa,dormitorios,suites,vagas,"
    "descricao_web,fotos,foto_destaque,tour_360,caracteristicas,corretores"
)

ATIVO_FIELDS = (
    "id,org_id,natureza,imovel_codigo,codigo,corretor_id,"
    "proprietario_nome,proprietario_telefone,proprietario_email,"
    "tipo_imovel,cep,logradouro,numero,bairro,cidade,uf,zona,condominio_nome,"
    "valor,area_total,area_privativa,quartos,suites,vagas,"
    "faixa_preco_min,faixa_preco_max,regiao_preferida,"
    "aceita_completar_diferenca,limite_complemento,percentual_min,percentual_max,"
    "observacoes,interesses_descricao,status,origem,origem_id,"
    "embedding,embedding_interesses"
)

INTERESSE_FIELDS = (
    "id,ativo_id,tipo,tipo_imovel,zona,cidade,bairro,"
    "valor_minimo,valor_maximo,percentual_min,percentual_max,"
    "marca,modelo,ano_min,ano_max,observacoes"
)


def _f(value: Any) -> Optional[float]:
    """Numeric columns arrive as Decimal or str from the driver."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def interesse_para_scorer(row: dict) -> dict:
    """One `permuta_interesses` row in the shape the scorer's gate reads.

    The scorer calls these `valor_min`/`valor_max`; the table calls them
    `valor_minimo`/`valor_maximo` to match every other value band in this
    schema (`atendimento_negociacao`, `agentes_financeiros`). The rename lives
    here rather than in the column names, because the schema's internal
    consistency outlives any one consumer's vocabulary.
    """
    return {
        "tipo": row.get("tipo") or "imovel",
        "tipo_imovel": row.get("tipo_imovel"),
        "cidade": row.get("cidade"),
        "bairro": row.get("bairro"),
        "zona": row.get("zona"),
        "valor_min": _f(row.get("valor_minimo")),
        "valor_max": _f(row.get("valor_maximo")),
        "marca": row.get("marca"),
        "modelo": row.get("modelo"),
        "observacoes": row.get("observacoes"),
    }


def ativo_para_scorer(
    ativo: dict,
    *,
    imovel: Optional[dict] = None,
    interesses: Iterable[dict] = (),
) -> Optional[dict]:
    """Build the scorer's dict for one ativo.

    Returns ``None`` for a `natureza='imovel'` row whose catalog listing could
    not be resolved.

    🔴 NONE, NOT A STUB. An `imovel` ativo carries no specs of its own — every
    one of them lives in `imoveis`. Emitting the row anyway would put a
    property with no price, no area and no location into the candidate pool,
    where the scorer would rate it against everything and the hard gate would
    reject it for reasons that have nothing to do with the actual property.
    The caller counts these and reports them; see `listar_ativos_para_scorer`.
    """
    natureza = ativo.get("natureza")
    lista_interesses = [interesse_para_scorer(i) for i in interesses]

    base = {
        "id": ativo["id"],
        "natureza": natureza,
        "status": ativo.get("status") or "ativo",
        "interesses": lista_interesses,
        "embedding": ativo.get("embedding"),
        "embedding_interesses": ativo.get("embedding_interesses"),
        # The scorer excludes a pair whose two sides share an owner. This
        # product has no owner identity on either side yet (the legacy
        # `proprietario` rows are deliberately not promoted to `clientes` —
        # see migration 101), so the key is left absent. The lib's guard
        # requires a TRUTHY owner_id before it excludes anything, precisely so
        # an absent one does not silently exclude every pair.
        "owner_id": None,
    }

    if natureza == "imovel":
        if not imovel:
            return None
        return {
            **base,
            # 🔴 DERIVED — see the module header. The stored column is NULL on
            # every Vista row; the intent row IS the acceptance.
            "aceita_permutas": True,
            "tipo_imovel": imovel.get("categoria"),
            "cidade": imovel.get("cidade"),
            "bairro": imovel.get("bairro"),
            "estado": imovel.get("uf"),
            "zona": imovel.get("zona") or imovel.get("regiao"),
            "valor": _f(imovel.get("valor_venda")),
            "area_total": _f(imovel.get("area_total")),
            "area_privativa": _f(imovel.get("area_privativa")),
            "quartos": imovel.get("dormitorios"),
            "suites": imovel.get("suites"),
            "vagas": imovel.get("vagas"),
            "titulo_anuncio": imovel.get("titulo"),
            "descricao_seo": imovel.get("descricao_web"),
            "fotos": imovel.get("fotos") or [],
            "tour_virtual_url": imovel.get("tour_360"),
            "condominio_nome": imovel.get("empreendimento"),
            # The bands and the prose stay on OUR row even for the imóvel
            # side: they are the intent, not the property.
            "faixa_preco_min": _f(ativo.get("faixa_preco_min")),
            "faixa_preco_max": _f(ativo.get("faixa_preco_max")),
            "regiao_preferida": ativo.get("regiao_preferida") or [],
            "aceita_completar_diferenca": ativo.get("aceita_completar_diferenca"),
        }

    # `permuta_imovel` / `permuta_automovel` — everything is ours, because a
    # property a client brings is frequently not in the catalog at all.
    return {
        **base,
        "tipo_imovel": ativo.get("tipo_imovel"),
        "cidade": ativo.get("cidade"),
        "bairro": ativo.get("bairro"),
        "estado": ativo.get("uf"),
        "zona": ativo.get("zona"),
        "valor": _f(ativo.get("valor")),
        "area_total": _f(ativo.get("area_total")),
        "area_privativa": _f(ativo.get("area_privativa")),
        "quartos": ativo.get("quartos"),
        "suites": ativo.get("suites"),
        "vagas": ativo.get("vagas"),
        "condominio_nome": ativo.get("condominio_nome"),
        "faixa_preco_min": _f(ativo.get("faixa_preco_min")),
        "faixa_preco_max": _f(ativo.get("faixa_preco_max")),
        "regiao_preferida": ativo.get("regiao_preferida") or [],
        "aceita_completar_diferenca": ativo.get("aceita_completar_diferenca"),
    }


def listar_ativos_para_scorer(
    client: Any,
    org_id: str,
    *,
    natureza: Optional[list[str]] = None,
    apenas_ativos: bool = True,
) -> tuple[list[dict], list[str]]:
    """Every matchable ativo for an org, already in the scorer's shape.

    Returns ``(ativos, codigos_nao_resolvidos)``.

    🔴 THE SECOND ELEMENT IS NOT DECORATION. An `imovel` intent whose listing
    has left the catalog (Vista de-lists, and 52 of the legacy refs are
    already gone) drops out of matching entirely. Silently, that reads as "no
    matches for this property" — indistinguishable from a real answer. Handing
    the codes back makes the caller say how many were skipped, which is what
    turns an invisible shrinkage into a number someone can act on.

    Three queries, never N+1: the ativos, their interests, and one batched
    `in_` over the catalog.
    """
    q = client.schema(SCHEMA).table("permuta_ativos").select(ATIVO_FIELDS).eq("org_id", org_id)
    if natureza:
        q = q.in_("natureza", natureza)
    if apenas_ativos:
        q = q.eq("status", "ativo")
    ativos = (q.execute()).data or []
    if not ativos:
        return [], []

    ids = [a["id"] for a in ativos]
    interesses_rows = (
        client.schema(SCHEMA)
        .table("permuta_interesses")
        .select(INTERESSE_FIELDS)
        .in_("ativo_id", ids)
        .execute()
    ).data or []
    por_ativo: dict[str, list[dict]] = {}
    for row in interesses_rows:
        por_ativo.setdefault(row["ativo_id"], []).append(row)

    codigos = [a["imovel_codigo"] for a in ativos if a.get("imovel_codigo")]
    imoveis_por_codigo: dict[str, dict] = {}
    if codigos:
        imoveis = (
            client.schema(SCHEMA)
            .table("imoveis")
            .select(IMOVEL_FIELDS)
            .eq("org_id", org_id)
            .in_("codigo", codigos)
            .execute()
        ).data or []
        imoveis_por_codigo = {i["codigo"]: i for i in imoveis}

    saida: list[dict] = []
    nao_resolvidos: list[str] = []
    for ativo in ativos:
        codigo = ativo.get("imovel_codigo")
        projetado = ativo_para_scorer(
            ativo,
            imovel=imoveis_por_codigo.get(codigo) if codigo else None,
            interesses=por_ativo.get(ativo["id"], []),
        )
        if projetado is None:
            nao_resolvidos.append(codigo or ativo["id"])
            continue
        saida.append(projetado)

    if nao_resolvidos:
        logger.warning(
            "permutas: %d intenção(ões) sem imóvel no catálogo, fora do matching: %s",
            len(nao_resolvidos),
            ", ".join(nao_resolvidos[:10]),
        )

    return saida, nao_resolvidos


def texto_para_embedding(ativo_scorer: dict) -> str:
    """The prose that represents what this ativo IS.

    Built from the projected dict rather than the raw row, so the imóvel side
    describes the CATALOG listing (which has areas, rooms and a description)
    and not the near-empty intent row that points at it.
    """
    partes: list[str] = []
    if ativo_scorer.get("tipo_imovel"):
        partes.append(f"Tipo: {ativo_scorer['tipo_imovel']}")

    local = ", ".join(
        p for p in (
            ativo_scorer.get("bairro"),
            ativo_scorer.get("cidade"),
            ativo_scorer.get("estado"),
        ) if p
    )
    if local:
        partes.append(f"Localização: {local}")
    if ativo_scorer.get("condominio_nome"):
        partes.append(f"Condomínio: {ativo_scorer['condominio_nome']}")

    area = ativo_scorer.get("area_privativa") or ativo_scorer.get("area_total")
    if area:
        partes.append(f"Área: {area}m²")
    for rotulo, chave in (("Quartos", "quartos"), ("Suítes", "suites"), ("Vagas", "vagas")):
        if ativo_scorer.get(chave):
            partes.append(f"{rotulo}: {ativo_scorer[chave]}")
    if ativo_scorer.get("valor"):
        partes.append(f"Valor: R$ {ativo_scorer['valor']:,.0f}".replace(",", "."))
    if ativo_scorer.get("titulo_anuncio"):
        partes.append(f"Título: {ativo_scorer['titulo_anuncio']}")
    if ativo_scorer.get("descricao_seo"):
        partes.append(f"Descrição: {ativo_scorer['descricao_seo']}")

    return " | ".join(partes)


def texto_interesses_para_embedding(ativo: dict, interesses: Iterable[dict]) -> str:
    """The prose that represents what this ativo WANTS.

    🔴 `observacoes` LEADS, and that ordering is the point of the whole
    feature. In the corpus this was built for, the structured criteria are
    nearly empty — `cidade` set on 0 of 135 legacy interest rows — while the
    sentence carries the real constraint: "casa sem escada", "rua do
    condomínio sem ladeira", "quintal amplo", "aceite 100 por cento da
    permuta". Appending the prose after a list of mostly-null fields would
    bury the only signal that exists behind padding the model has to ignore.
    """
    partes: list[str] = []

    texto_livre = (ativo.get("observacoes") or "").strip()
    if texto_livre:
        partes.append(texto_livre)

    for interesse in interesses:
        obs = (interesse.get("observacoes") or "").strip()
        if obs and obs != texto_livre:
            partes.append(obs)

        criterios: list[str] = []
        if interesse.get("tipo_imovel"):
            criterios.append(f"tipo {interesse['tipo_imovel']}")
        for chave in ("cidade", "bairro", "zona"):
            if interesse.get(chave):
                criterios.append(f"{chave} {interesse[chave]}")
        vmin, vmax = _f(interesse.get("valor_minimo")), _f(interesse.get("valor_maximo"))
        if vmax:
            criterios.append(
                f"valor entre R$ {vmin or 0:,.0f} e R$ {vmax:,.0f}".replace(",", ".")
            )
        pmin, pmax = interesse.get("percentual_min"), interesse.get("percentual_max")
        if pmin or pmax:
            criterios.append(f"permuta cobrindo de {pmin or 0}% a {pmax or 100}% do valor")
        if criterios:
            partes.append("Procura: " + ", ".join(criterios))

    if not partes:
        # An ativo that stated nothing has no interest vector. Returning "" (as
        # opposed to a generic "procura imóvel") keeps the caller from
        # embedding a sentence that would sit at a similar distance from every
        # listing and manufacture bilateral matches out of nothing.
        return ""

    return " | ".join(partes)


__all__ = [
    "ATIVO_FIELDS",
    "IMOVEL_FIELDS",
    "INTERESSE_FIELDS",
    "ativo_para_scorer",
    "interesse_para_scorer",
    "listar_ativos_para_scorer",
    "texto_interesses_para_embedding",
    "texto_para_embedding",
]
