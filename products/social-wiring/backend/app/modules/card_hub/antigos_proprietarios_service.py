"""Antigos proprietários (previous owners) — the deal's Certidões-tab group.

Owner decisions 2026-10-05 (backed by a 33-contract signed-corpus study):

1. Previous owners stay REQUIRED when the imóvel's last registered transfer is
   under 5 years old (`contrato_gerador.derivacao.exige_antigo_proprietario`).
2. An admin can DISPENSE them per deal, with a motivo and who/when
   (`atendimentos.antigos_dispensados_*`, migration 203). Readiness then
   names an `aviso` instead of a `falta` — never a silent skip.
3. When the card's imóvel has a matrícula whose last transfer is < 5 years
   old, the sellers of that transfer BECOME a group on the card
   automatically (`sincronizar`) — party rows with papel
   `antigo_proprietario`, `origem='matricula'` — and their certidões emission
   starts at once through the SAME path the Certidões tab's emission button
   uses (`certidoes_partes_service.solicitar_emissao`; the router schedules
   `processar_consulta`). They are NOT contract parties: never listed by
   `/partes`, never qualified.
4. When the matrícula does not name them an operator adds / removes them by
   hand (`origem='manual'`).

Everything here is deal-scoped and idempotent: `sincronizar` creates only what
is missing, so calling it on every Certidões-tab open is safe.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import cnpj as cnpj_docs
from noctusai_lib.integrations.documents import cpf as cpf_docs
from noctusai_lib.primitives.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import certidoes_partes_service as certidoes_partes_svc
from app.modules.card_hub import compradores_service as comp_svc
from app.modules.card_hub import negociacao_service
from app.modules.card_hub import partes_service
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.services import ensure_cliente, resolve_atendimento_id
from app.modules.matriculas import titulo_service
from app.services import clientes_service as clientes_svc
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

PAPEL = comp_svc.PAPEL_ANTIGO_PROPRIETARIO
LADO = "vendedor"
ORIGEM_MATRICULA = "matricula"
ORIGEM_MANUAL = "manual"
#: `titulo_service.antigos_proprietarios` origins that mean "read off a
#: matrícula" (a manual override carries no transmitentes to materialise).
_ORIGENS_MATRICULA = ("titulo_confirmado", "extracao")

ATENDIMENTOS = "atendimentos"
PARTES = comp_svc.TABLE

MOTIVO_MIN = 3
MOTIVO_MAX = 500


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def mascarar_documento(valor: Any) -> Optional[str]:
    """`***.456.789-**` for a CPF, `**.***.789/0001-**` for a CNPJ — the
    previous owners read off a matrícula are shown masked; the full document
    only reaches a party row once it is a card party."""
    d = _digitos(valor)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"**.***.{d[5:8]}/{d[8:12]}-**"
    return None


# ─── dispensa (migration 203) ─────────────────────────────────────────────


def _atendimento_row(client: Any, org_id: UUID, atendimento_id: str) -> dict:
    rows = (
        _t(client, ATENDIMENTOS).select("*")
        .eq("org_id", str(org_id)).eq("id", str(atendimento_id)).limit(1).execute()
    ).data or []
    if not rows:
        raise NotFoundError(ATENDIMENTOS, str(atendimento_id))
    return rows[0]


def esta_dispensado(client: Any, org_id: UUID, atendimento_id: str) -> bool:
    """The stamp IS the flag (`antigos_dispensados_em IS NOT NULL`)."""
    return bool(_atendimento_row(client, org_id, atendimento_id).get("antigos_dispensados_em"))


def _dispensa_saida(row: dict) -> Optional[dict]:
    if not row.get("antigos_dispensados_em"):
        return None
    resolved = table_reads.resolve_actors({row["antigos_dispensados_por"]} - {None})
    return {
        "em": row["antigos_dispensados_em"],
        "por": table_reads.actor(resolved, row.get("antigos_dispensados_por")),
        "motivo": row.get("antigos_dispensados_motivo"),
    }


def _alvo(client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: Optional[UUID]) -> str:
    ensure_cliente(client, org_id, cliente_id)
    return str(resolve_atendimento_id(client, org_id, cliente_id, atendimento_id))


def dispensar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    motivo: Optional[str],
    usuario_id: Optional[UUID],
    atendimento_id: Optional[UUID] = None,
    ler_antigos: Optional["LerAntigos"] = None,
) -> dict:
    """`PUT …/antigos-proprietarios/dispensa` — admin-gated upstream (the
    router), exactly like `processo_legado`. The motivo is REQUIRED
    (3..500 chars): a dispensation without a reason is a silent skip."""
    texto = (motivo or "").strip()
    if not (MOTIVO_MIN <= len(texto) <= MOTIVO_MAX):
        raise ValidationError_(
            f"motivo é obrigatório ({MOTIVO_MIN} a {MOTIVO_MAX} caracteres) ao dispensar os "
            "antigos proprietários neste negócio",
            field="motivo",
        )
    alvo = _alvo(client, org_id, cliente_id, atendimento_id)
    _t(client, ATENDIMENTOS).update({
        "antigos_dispensados_em": now_iso(),
        "antigos_dispensados_por": str(usuario_id) if usuario_id else None,
        "antigos_dispensados_motivo": texto,
    }).eq("org_id", str(org_id)).eq("id", alvo).execute()
    return estado(
        client, org_id, cliente_id, atendimento_id=UUID(alvo), usuario_id=usuario_id,
        ler_antigos=ler_antigos,
    )


def reativar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    usuario_id: Optional[UUID],
    atendimento_id: Optional[UUID] = None,
    ler_antigos: Optional["LerAntigos"] = None,
) -> dict:
    """`DELETE …/antigos-proprietarios/dispensa` — the previous owners are
    required again; all three stamps cleared (a stale motivo must never look
    like it still applies)."""
    alvo = _alvo(client, org_id, cliente_id, atendimento_id)
    _t(client, ATENDIMENTOS).update({
        "antigos_dispensados_em": None,
        "antigos_dispensados_por": None,
        "antigos_dispensados_motivo": None,
    }).eq("org_id", str(org_id)).eq("id", alvo).execute()
    return estado(
        client, org_id, cliente_id, atendimento_id=UUID(alvo), usuario_id=usuario_id,
        ler_antigos=ler_antigos,
    )


# ─── estado do grupo (the header of the antigos subtab) ───────────────────


#: `(client, org_id, codigo, usuario_id=) -> dict` — the matrícula reading.
#: A DI seam (never a patch): production reads `titulo_service`; a test hands
#: in the one answer under test instead of seeding a whole extraction.
LerAntigos = Callable[..., dict]


def _info_matricula(
    client: Any, org_id: UUID, cliente_id: UUID, usuario_id: Optional[Any],
    ler: Optional[LerAntigos] = None,
) -> Optional[dict]:
    """`titulo_service.antigos_proprietarios` for the card's imóvel, or `None`
    when the deal has no imóvel yet."""
    codigo = negociacao_service.obter(client, org_id, cliente_id).get("imovel_codigo")
    if not codigo:
        return None
    return (ler or titulo_service.antigos_proprietarios)(
        client, org_id, codigo, usuario_id=usuario_id
    )


def _documentos_no_card(client: Any, org_id: UUID, atendimento_id: str) -> tuple[set[str], set[str]]:
    """(CPF digits, CNPJ digits) already on the deal — as titular or any
    party, on either side."""
    partes = table_reads.paged_rows(
        client, PARTES, org_id, eq_filters={"atendimento_id": atendimento_id}
    )
    atendimento = _atendimento_row(client, org_id, atendimento_id)
    cliente_ids = [str(p["cliente_id"]) for p in partes if p.get("cliente_id")]
    if atendimento.get("cliente_id"):
        cliente_ids.append(str(atendimento["cliente_id"]))
    empresa_ids = [str(p["empresa_id"]) for p in partes if p.get("empresa_id")]
    cpfs = {
        _digitos(r.get("cpf"))
        for r in table_reads.in_batched_rows(client, "clientes", org_id, "id", cliente_ids, select="id,cpf")
    }
    cnpjs = {
        _digitos(r.get("cnpj"))
        for r in table_reads.in_batched_rows(client, "empresas", org_id, "id", empresa_ids, select="id,cnpj")
    }
    return cpfs - {""}, cnpjs - {""}


def estado(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
    usuario_id: Optional[Any] = None,
    ler_antigos: Optional[LerAntigos] = None,
) -> dict:
    """The antigos subtab header: is the group required, why, who the matrícula
    names, whether an admin dispensed it. Read-only."""
    alvo = _alvo(client, org_id, cliente_id, atendimento_id)
    row = _atendimento_row(client, org_id, alvo)
    info = _info_matricula(client, org_id, cliente_id, usuario_id, ler_antigos)
    cpfs, cnpjs = _documentos_no_card(client, org_id, alvo)
    transmitentes = []
    for t in (info or {}).get("transmitentes") or []:
        doc = _digitos(t.get("cpf_cnpj"))
        transmitentes.append({
            "nome": t.get("nome"),
            "documento_mascarado": mascarar_documento(doc),
            "tipo_pessoa": "PJ" if len(doc) == 14 else "PF",
            "ja_no_card": doc in cpfs or doc in cnpjs if doc else False,
        })
    ultima = (info or {}).get("ultima_transferencia")
    exigido: Optional[bool]
    if info is None:
        exigido, motivo = None, "sem_imovel"
    elif info.get("sem_registro"):
        exigido, motivo = False, "sem_transferencia_registrada"
    elif ultima is None:
        exigido, motivo = None, "ultima_transferencia_desconhecida"
    elif info.get("exige_certidoes"):
        exigido, motivo = True, "transferencia_menos_de_5_anos"
    else:
        exigido, motivo = False, "transferencia_5_anos_ou_mais"
    pendentes = 0
    if exigido and not row.get("antigos_dispensados_em") and (info or {}).get("origem") in _ORIGENS_MATRICULA:
        pendentes = sum(1 for t in transmitentes if not t["ja_no_card"])
    return {
        "atendimento_id": alvo,
        "exigido": exigido,
        "motivo": motivo,
        "janela_anos": POLITICA_PADRAO.antigo_proprietario_janela_anos,
        "ultima_transferencia": ultima,
        "origem_dados": (info or {}).get("origem"),
        "transmitentes": transmitentes,
        "dispensado": _dispensa_saida(row),
        "sincronizacao_pendente": pendentes,
    }


# ─── sincronizar (matrícula → grupo do card) ──────────────────────────────


def _adicionar_antigo(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str, *,
    nome: Optional[str], documento: str, origem: str, user_id: Optional[UUID],
) -> dict:
    """One previous-owner party row, through the ONE party-creation path
    (`compradores_service.adicionar`) — a person found by CPF is linked, not
    duplicated."""
    comum = dict(
        atendimento_id=UUID(atendimento_id), lado=LADO, papel=PAPEL, origem=origem, user_id=user_id,
    )
    if len(documento) == 14:
        return comp_svc.adicionar(
            client, org_id, cliente_id, cnpj=documento, razao_social=nome, **comum
        )
    cpf = cpf_docs.format_cpf(documento) if len(documento) == 11 else None
    if cpf:
        existentes = clientes_svc.clientes_por_cpf(client, org_id, [cpf])
        if existentes:
            return comp_svc.adicionar(
                client, org_id, cliente_id, parte_cliente_id=UUID(str(existentes[0]["id"])), **comum
            )
    return comp_svc.adicionar(client, org_id, cliente_id, nome=nome, cpf=cpf, **comum)


def _emitir(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str, item: dict,
    *, user_id: Any, check_credentials: Callable[[str], list[str]],
) -> dict:
    """Request the automated certidões for one new party — the SAME function
    the tab's emission button calls. A refusal (no document yet, missing
    credentials) is REPORTED, never swallowed."""
    kind = "empresa" if item.get("empresa_id") else "pessoa"
    alvo_id = item.get("empresa_id") or item.get("cliente_id")
    try:
        out = certidoes_partes_svc.solicitar_emissao(
            client, org_id, cliente_id, kind, UUID(str(alvo_id)),
            tipos=None, atendimento_id=UUID(atendimento_id),
            user_id=user_id, check_credentials=check_credentials,
        )
    except AppException as exc:
        logger.warning("antigos: emissão não iniciada (%s) para %s", exc.code, kind)
        return {"parte_id": item["parte_id"], "status": "nao_iniciada", "codigo": exc.code, "consulta_id": None}
    return {"parte_id": item["parte_id"], "status": "solicitada", "codigo": None, "consulta_id": out["consulta_id"]}


def sincronizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
    user_id: Optional[UUID],
    check_credentials: Callable[[str], list[str]],
    ler_antigos: Optional[LerAntigos] = None,
) -> dict:
    """`POST …/antigos-proprietarios/sincronizar` — idempotent.

    Materialises the last transfer's sellers as previous-owner parties when
    (a) the deal is not dispensed, (b) the imóvel's matrícula names them
    (a confirmed título act or the latest transfer act — NOT a manual date
    override, which carries no names) and (c) the transfer is < 5 years old.
    Only people/companies not already on the deal (matched by CPF/CNPJ) are
    created; for each one the automated certidões are requested right away.
    Returns `{criados, ja_no_card, emissoes, ignorado}`; the router
    schedules `processar_consulta` for every `emissoes[].consulta_id`.
    """
    alvo = _alvo(client, org_id, cliente_id, atendimento_id)
    vazio = {"atendimento_id": alvo, "criados": [], "ja_no_card": [], "emissoes": [], "ignorado": None}
    if esta_dispensado(client, org_id, alvo):
        return {**vazio, "ignorado": "dispensado"}
    info = _info_matricula(client, org_id, cliente_id, user_id, ler_antigos)
    if info is None:
        return {**vazio, "ignorado": "sem_imovel"}
    if info.get("origem") not in _ORIGENS_MATRICULA:
        return {**vazio, "ignorado": "matricula_nao_nomeia_antigos"}
    if not info.get("exige_certidoes"):
        return {**vazio, "ignorado": "transferencia_5_anos_ou_mais"}

    cpfs, cnpjs = _documentos_no_card(client, org_id, alvo)
    nomes_antigos = {
        (i.get("nome") or "").strip().lower()
        for i in partes_service.listar_antigos(client, org_id, cliente_id, atendimento_id=UUID(alvo))
    }
    criados: list[dict] = []
    ja: list[dict] = []
    emissoes: list[dict] = []
    for t in info.get("transmitentes") or []:
        nome = (t.get("nome") or "").strip() or None
        doc = _digitos(t.get("cpf_cnpj"))
        valido = (
            (len(doc) == 11 and cpf_docs.is_valid(doc)) or (len(doc) == 14 and cnpj_docs.is_valid(doc))
        )
        if doc and not valido:
            doc = ""  # a garbled read is no document: named, not trusted
        if (doc and (doc in cpfs or doc in cnpjs)) or (
            not doc and nome and nome.lower() in nomes_antigos
        ):
            ja.append({"nome": nome, "documento_mascarado": mascarar_documento(doc)})
            continue
        if not nome and not doc:
            continue
        try:
            item = _adicionar_antigo(
                client, org_id, cliente_id, alvo, nome=nome, documento=doc,
                origem=ORIGEM_MATRICULA, user_id=user_id,
            )
        except ConflictError:
            ja.append({"nome": nome, "documento_mascarado": mascarar_documento(doc)})
            continue
        if doc:
            cpfs.add(doc)
        criados.append({"parte_id": item["parte_id"], "nome": item["nome"], "tipo_pessoa": item["tipo_pessoa"]})
        emissoes.append(
            _emitir(client, org_id, cliente_id, alvo, item, user_id=user_id, check_credentials=check_credentials)
            if doc
            else {"parte_id": item["parte_id"], "status": "nao_iniciada", "codigo": "DOCUMENTO_AUSENTE", "consulta_id": None}
        )
    return {**vazio, "criados": criados, "ja_no_card": ja, "emissoes": emissoes}


# ─── add / remove by hand (the matrícula does not name them) ──────────────


def adicionar_manual(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    nome: Optional[str] = None,
    cpf: Optional[str] = None,
    cnpj: Optional[str] = None,
    razao_social: Optional[str] = None,
    atendimento_id: Optional[UUID] = None,
    user_id: Optional[UUID],
    check_credentials: Callable[[str], list[str]],
) -> dict:
    """`POST …/antigos-proprietarios` — a previous owner the matrícula does
    not name. A person needs `nome`+`cpf`; a company `cnpj` (+`razao_social`).
    Emission starts immediately, like an auto-created one."""
    pf = bool(nome)
    pj = bool(cnpj)
    if pf == pj:
        raise ValidationError_("Informe nome e CPF (pessoa) OU CNPJ (empresa).")
    documento = _digitos(cnpj if pj else cpf)
    if pf and not (len(documento) == 11 and cpf_docs.is_valid(documento)):
        raise ValidationError_("CPF inválido ou ausente.", field="cpf")
    if pj and not (len(documento) == 14 and cnpj_docs.is_valid(documento)):
        raise ValidationError_("CNPJ inválido.", field="cnpj")
    alvo = _alvo(client, org_id, cliente_id, atendimento_id)
    cpfs, cnpjs = _documentos_no_card(client, org_id, alvo)
    if documento in cpfs or documento in cnpjs:
        raise ConflictError("Esta pessoa/empresa já é parte deste atendimento.")
    item = _adicionar_antigo(
        client, org_id, cliente_id, alvo, nome=nome or razao_social, documento=documento,
        origem=ORIGEM_MANUAL, user_id=user_id,
    )
    emissao = _emitir(client, org_id, cliente_id, alvo, item, user_id=user_id, check_credentials=check_credentials)
    return {"parte": item, "emissao": emissao}


def remover(client: Any, org_id: UUID, cliente_id: UUID, parte_id: UUID) -> None:
    """`DELETE …/antigos-proprietarios/{parte_id}` — detach a previous-owner
    party (person or company). Refuses any party that is not a previous
    owner: this door must never detach a seller. A matrícula-origin row
    removed here is re-created by the next `sincronizar` unless the group is
    dispensed — remove it only to correct a wrong read, else dispense."""
    row = comp_svc._parte_do_cliente(client, org_id, cliente_id, parte_id)
    if row.get("papel") != PAPEL:
        raise ValidationError_("Esta parte não é um antigo proprietário.")
    comp_svc.remover(client, org_id, cliente_id, parte_id)


__all__ = [
    "adicionar_manual", "dispensar", "esta_dispensado", "estado", "mascarar_documento",
    "reativar", "remover", "sincronizar",
]
