"""Condomínios -- suggest, list with stats, edit, validate/discard, merge.

Every call takes the `social_wiring`-scoped ADMIN client (the imovel_hub seam),
so RLS is bypassed and EVERY query carries ``org_id`` explicitly. The Vista
mirror (``imoveis``) and ``imovel_dados`` are only ever READ here.

Resolution of an imóvel to a condomínio mirrors the ``condominio_imoveis`` view
(migration 265): ``alias_key(imovel_dados.empreendimento_manual or
imoveis.empreendimento)`` looked up in ``condominio_aliases``.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError, ValidationError_

from app.modules.condominios import normalizacao as norm
from app.services.table_reads import paged_rows, table

CONDOMINIOS = "condominios"
ALIASES = "condominio_aliases"
EVENTOS = "condominio_eventos"

ATRIBUTOS_EDITAVEL = (
    "cidade", "bairro", "tipo", "seguranca_nivel", "portaria_24h", "area_lazer",
    "distancia_raposo_km", "acesso_principal", "observacoes", "latitude", "longitude",
)
TIPOS = ("horizontal", "vertical", "loteamento", "misto")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evento(client: Any, org_id: UUID, condominio_id: str, tipo: str, ator: Optional[UUID], **detalhes: Any) -> None:
    table(client, EVENTOS).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "condominio_id": str(condominio_id),
            "tipo": tipo,
            "ator": str(ator) if ator else None,
            "detalhes": detalhes,
        }
    ).execute()


def _get(client: Any, org_id: UUID, condominio_id: UUID) -> dict:
    rows = (
        table(client, CONDOMINIOS).select("*")
        .eq("org_id", str(org_id)).eq("id", str(condominio_id)).execute()
    ).data or []
    if not rows:
        raise NotFoundError("Condomínio não encontrado.")
    return rows[0]


# ── Reading the mirror ──────────────────────────────────────────────────────


def _imoveis_com_empreendimento(client: Any, org_id: UUID) -> list[dict]:
    """Every imóvel (mirror + manual-only) with the empreendimento that applies
    (manual wins) and the fields the stats need."""
    mirror = paged_rows(
        client, "imoveis", org_id, order_col="codigo_norm", id_key="codigo_norm",
        select="codigo_norm,empreendimento,cidade,bairro,latitude,longitude,status,"
               "valor_venda,area_privativa,area_total",
    )
    dados = paged_rows(
        client, "imovel_dados", org_id, order_col="codigo", id_key="codigo",
        select="codigo,empreendimento_manual",
    )
    manual = {
        (d["codigo"] or "").strip().upper(): d.get("empreendimento_manual")
        for d in dados
        if (d.get("empreendimento_manual") or "").strip()
    }
    out: list[dict] = []
    vistos = set()
    for r in mirror:
        cod = r["codigo_norm"]
        vistos.add(cod)
        out.append({**r, "empreendimento_efetivo": manual.get(cod) or r.get("empreendimento")})
    for cod, emp in manual.items():
        if cod not in vistos:
            out.append({"codigo_norm": cod, "empreendimento_efetivo": emp, "so_manual": True})
    return out


def _preco_m2(imovel: dict) -> Optional[float]:
    valor = imovel.get("valor_venda")
    area = imovel.get("area_privativa") or imovel.get("area_total")
    try:
        if valor and area and float(area) > 0:
            return float(valor) / float(area)
    except (TypeError, ValueError):
        return None
    return None


# ── Suggest ─────────────────────────────────────────────────────────────────


def sugerir(client: Any, org_id: UUID, ator: Optional[UUID]) -> dict:
    """Build `sugerido` condomínios from the distinct empreendimento spellings.

    Idempotent: a spelling that already has an alias is never re-assigned; a
    new spelling joins an existing condomínio of the same name+cidade (adding
    an alias only -- no field of a validated row is ever written) or founds a
    new `sugerido` one.
    """
    imoveis = _imoveis_com_empreendimento(client, org_id)
    aliases_existentes = {
        a["alias_normalizado"]: a["condominio_id"]
        for a in paged_rows(client, ALIASES, org_id, select="id,alias_normalizado,condominio_id")
    }

    obs: dict[str, norm.Observacao] = {}
    spellings: dict[str, Counter] = {}
    lat_lng: dict[str, list[tuple[float, float]]] = {}
    for im in imoveis:
        raw = im.get("empreendimento_efetivo")
        chave = norm.alias_key(raw)
        if not chave:
            continue
        o = obs.setdefault(chave, norm.Observacao(alias=chave, chave=chave))
        o.total += 1
        spellings.setdefault(chave, Counter())[norm._WS.sub(" ", raw.strip())] += 1
        if im.get("cidade"):
            o.cidades[im["cidade"].strip()] += 1
        if im.get("bairro"):
            o.bairros[im["bairro"].strip()] += 1
        if im.get("latitude") is not None and im.get("longitude") is not None:
            lat_lng.setdefault(chave, []).append((float(im["latitude"]), float(im["longitude"])))
    for chave, o in obs.items():
        o.alias = spellings[chave].most_common(1)[0][0]

    novas = [o for k, o in obs.items() if k not in aliases_existentes]

    existentes = {
        (c["nome_normalizado"], norm._cidade_key(c.get("cidade"))): c
        for c in paged_rows(client, CONDOMINIOS, org_id)
    }

    criados = anexados = 0
    for cluster in norm.agrupar(novas):
        chave_cond = cluster.chave
        alvo = existentes.get((chave_cond, norm._cidade_key(cluster.cidade)))
        if alvo is None:
            pontos = [p for m in cluster.membros for p in lat_lng.get(m.chave, [])]
            linha = {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "nome": cluster.principal.alias,
                "nome_normalizado": chave_cond,
                "cidade": cluster.cidade,
                "bairro": cluster.bairro,
                "status_validacao": "sugerido",
                "latitude": round(statistics.fmean(p[0] for p in pontos), 6) if pontos else None,
                "longitude": round(statistics.fmean(p[1] for p in pontos), 6) if pontos else None,
            }
            alvo = table(client, CONDOMINIOS).insert(linha).execute().data[0]
            existentes[(chave_cond, norm._cidade_key(cluster.cidade))] = alvo
            _evento(client, org_id, alvo["id"], "sugerido", ator, aliases=[m.alias for m in cluster.membros])
            criados += 1
        else:
            anexados += len(cluster.membros)
        for m in cluster.membros:
            table(client, ALIASES).insert(
                {
                    "id": str(uuid4()), "org_id": str(org_id), "condominio_id": alvo["id"], "alias": m.alias,
                    "alias_normalizado": m.chave, "origem": "sugestao",
                }
            ).execute()
    return {
        "empreendimentos_distintos": len(obs),
        "aliases_novos": len(novas),
        "condominios_criados": criados,
        "aliases_em_existentes": anexados,
    }


# ── Reads ───────────────────────────────────────────────────────────────────


def _stats(client: Any, org_id: UUID) -> tuple[dict[str, dict], list[dict]]:
    aliases = paged_rows(client, ALIASES, org_id, select="id,condominio_id,alias,alias_normalizado,origem,created_at")
    por_chave = {a["alias_normalizado"]: a["condominio_id"] for a in aliases}
    acc: dict[str, dict] = {}
    for im in _imoveis_com_empreendimento(client, org_id):
        cid = por_chave.get(norm.alias_key(im.get("empreendimento_efetivo")) or "")
        if not cid:
            continue
        s = acc.setdefault(cid, {"imoveis": 0, "ativos": 0, "precos": [], "aliases_imoveis": Counter()})
        s["imoveis"] += 1
        s["aliases_imoveis"][norm.alias_key(im.get("empreendimento_efetivo"))] += 1
        if im.get("valor_venda"):
            s["ativos"] += 1
        p = _preco_m2(im)
        if p is not None:
            s["precos"].append(p)
    return acc, aliases


def _saida(c: dict, s: Optional[dict], n_aliases: int) -> dict:
    s = s or {"imoveis": 0, "ativos": 0, "precos": []}
    return {
        **c,
        "imoveis_count": s["imoveis"],
        "anuncios_venda_count": s["ativos"],
        "preco_m2_mediano": round(statistics.median(s["precos"]), 2) if s["precos"] else None,
        "aliases_count": n_aliases,
    }


def listar(client: Any, org_id: UUID, *, status: Optional[str] = None, cidade: Optional[str] = None,
           q: Optional[str] = None) -> dict:
    stats, aliases = _stats(client, org_id)
    n_alias = Counter(a["condominio_id"] for a in aliases)
    itens = []
    for c in paged_rows(client, CONDOMINIOS, org_id):
        if status and c["status_validacao"] != status:
            continue
        if cidade and (c.get("cidade") or "").strip().upper() != cidade.strip().upper():
            continue
        if q and norm.match_key(q) and norm.match_key(q) not in (c["nome_normalizado"] or "") \
                and q.strip().upper() not in (c["nome"] or "").upper():
            continue
        itens.append(_saida(c, stats.get(c["id"]), n_alias.get(c["id"], 0)))
    itens.sort(key=lambda x: (-x["imoveis_count"], x["nome"] or ""))
    return {"items": itens, "total": len(itens)}


def obter(client: Any, org_id: UUID, condominio_id: UUID) -> dict:
    c = _get(client, org_id, condominio_id)
    stats, aliases = _stats(client, org_id)
    s = stats.get(c["id"])
    meus = [a for a in aliases if a["condominio_id"] == c["id"]]
    contagem = (s or {}).get("aliases_imoveis", Counter())
    eventos = (
        table(client, EVENTOS).select("*").eq("org_id", str(org_id))
        .eq("condominio_id", c["id"]).order("created_at", desc=True).execute()
    ).data or []
    return {
        **_saida(c, s, len(meus)),
        "aliases": sorted(
            ({**a, "imoveis_count": contagem.get(a["alias_normalizado"], 0)} for a in meus),
            key=lambda a: -a["imoveis_count"],
        ),
        "eventos": eventos,
    }


# ── Writes ──────────────────────────────────────────────────────────────────


def atualizar(client: Any, org_id: UUID, condominio_id: UUID, campos: dict, ator: Optional[UUID]) -> dict:
    c = _get(client, org_id, condominio_id)
    patch = {k: v for k, v in campos.items() if k in ATRIBUTOS_EDITAVEL}
    if "tipo" in patch and patch["tipo"] is not None and patch["tipo"] not in TIPOS:
        raise ValidationError_(f"tipo deve ser um de {', '.join(TIPOS)}.")
    if not patch:
        return c
    table(client, CONDOMINIOS).update(patch).eq("org_id", str(org_id)).eq("id", c["id"]).execute()
    _evento(client, org_id, c["id"], "update", ator, campos=patch)
    return _get(client, org_id, condominio_id)


def _transicao(client, org_id, condominio_id, ator, *, novo: str, evento: str, extra: Optional[dict] = None) -> dict:
    c = _get(client, org_id, condominio_id)
    if c["status_validacao"] == novo:
        raise ConflictError(f"O condomínio já está '{novo}'.")
    patch = {"status_validacao": novo, **(extra or {})}
    table(client, CONDOMINIOS).update(patch).eq("org_id", str(org_id)).eq("id", c["id"]).execute()
    _evento(client, org_id, c["id"], evento, ator, de=c["status_validacao"], para=novo)
    return _get(client, org_id, condominio_id)


def validar(client, org_id, condominio_id, ator) -> dict:
    return _transicao(client, org_id, condominio_id, ator, novo="validado", evento="validate",
                      extra={"validado_por": str(ator) if ator else None, "validado_em": _agora()})


def descartar(client, org_id, condominio_id, ator) -> dict:
    return _transicao(client, org_id, condominio_id, ator, novo="descartado", evento="discard")


def reabrir(client, org_id, condominio_id, ator) -> dict:
    return _transicao(client, org_id, condominio_id, ator, novo="sugerido", evento="reabrir",
                      extra={"validado_por": None, "validado_em": None})


def renomear(client, org_id, condominio_id, nome: str, ator) -> dict:
    nome = norm._WS.sub(" ", (nome or "").strip())
    chave = norm.match_key(nome)
    if not chave:
        raise ValidationError_("Informe um nome.")
    c = _get(client, org_id, condominio_id)
    clash = [
        r for r in (
            table(client, CONDOMINIOS).select("id,cidade").eq("org_id", str(org_id))
            .eq("nome_normalizado", chave).execute()
        ).data or []
        if r["id"] != c["id"] and norm._cidade_key(r.get("cidade")) == norm._cidade_key(c.get("cidade"))
    ]
    if clash:
        raise ConflictError("Já existe um condomínio com esse nome nessa cidade; use Fundir.")
    table(client, CONDOMINIOS).update({"nome": nome, "nome_normalizado": chave}) \
        .eq("org_id", str(org_id)).eq("id", c["id"]).execute()
    _evento(client, org_id, c["id"], "rename", ator, de=c["nome"], para=nome)
    return _get(client, org_id, condominio_id)


def fundir(client, org_id, origem_id: UUID, destino_id: UUID, ator) -> dict:
    """Re-point every alias of `origem` to `destino`; `origem` becomes
    `descartado` with `fundido_em_id` set. Reversible via :func:`desfazer_fusao`
    (the event records the alias ids that moved)."""
    if origem_id == destino_id:
        raise ValidationError_("Origem e destino são o mesmo condomínio.")
    origem = _get(client, org_id, origem_id)
    destino = _get(client, org_id, destino_id)
    if destino["status_validacao"] == "descartado":
        raise ConflictError("O destino está descartado.")
    if origem.get("fundido_em_id"):
        raise ConflictError("Este condomínio já foi fundido.")
    status_anterior = origem["status_validacao"]  # snapshot BEFORE the update below
    movidos = [
        a["id"] for a in (
            table(client, ALIASES).select("id").eq("org_id", str(org_id))
            .eq("condominio_id", origem["id"]).execute()
        ).data or []
    ]
    for aid in movidos:
        table(client, ALIASES).update({"condominio_id": destino["id"], "origem": "fusao"}) \
            .eq("org_id", str(org_id)).eq("id", aid).execute()
    table(client, CONDOMINIOS).update(
        {"status_validacao": "descartado", "fundido_em_id": destino["id"]}
    ).eq("org_id", str(org_id)).eq("id", origem["id"]).execute()
    detalhes = {"alias_ids": movidos, "origem_nome": origem["nome"], "destino_nome": destino["nome"],
                "origem_status_anterior": status_anterior}
    _evento(client, org_id, destino["id"], "merge", ator, origem_id=origem["id"], **detalhes)
    _evento(client, org_id, origem["id"], "merge", ator, destino_id=destino["id"], **detalhes)
    return {"origem": _get(client, org_id, origem_id), "destino": _get(client, org_id, destino_id),
            "aliases_movidos": len(movidos)}


def desfazer_fusao(client, org_id, origem_id: UUID, ator) -> dict:
    origem = _get(client, org_id, origem_id)
    destino_id = origem.get("fundido_em_id")
    if not destino_id:
        raise ConflictError("Este condomínio não foi fundido.")
    eventos = (
        table(client, EVENTOS).select("*").eq("org_id", str(org_id))
        .eq("condominio_id", origem["id"]).eq("tipo", "merge").order("created_at", desc=True).execute()
    ).data or []
    if not eventos:
        raise ConflictError("Sem registro da fusão para desfazer.")
    det = eventos[0].get("detalhes") or {}
    for aid in det.get("alias_ids", []):
        table(client, ALIASES).update({"condominio_id": origem["id"], "origem": "manual"}) \
            .eq("org_id", str(org_id)).eq("id", aid).execute()
    table(client, CONDOMINIOS).update(
        {"status_validacao": det.get("origem_status_anterior") or "sugerido", "fundido_em_id": None}
    ).eq("org_id", str(org_id)).eq("id", origem["id"]).execute()
    _evento(client, org_id, origem["id"], "desfazer_merge", ator, destino_id=destino_id, alias_ids=det.get("alias_ids", []))
    _evento(client, org_id, destino_id, "desfazer_merge", ator, origem_id=origem["id"], alias_ids=det.get("alias_ids", []))
    return _get(client, org_id, origem_id)


def adicionar_alias(client, org_id, condominio_id, alias: str, ator) -> dict:
    c = _get(client, org_id, condominio_id)
    chave = norm.alias_key(alias)
    if not chave:
        raise ValidationError_("Informe a grafia.")
    ja = (
        table(client, ALIASES).select("id,condominio_id").eq("org_id", str(org_id))
        .eq("alias_normalizado", chave).execute()
    ).data or []
    if ja:
        raise ConflictError("Essa grafia já pertence a um condomínio.")
    row = table(client, ALIASES).insert(
        {"id": str(uuid4()), "org_id": str(org_id), "condominio_id": c["id"], "alias": norm._WS.sub(" ", alias.strip()),
         "alias_normalizado": chave, "origem": "manual"}
    ).execute().data[0]
    _evento(client, org_id, c["id"], "alias_add", ator, alias=chave)
    return row


def remover_alias(client, org_id, condominio_id, alias_id: UUID, ator) -> dict:
    c = _get(client, org_id, condominio_id)
    rows = (
        table(client, ALIASES).select("*").eq("org_id", str(org_id))
        .eq("condominio_id", c["id"]).eq("id", str(alias_id)).execute()
    ).data or []
    if not rows:
        raise NotFoundError("Grafia não encontrada.")
    table(client, ALIASES).delete().eq("org_id", str(org_id)).eq("id", str(alias_id)).execute()
    _evento(client, org_id, c["id"], "alias_remove", ator, alias=rows[0]["alias_normalizado"])
    return {"status": "ok"}
