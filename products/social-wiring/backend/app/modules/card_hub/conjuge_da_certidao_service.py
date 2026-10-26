"""The spouse a certidão de casamento READ, offered as a one-click party.

Owner rule: a document-derived field is never hand-typed. A titular's (or a
seller's) certidão de casamento names BOTH spouses (`cliente_documentos.
extracao_conjuges`, no CPF on that page), yet the Cônjuge tab used to say
"Nenhum cônjuge cadastrado" and ask the operator to TYPE the name.
`identidade_extracao_service._criar_conjuge_da_certidao` already creates her
unattended — but only with a check-digit-valid CPF. This module is the
operator-confirmed twin for the CPF-less case, built on the SAME mechanism:

* `sugerir` — the read: per principal (buyer side: the titular; seller side:
  each `proprietario`) whose live, read certidão attributes exactly ONE other
  spouse and who has no spouse linked yet → the entry, with its document id.
* `adicionar` — the action: link a same-name+birthdate cliente already in the
  org (409 + candidates when it is not unambiguous the operator's choice),
  else create her through `compradores_service.adicionar` (papel `conjuge`,
  same `lado`), link the pair with `certidao_casamento` provenance and run the
  existing attribution so every couple/person fact lands machine-pending.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import chave_nome
from noctusai_lib.integrations.documents.name import looks_like_a_name
from noctusai_lib.primitives.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import compradores_service as comp
from app.modules.card_hub import identidade_extracao_service as ident
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)

logger = logging.getLogger(__name__)

CLIENTES_TABLE = "clientes"
DOCUMENTOS_TABLE = "cliente_documentos"
PARTES_TABLE = "atendimento_partes"
ATENDIMENTOS_TABLE = "atendimentos"
ORIGEM = "certidao_casamento"

#: What the suggestion carries about her — read off the document row, nothing else.
_CAMPOS_SUGESTAO = (
    "nome", "nome_anterior", "data_nascimento", "nacionalidade", "profissao",
    "genero", "naturalidade", "nome_mae", "nome_pai",
)


class ConjugeCandidatos(AppException):
    """A cliente matching her name + birthdate already exists in the org: the
    operator picks (link it) or says she is someone new. An `AppException` so
    `details` reaches the client (see `AmbiguousAtendimento`)."""

    def __init__(self, candidatos: list[dict]):
        super().__init__(
            code="CONJUGE_CANDIDATOS",
            message=(
                "Já existe uma pessoa com este nome e data de nascimento — "
                "vincule-a em vez de criar outra."
            ),
            status_code=409,
            details={"candidatos": candidatos},
        )


def _principais(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str, lado: str
) -> list[str]:
    """The people whose spouse this side may need: the titular (buyer side —
    deliberately not a party row) or each `proprietario` (seller side)."""
    if lado == "comprador":
        rows = (
            _t(client, ATENDIMENTOS_TABLE)
            .select("id,cliente_id")
            .eq("org_id", str(org_id))
            .eq("id", atendimento_id)
            .execute()
        ).data or []
        return [str(r["cliente_id"]) for r in rows if r.get("cliente_id")]
    partes = (
        _t(client, PARTES_TABLE)
        .select("cliente_id,papel")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", atendimento_id)
        .eq("lado", lado)
        .execute()
    ).data or []
    return [
        str(p["cliente_id"])
        for p in partes
        if p.get("cliente_id") and p.get("papel") == comp.PAPEL_PADRAO_POR_LADO["vendedor"]
    ]


def _entrada_sugerida(doc: dict) -> Optional[dict]:
    """The ONE non-titular, unattributed, plausibly-named entry of a read
    certidão that states a marriage — else `None` (ambiguous or no marriage)."""
    from app.modules.card_hub.documento_checklist_service import _estado_civil_normalizado

    estado = doc.get("extracao_estado_civil")
    normalizado = _estado_civil_normalizado(str(estado)) if estado else None
    if normalizado is not None and normalizado not in ("casado", "uniao_estavel"):
        return None  # a divorced/widowed reading is not a spouse to add
    nao_titulares = [e for e in ident._entradas_conjuges(doc) if not e.get("titular")]
    if len(nao_titulares) != 1:
        return None
    entrada = nao_titulares[0]
    if entrada.get("cliente_id") or not looks_like_a_name(entrada.get("nome") or ""):
        return None
    return entrada


def _certidao_do(client: Any, org_id: UUID, principal_id: str) -> Optional[tuple[dict, dict]]:
    docs = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", principal_id)
        .eq("tipo_documento", "certidao_casamento")
        .eq("extracao_status", "ok")
        .is_("deleted_at", "null")
        .is_("extracao_descartada_em", "null")
        .execute()
    ).data or []
    for doc in sorted(docs, key=lambda d: d.get("created_at") or "", reverse=True):
        entrada = _entrada_sugerida(doc)
        if entrada is not None:
            return doc, entrada
    return None


def _alvo(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: Optional[UUID], lado: str
) -> Optional[str]:
    ensure_cliente(client, org_id, cliente_id)
    try:
        return resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
    except AmbiguousAtendimento:
        return None  # nothing to suggest; the write path surfaces the 409


def _sugestoes(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str, lado: str
) -> list[dict]:
    principais = _principais(client, org_id, cliente_id, atendimento_id, lado)
    if not principais:
        return []
    linhas = (
        _t(client, CLIENTES_TABLE)
        .select("id,conjuge_cliente_id")
        .eq("org_id", str(org_id))
        .in_("id", principais)
        .execute()
    ).data or []
    casados = {str(r["id"]) for r in linhas if r.get("conjuge_cliente_id")}
    # A spouse party already on this side + a lone principal = she is linked
    # (the link resolves by `_principal_do_conjuge`); with several principals
    # only the `conjuge_cliente_id` above tells whose she is.
    conjuges = [
        p for p in (
            _t(client, PARTES_TABLE)
            .select("cliente_id,papel")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", atendimento_id)
            .eq("lado", lado)
            .execute()
        ).data or []
        if p.get("papel") == comp.PAPEL_CONJUGE
    ]
    itens: list[dict] = []
    for principal in principais:
        if principal in casados or (len(principais) == 1 and conjuges):
            continue
        achada = _certidao_do(client, org_id, principal)
        if achada is None:
            continue
        doc, entrada = achada
        itens.append({
            "principal_cliente_id": principal,
            "documento_id": str(doc["id"]),
            "lado": lado,
            **{k: entrada.get(k) for k in _CAMPOS_SUGESTAO},
        })
    return itens


def sugerir(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
    lado: Optional[str] = None,
) -> dict:
    """`{items: [...], atendimento_id, lado}` — empty (never an error) when the
    card has no single open atendimento, mirroring `compradores_service.listar`."""
    lado_alvo = comp.normalizar_lado(lado)
    alvo = _alvo(client, org_id, cliente_id, atendimento_id, lado_alvo)
    if alvo is None:
        return {"items": [], "atendimento_id": None, "lado": lado_alvo}
    return {
        "items": _sugestoes(client, org_id, cliente_id, alvo, lado_alvo),
        "atendimento_id": alvo,
        "lado": lado_alvo,
    }


def _candidatos_existentes(
    client: Any, org_id: UUID, principal_id: str, entrada: dict
) -> list[dict]:
    """Clientes of the org with the same normalised name AND birthdate."""
    nascimento = str(entrada.get("data_nascimento") or "")[:10]
    chave = chave_nome(entrada.get("nome"))
    if not nascimento or not chave:
        return []
    achados = (
        _t(client, CLIENTES_TABLE)
        .select("id,nome,nome_completo,nome_oficial,data_nascimento")
        .eq("org_id", str(org_id))
        .eq("data_nascimento", nascimento)
        .execute()
    ).data or []
    return [
        r for r in achados
        if str(r["id"]) != principal_id
        and any(
            chave_nome(n) == chave
            for n in (r.get("nome_oficial"), r.get("nome_completo"), r.get("nome"))
            if n
        )
    ]


def adicionar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    documento_id: UUID,
    atendimento_id: Optional[UUID] = None,
    lado: Optional[str] = None,
    parte_cliente_id: Optional[UUID] = None,
    criar_novo: bool = False,
    user_id: Optional[UUID] = None,
) -> dict:
    """Add the spouse the certidão read as a `conjuge` party and link the pair."""
    lado_alvo = comp.normalizar_lado(lado)
    alvo = _alvo(client, org_id, cliente_id, atendimento_id, lado_alvo)
    if alvo is None:
        # The ambiguity (or absence) is the same 409 the resolver raises.
        resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
        raise NotFoundError(ATENDIMENTOS_TABLE, str(atendimento_id))
    sugestao = next(
        (s for s in _sugestoes(client, org_id, cliente_id, alvo, lado_alvo)
         if s["documento_id"] == str(documento_id)),
        None,
    )
    if sugestao is None:
        raise ConflictError(
            "Este documento não sugere um cônjuge a adicionar (já vinculado, "
            "ambíguo ou de outro atendimento)."
        )
    principal = sugestao["principal_cliente_id"]
    doc, entrada = _certidao_do(client, org_id, principal) or (None, None)
    if doc is None or str(doc["id"]) != str(documento_id):
        raise ConflictError("A certidão mudou — recarregue o card.")

    candidatos = _candidatos_existentes(client, org_id, principal, entrada)
    ids_candidatos = {str(c["id"]) for c in candidatos}
    if parte_cliente_id is not None and str(parte_cliente_id) not in ids_candidatos:
        raise ValidationError_("A pessoa escolhida não corresponde ao cônjuge lido na certidão.")
    if candidatos and parte_cliente_id is None and not criar_novo:
        raise ConjugeCandidatos([
            {
                "cliente_id": str(c["id"]),
                "nome": c.get("nome_oficial") or c.get("nome_completo") or c.get("nome"),
                "data_nascimento": c.get("data_nascimento"),
            }
            for c in candidatos
        ])

    # Same mechanism as "Adicionar cônjuge" (`compradores_service.adicionar`,
    # papel `conjuge`); no CPF is passed (that would stamp it `manual`).
    parte = comp.adicionar(
        client, org_id, cliente_id,
        parte_cliente_id=parte_cliente_id,
        nome=None if parte_cliente_id else entrada["nome"],
        papel=comp.PAPEL_CONJUGE,
        atendimento_id=UUID(alvo), lado=lado_alvo, user_id=user_id,
        forcar_novo=criar_novo,
    )
    novo = UUID(str(parte["cliente_id"]))
    # `adicionar` links only when its principal resolution is unambiguous; here
    # the document names the principal, so link both ways (idempotent) with the
    # certidão as provenance, then run the attribution (fills the couple and
    # person facts machine-pending, stamps `cliente_id` on the entry).
    conflitos = ident.vincular_conjuges(
        client, org_id, UUID(principal), novo, origem=ORIGEM, documento_id=documento_id
    )
    ident._carimbar_vinculo(client, org_id, (principal, str(novo)), ORIGEM, documento_id)
    conflitos += ident.aplicar_certidao_casamento_ao_conjuge(client, org_id, UUID(principal), novo)
    return {**parte, "conflitos_abertos": len(conflitos)}
