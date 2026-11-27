"""The imóvel action register (`imovel_historico`, migration 349) and its "Histórico" timeline.

WRITE side: `registrar(...)` appends one row per action (a change the Vista sync applied, a Vista-wins, a value sent to
Vista or the failure to, an approval opened or decided). The table is append-only at the grant level; nothing here updates.

READ side: the SEED card_hub timeline engine (`noctusai_lib.domain.card_hub.timeline.get_timeline` + `CardHubConfig` for
entity `imovel`) -- not a fork -- with four gatherers merged on one thread:

  kind            source                      payload
  vista           imovel_historico            campo_atualizado | vista_prevaleceu     {campo, rotulo, de, para, acao}
  aprovacao       imovel_historico            aprovacao_pendente | aprovacao_decidida {campo, rotulo, de, para, acao, conversa?, status, divergencia_id}
  vista_envio     imovel_historico            enviado_ao_vista | envio_vista_falhou   {campo, rotulo, de, para, acao, conversa?, detalhe?}
  alteracao       imovel_historico            campo_atualizado by a user / Julia / the system, video_youtube_definido |
                                              video_youtube_removido (campo `video_youtube`, detalhe = the motivo; any origem)
  preco           imovel_preco_historico      one entry per price that changed        {campo, rotulo, de, para, acao}
  nota            imovel_notas                {id, corpo, autor}

`ator` is `{tipo: vista|usuario|julia|sistema, nome}`; `ocorrido_em` is the event's own time. The `entity_id` the engine
carries for this card is the imóvel's CANONICAL CODE (upper-cased), not a UUID -- the engine only forwards it.

Owner 2026-11-04: "every change to them is supposed to be stored in its history".
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.domain.card_hub import CardHubConfig, MemberSource
from noctusai_lib.domain.card_hub import timeline as card_timeline
from noctusai_lib.integrations.persistence.table_reads import actor_resolver, in_batched_rows, paged_rows

logger = logging.getLogger(__name__)

T_HISTORICO = "imovel_historico"
T_PRECOS = "imovel_preco_historico"
T_NOTAS = "imovel_notas"
T_REGISTRY = "imovel_registry"
T_CONFLITOS = "imovel_campo_conflitos"

ORIGENS = ("vista_sync", "usuario", "julia", "sistema")
ACOES = (
    "campo_atualizado", "vista_prevaleceu", "enviado_ao_vista", "envio_vista_falhou", "aprovacao_pendente", "aprovacao_decidida",
    "video_youtube_definido", "video_youtube_removido",  # migration 371 (imovel_video_youtube_service)
)
_TIPO_ATOR = {"vista_sync": "vista", "usuario": "usuario", "julia": "julia", "sistema": "sistema"}
_NOME_ATOR = {"vista": "Vista", "julia": "Julia", "sistema": "Sistema"}
_STATUS_CONFLITO = {"pendente": "pendente", "aceito": "aprovada", "rejeitado": "recusada"}
_ROTULO_PRECO = {"valor_venda": "valor de venda", "valor_locacao": "valor de locação"}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def montar_linha(
    org_id: Any, codigo: str, *, origem: str, acao: str, campo: Optional[str] = None, anterior: Any = None, novo: Any = None,
    ator: Any = None, conversa: Optional[dict] = None, detalhe: Optional[str] = None, conflito_id: Any = None,
    ocorrido_em: Optional[str] = None,
) -> dict:
    if origem not in ORIGENS or acao not in ACOES:
        raise ValueError(f"imovel_historico: origem {origem!r} / acao {acao!r} invalid")
    return {
        "org_id": str(org_id), "codigo_canonical": codigo.strip().upper(), "ocorrido_em": ocorrido_em or _agora(), "origem": origem,
        "acao": acao, "campo": campo, "valor_anterior": anterior, "valor_novo": novo, "ator_user_id": str(ator) if ator else None,
        "conversa": conversa, "detalhe": detalhe, "conflito_id": str(conflito_id) if conflito_id else None,
    }


def registrar_varias(db: Any, linhas: list[dict]) -> int:
    """Append `linhas` (built by `montar_linha`). Raises on a failed insert: the SYNC catches and reports it (a history that
    cannot be written must be visible), the request path lets it surface."""
    if not linhas:
        return 0
    db.table(T_HISTORICO).insert(linhas).execute()
    return len(linhas)


def registrar(db: Any, org_id: Any, codigo: str, **kw: Any) -> int:
    return registrar_varias(db, [montar_linha(org_id, codigo, **kw)])


# ── the timeline ────────────────────────────────────────────────────────────
def _ator_de(origem: str, user_id: Optional[str], resolved: dict[str, dict]) -> Optional[dict]:
    tipo = _TIPO_ATOR.get(origem, "sistema")
    if tipo == "usuario":
        if not user_id:
            return {"tipo": "usuario", "nome": None}
        return {"tipo": "usuario", "nome": (resolved.get(str(user_id)) or {}).get("nome")}
    return {"tipo": tipo, "nome": _NOME_ATOR.get(tipo)}


def _rotulo(campo: Optional[str]) -> Optional[str]:
    if not campo:
        return None
    from app.services.vista_divergencias import ROTULO_CAMPO

    return ROTULO_CAMPO.get(campo, campo)


def _entradas_historico(cfg: CardHubConfig, db: Any, org_id: Any, codigo: str, kind: str, selecao: Any) -> list[dict]:
    rows = [r for r in paged_rows(db, T_HISTORICO, org_id, eq_filters={"codigo_canonical": codigo}, order_col="id") if selecao(r)]
    if not rows:
        return []
    resolved = cfg.actor_resolver({str(r["ator_user_id"]) for r in rows if r.get("ator_user_id")})
    conflitos: dict[str, dict] = {}
    ids = sorted({str(r["conflito_id"]) for r in rows if r.get("conflito_id")})
    if ids and kind == "aprovacao":
        conflitos = {str(c["id"]): c for c in in_batched_rows(db, T_CONFLITOS, org_id, "id", ids)}
    saida = []
    for r in rows:
        payload: dict[str, Any] = {
            "campo": r.get("campo"), "rotulo": _rotulo(r.get("campo")), "de": r.get("valor_anterior"), "para": r.get("valor_novo"),
            "acao": r["acao"],
        }
        if r.get("conversa"):
            payload["conversa"] = r["conversa"]
        if r.get("detalhe"):
            payload["detalhe"] = r["detalhe"]
        if kind == "aprovacao":
            c = conflitos.get(str(r.get("conflito_id") or ""))
            payload["status"] = _STATUS_CONFLITO.get((c or {}).get("status") or "", "pendente" if r["acao"] == "aprovacao_pendente" else "aprovada")
            payload["divergencia_id"] = str(r["conflito_id"]) if r.get("conflito_id") else None
        saida.append({
            "id": str(r["id"]), "kind": kind, "ocorrido_em": r["ocorrido_em"], "ator": _ator_de(r["origem"], r.get("ator_user_id"), resolved),
            "payload": payload,
        })
    return saida


def _gatherer_historico(kind: str, selecao: Any):
    def gather(cfg: CardHubConfig, db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
        return _entradas_historico(cfg, db, org_id, entity["codigo"], kind, selecao)

    gather.__name__ = f"gather_{kind}"
    return gather


def _gather_preco(cfg: CardHubConfig, db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    rows = paged_rows(db, T_PRECOS, org_id, eq_filters={"codigo_canonical": entity["codigo"]})
    saida = []
    for r in rows:
        ator = {"tipo": "vista", "nome": "Vista"} if r.get("fonte") == "vista_sync" else (
            {"tipo": "sistema", "nome": "Sistema"} if r.get("fonte") == "baseline" else {"tipo": "usuario", "nome": None})
        for campo, col in (("valor_venda", "valor_venda"), ("valor_locacao", "valor_locacao")):
            de, para = r.get(f"{col}_anterior"), r.get(f"{col}_novo")
            if de == para:
                continue
            saida.append({
                "id": f"{r['id']}:{campo}", "kind": "preco", "ocorrido_em": r["observado_em"], "ator": ator,
                "payload": {"campo": campo, "rotulo": _ROTULO_PRECO[campo], "de": de, "para": para, "acao": r.get("evento") or "alteracao"},
            })
    return saida


def _gather_nota(cfg: CardHubConfig, db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    rows = paged_rows(db, T_NOTAS, org_id, eq_filters={"codigo": entity["codigo"]})
    resolved = cfg.actor_resolver({str(r["created_by"]) for r in rows if r.get("created_by")})
    return [
        {
            "id": str(r["id"]), "kind": "nota", "ocorrido_em": r["created_at"],
            "ator": {"tipo": "usuario", "nome": (resolved.get(str(r.get("created_by"))) or {}).get("nome")},
            "payload": {"id": str(r["id"]), "corpo": r["texto"], "autor": (resolved.get(str(r.get("created_by"))) or None)},
        }
        for r in rows
    ]


def _entidade(db: Any, org_id: Any, entity_id: Any) -> Optional[dict]:
    codigo = str(entity_id).strip().upper()
    rows = (db.table(T_REGISTRY).select("codigo_canonical").eq("org_id", str(org_id)).eq("codigo_canonical", codigo).limit(1).execute().data or [])
    return {"codigo": codigo} if rows else None


def configuracao() -> CardHubConfig:
    """The imóvel card as a seed `CardHubConfig` (only the timeline is used: the other card-hub tables do not exist for it)."""
    from app.dependencies import get_core_client
    from app.modules.card_hub.deps import BUCKET

    return CardHubConfig(
        entity_kind="imovel", entity_label="Imóvel", entity_table="imovel_registry", entity_fk="codigo", id_param="codigo",
        table_prefix="imovel", member_source=MemberSource(table="noctus_users", fk="user_id"), bucket=BUCKET,
        actor_resolver=actor_resolver(get_core_client), ensure_entity=_entidade, entity_datas=False, stage_table=None,
        timeline_gatherers={
            "vista": _gatherer_historico("vista", lambda r: r["acao"] in ("vista_prevaleceu",) or (r["acao"] == "campo_atualizado" and r["origem"] == "vista_sync")),
            "aprovacao": _gatherer_historico("aprovacao", lambda r: r["acao"] in ("aprovacao_pendente", "aprovacao_decidida")),
            "vista_envio": _gatherer_historico("vista_envio", lambda r: r["acao"] in ("enviado_ao_vista", "envio_vista_falhou")),
            "alteracao": _gatherer_historico("alteracao", lambda r: (r["acao"] == "campo_atualizado" and r["origem"] != "vista_sync")
                                             or r["acao"] in ("video_youtube_definido", "video_youtube_removido")),
            "preco": _gather_preco,
            "nota": _gather_nota,
        },
    )


def linha_do_tempo(db: Any, org_id: Any, codigo: str, *, cursor: Optional[str] = None, limit: int = 50, cfg: Optional[CardHubConfig] = None) -> dict:
    """One page of the imóvel's history (`{items, next_cursor}`); every item is the seed's flattened shape PLUS a `payload`
    copy of its kind-specific keys. A cursor that does not decode is the engine's typed 400."""
    limit = max(1, min(int(limit), 100))
    page = card_timeline.get_timeline(cfg or configuracao(), db, org_id, codigo.strip().upper(), cursor=cursor or None, limit=limit)
    base = {"id", "kind", "ocorrido_em", "ator"}
    items = [{**it, "payload": {k: v for k, v in it.items() if k not in base}} for it in page["items"]]
    return {"items": items, "next_cursor": page["next_cursor"]}


__all__ = ["ACOES", "ORIGENS", "configuracao", "linha_do_tempo", "montar_linha", "registrar", "registrar_varias"]
