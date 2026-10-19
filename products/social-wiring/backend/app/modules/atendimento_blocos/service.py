"""`GET` / `PUT /api/atendimento-blocos` behaviour (maya-blocks CONTRACT §4.1 / §4.2).

`ler` builds the 6-block view (saved row or code default, `etapas_sem_bloco`, the agent allowlist, the
supervision switch). `salvar` validates the WHOLE resulting configuration before writing anything, then writes in
two phases -- every saved row that loses a stage is shrunk first, then every listed block is upserted -- so a stage
moving between blocks (or two blocks swapping stages) never trips the DB disjointness trigger. Side effect: rows of
`atendimento_blocos` only -- no handoff, no send.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.modules.atendimento_blocos import repository as repo
from app.modules.atendimento_blocos.blocos import (
    AGENTES_POR_BLOCO,
    BLOCOS,
    BLOCO_POR_NOME,
    BLOCO_SDR,
    ConfigBloco,
    agentes_permitidos,
    dono,
    sobreposicoes,
)

logger = logging.getLogger(__name__)

#: The DB trigger/constraints whose refusal on save means "a concurrent save changed the picture" (409).
_RECUSAS_CONCORRENTES = ("atendimento_blocos_etapas_disjuntas", "atendimento_blocos_etapas_validas")


def _bloco_dto(c: ConfigBloco) -> dict[str, Any]:
    b = BLOCO_POR_NOME[c.bloco]
    return {
        "bloco": c.bloco, "rotulo": b.rotulo, "ordem": b.ordem, "agent_key": c.agent_key, "ativo": c.ativo,
        "pipeline": b.pipeline, "etapas": list(c.etapas), "origem": c.origem,
        "updated_at": c.updated_at, "updated_by": c.updated_by,
    }


def ler(client: Any, org_id: UUID | str) -> dict[str, Any]:
    config = repo.configuracao_efetiva(client, org_id)
    etapas = repo.etapas_da_org(client, org_id)
    sem_bloco = [
        {"pipeline": e["pipeline"], "slug": e["slug"], "label": e.get("label")}
        for e in etapas if dono(config, e["pipeline"], e["slug"]) is None
    ]
    return {
        "blocos": [_bloco_dto(config[b.bloco]) for b in BLOCOS],
        "etapas_sem_bloco": sem_bloco,
        "agentes_por_bloco": {k: sorted(v) for k, v in AGENTES_POR_BLOCO.items()},
        "supervisao_ativa": repo.ler_supervisao(client, org_id)["supervisao_ativa"],
    }


def _erro(code: str, message: str, **details: Any) -> AppException:
    return AppException(code, message, status_code=422, details=details or None)


def validar(
    atual: dict[str, ConfigBloco], itens: Iterable[dict[str, Any]], etapas_ativas: dict[str, set[str]],
) -> dict[str, ConfigBloco]:
    """The resulting configuration, or the first contract error (nothing is written on an error)."""
    resultado = dict(atual)
    for item in itens:
        bloco = item["bloco"]
        etapas = tuple(item.get("etapas") or ())
        agent_key = item.get("agent_key")
        if bloco == BLOCO_SDR and etapas:
            raise _erro("sdr_sem_etapas", "O bloco SDR (Julia) não possui etapas do funil.", bloco=bloco)
        if agent_key is not None and agent_key not in agentes_permitidos(bloco):
            raise _erro(
                "agente_indisponivel", f"O agente '{agent_key}' não está disponível para o bloco {bloco}.",
                bloco=bloco, agent_key=agent_key,
            )
        pipeline = BLOCO_POR_NOME[bloco].pipeline
        desconhecidas = [s for s in etapas if s not in etapas_ativas.get(pipeline or "", set())]
        if desconhecidas:
            raise _erro(
                "etapa_desconhecida", f"Etapa(s) {', '.join(desconhecidas)} não existe(m) entre as etapas ativas de {pipeline}.",
                bloco=bloco, etapas=desconhecidas,
            )
        resultado[bloco] = ConfigBloco(bloco=bloco, agent_key=agent_key, ativo=bool(item["ativo"]), etapas=etapas, origem="org")
    conflitos = sobreposicoes(resultado)
    if conflitos:
        slug, a, b = conflitos[0]
        raise _erro(
            "etapa_em_dois_blocos", f"A etapa '{slug}' ficaria nos blocos {a} e {b}.", etapa=slug, blocos=[a, b],
        )
    return resultado


def salvar(client: Any, org_id: UUID | str, itens: list[dict[str, Any]], *, updated_by: Optional[str]) -> dict[str, Any]:
    atual = repo.configuracao_efetiva(client, org_id)
    ativas: dict[str, set[str]] = {}
    for e in repo.etapas_da_org(client, org_id):
        ativas.setdefault(e["pipeline"], set()).add(e["slug"])
    resultado = validar(atual, itens, ativas)
    salvas = repo.linhas_salvas(client, org_id)
    listados = [i["bloco"] for i in itens]
    try:
        # phase 1: a saved row that LOSES stages shrinks to what it keeps, so no slug is ever on two rows at once
        for bloco in listados:
            if bloco in salvas:
                antes = tuple(salvas[bloco].get("etapas") or ())
                mantidas = [s for s in antes if s in resultado[bloco].etapas]
                if len(mantidas) < len(antes):
                    repo.reduzir_etapas(client, org_id, bloco, mantidas)
        # phase 2: the final rows
        for bloco in listados:
            c = resultado[bloco]
            repo.gravar_linha(client, org_id, bloco, agent_key=c.agent_key, ativo=c.ativo, etapas=c.etapas, updated_by=updated_by)
    except Exception as exc:
        texto = str(exc)
        if any(nome in texto for nome in _RECUSAS_CONCORRENTES):
            logger.warning("atendimento_blocos: save refused by the DB (concurrent save?) org=%s: %s", org_id, texto)
            raise AppException(
                "conflito_concorrente", "A configuração mudou enquanto você salvava. Recarregue e tente de novo.",
                status_code=409,
            ) from exc
        raise
    return ler(client, org_id)


__all__ = ["ler", "salvar", "validar"]
