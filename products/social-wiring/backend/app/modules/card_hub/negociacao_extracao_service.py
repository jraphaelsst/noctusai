"""Negociação/financiamento document extraction — S2 contract
`sw-negociacao-extracao-contract.md` §E1-E3/§E5/§E6.

`guia_itbi` / `proposta_financiamento` / `contrato_financiamento` uploads
(`financiamento_service.upload`, on `atendimento_documentos`) get read here,
in a background task, and their D1 (fill-empty, else conflict) apply lands
on `atendimento_negociacao.valor_negociado`, an `atendimento_negociacao_
parcelas` row of `tipo='financiamento'`, and `atendimento_financiamento`
(`fgts` / `numero_proposta` / `agente_financeiro_id` / `situacao`).

`leitura` objects are duck-typed throughout — this module never imports the
seed's `GuiaItbiFields`/`FinanciamentoFields` dataclasses at module scope
(same posture `crednet_service`/`empresas.dados_service.aplicar_cartao`
take), because the seed extractors (S1) are built in parallel to this
module.

OWNER ANSWERS THIS MODULE IMPLEMENTS (binding, contract bottom)
-----------------------------------------------------------------
- **H2** — `valor_negociado` has NO authoritative document. ANY disagreement
  (between documents, or with an existing value) is a conflict for a human.
- **H4** — see `negociacao_estruturada_service.sincronizar_parcela_
  intermediaria_derivada` (called here after every apply that can move its
  inputs).
- **H5** — the Quadro Resumo's seller credit account fills a favorecido,
  matched to a vendedor by CPF (D1 + provenance).
- **H6** — a signed `contrato_financiamento` sets `financiamento.situacao=
  'aprovado'`. "Signed" is read as: a successful `contrato_financiamento`
  extraction with `quadro_encontrado=True` — the Quadro Resumo prints the
  EXECUTED terms of a financing operation, so a read that reaches it is a
  document the bank has already produced against a signed contract. Never
  overrides an existing `'recusado'` decision — a human's refusal is not
  silently reopened by a later document.
- **H7** — an unmatched bank code auto-creates the `agentes_financeiros` row
  (nome + código do banco), logged.
- **H8** — DPS is never stored: refused by construction (`financiamento_
  service.TIPOS_DOCUMENTO` never lists it — see that module). The tripwire
  below is the SECOND layer, for a DPS misfiled under a different tipo.

LESSONS THIS MODULE HONOURS (contract §0/owner)
--------------------------------------------------
- **G5** — at least one realdb FK test covers the new `*_documento_id` FKs
  (`tests/modules/card_hub/test_negociacao_extracao.py`, `NOCTUS_REALDB_
  TESTS=1`) — a mock hid an FK bug once.
- **G6** — `extracao_status` is NEVER stamped `'ok'` before every side
  effect (the D1 apply, the conflict opens) finishes. `extrair` below wraps
  the apply in `try/except`; an exception there ends in `erro`, never a
  false `ok`.
- **The recurrence rule** — this module's OWN sweep goes through the new
  shared `app.services.extracao_varredura` (the fifth hand-rolled sweep is
  forbidden; `empresas.sweep_service` is migrated onto the same helper in
  this slice).
- **Owner: "audit every action"** — every content read appends to
  `atendimento_documento_acessos` (`acao='extract'`, via `STORE.log_acesso`)
  and every write this module makes is `logger.info`/`.warning`d, mirroring
  the access-log/audit convention already in this product.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import cpf as cpf_docs
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.card_hub import financiamento_service
from app.modules.card_hub import negociacao_estruturada_service as neg_estruturada
from app.modules.card_hub import negociacao_service
from app.modules.card_hub.proveniencia import fontes
from app.services import campo_conflitos, table_reads

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = financiamento_service.DOCUMENTOS_TABLE
FINANCIAMENTO_TABLE = financiamento_service.TABLE
NEGOCIACAO_TABLE = negociacao_service.TABLE
PARCELAS_TABLE = neg_estruturada.TABLE_PARCELAS
FAVORECIDOS_TABLE = neg_estruturada.TABLE_FAVORECIDOS

#: The `atendimento_campo_conflitos` descriptor (contract §C.6/§I — "the
#: fourth conflict table goes through the shared writer as a descriptor").
ATENDIMENTO = campo_conflitos.ConflictTable(
    table="atendimento_campo_conflitos", owner_col="atendimento_id",
    has_documento_id_proposto=True,
)

#: Outcomes `extrair`/`aplicar_leitura` may return.
OK = "ok"
SEM_DADOS = "sem_dados"
ERRO = "erro"

#: §D.5's DPS tripwire — a transcription carrying DPS markers is refused
#: by the SEED parser (`error='documento_sensivel_dps'`, no fields, no
#: text); this module never persists that reading. Owner H8.
ERRO_DPS = "documento_sensivel_dps"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ""


def _json_seguro(valor: Any) -> Any:
    """Recursively coerce a `leitura` (or any nested value on it) into
    JSON-safe data for `extracao_dados` — the whole reading, incl. per-field
    confiança/rótulo, mirroring `empresas.extracao_service._serializar_
    leitura`'s intent but generic over TWO distinct field-sets (guia_itbi /
    financiamento_imobiliario) rather than hardcoding either one's fields.
    """
    if is_dataclass(valor) and not isinstance(valor, type):
        return {k: _json_seguro(v) for k, v in dataclasses.asdict(valor).items()}
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [_json_seguro(v) for v in valor]
    return valor


def _confianca(leitura: Any, campo: str) -> Optional[str]:
    confianca = (getattr(leitura, "confiancas", None) or {}).get(campo)
    return getattr(confianca, "value", confianca)


# ─── (a) fetch / mark ───────────────────────────────────────────────────


def _documento(client: Any, org_id: UUID, documento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _marcar_documento(client: Any, documento_id: UUID, **campos: Any) -> None:
    _t(client, DOCUMENTOS_TABLE).update(campos).eq("id", str(documento_id)).execute()


# ─── (b) belongs-to-this-deal ────────────────────────────────────────────


def _cpfs_do_negocio(client: Any, org_id: UUID, atendimento_id: UUID) -> dict[str, dict]:
    """`cpf_normalizado -> {cliente_id, lado, nome}` for the titular AND
    every `atendimento_partes` row of this deal — the set the belongs-check
    (and H5's vendedor match) compares a document's read CPFs against."""
    titulares = (
        _t(client, "atendimentos")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    lado_por_cliente: dict[str, str] = {}
    if titulares and titulares[0].get("cliente_id"):
        lado_por_cliente[str(titulares[0]["cliente_id"])] = "comprador"
    for row in (
        _t(client, "atendimento_partes")
        .select("cliente_id,lado")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .execute()
    ).data or []:
        if row.get("cliente_id"):
            lado_por_cliente.setdefault(str(row["cliente_id"]), row.get("lado") or "comprador")

    if not lado_por_cliente:
        return {}
    clientes = (
        _t(client, "clientes")
        .select("id,cpf,nome")
        .eq("org_id", str(org_id))
        .in_("id", sorted(lado_por_cliente))
        .execute()
    ).data or []
    saida: dict[str, dict] = {}
    for c in clientes:
        cpf_norm = cpf_docs.only_digits(str(c.get("cpf") or ""))
        if cpf_norm:
            saida[cpf_norm] = {
                "cliente_id": c["id"],
                "lado": lado_por_cliente.get(str(c["id"]), "comprador"),
                "nome": c.get("nome"),
            }
    return saida


def _cpfs_lidos(leitura: Any) -> list[tuple[str, Any]]:
    """Every `(cpf_normalizado, pessoa)` the reading validated (`cpf_valido`)
    — across BOTH `compradores` and `vendedores`, whichever the tipo carries.
    """
    achados: list[tuple[str, Any]] = []
    for grupo in ("compradores", "vendedores"):
        for pessoa in getattr(leitura, grupo, None) or []:
            if not getattr(pessoa, "cpf_valido", False):
                continue
            cpf_val = getattr(pessoa, "cpf", None)
            if not cpf_val:
                continue
            achados.append((cpf_docs.only_digits(str(cpf_val)), pessoa))
    return achados


def _pertence_ao_negocio(leitura: Any, cpfs_negocio: dict[str, dict]) -> bool:
    """(b) — at least one document CPF read must match a deal party.

    🔴 Only refuses when the document actually carries at least one
    VALIDATED CPF (mirrors `empresas.dados_service.aplicar_cartao`'s own
    `if leitura.cnpj and normalize(...) != empresa.cnpj` conditional — the
    check fires on a PRESENT-AND-WRONG value, never on an absent one). A
    guia_itbi/contrato that read no CPF at all is inconclusive, not
    "another deal's" — the field-level D1 apply below still runs.
    """
    lidos = _cpfs_lidos(leitura)
    if not lidos:
        return True
    return any(cpf_norm in cpfs_negocio for cpf_norm, _ in lidos)


# ─── (d) the D1 field map ────────────────────────────────────────────────


def _aplicar_valor_negociado(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """H2 — no authoritative source; ANY disagreement is a conflict.

    Returns `(aviso, conflito_or_None)`.
    """
    campo = "valor_transacao" if tipo_documento == "guia_itbi" else "valor_compra_venda"
    proposto = _dec(getattr(leitura, campo, None))
    if proposto is None:
        return None, None

    negociacao = (
        _t(client, NEGOCIACAO_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    atual_row = negociacao[0] if negociacao else None
    atual = _dec((atual_row or {}).get("valor_negociado"))

    if atual is None:
        now = _now()
        patch = {
            "valor_negociado": str(proposto),
            "valor_negociado_origem": tipo_documento,
            "valor_negociado_documento_id": str(documento_id),
            "valor_negociado_em": now,
            "valor_negociado_confirmado_por": None,
            "valor_negociado_confirmado_em": None,
        }
        if atual_row is None:
            _t(client, NEGOCIACAO_TABLE).insert(
                {
                    "atendimento_id": str(atendimento_id),
                    "org_id": str(org_id),
                    "tem_parceria": False,
                    "financiamento": False,
                    "fgts": False,
                    "created_at": now,
                    **patch,
                }
            ).execute()
        else:
            _t(client, NEGOCIACAO_TABLE).update(patch).eq(
                "org_id", str(org_id)
            ).eq("atendimento_id", str(atendimento_id)).execute()
        return None, None

    if atual == proposto:
        return None, None

    novo = campo_conflitos.registrar_conflito(
        client, ATENDIMENTO, org_id, atendimento_id, "valor_negociado",
        valor_anterior=str(atual),
        origem_anterior=(atual_row or {}).get("valor_negociado_origem"),
        valor_proposto=str(proposto),
        origem_proposto=tipo_documento,
        confianca_proposta=_confianca(leitura, campo),
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _aplicar_financiamento_parcela(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """[Q6] financiamento parcela = valor financiado + FGTS. `guia_itbi`
    never proposes this (it has no `valor_financiado`)."""
    if tipo_documento == "guia_itbi":
        return None, None
    financiado = _dec(getattr(leitura, "valor_financiado", None))
    if financiado is None:
        return None, None
    fgts = _dec(getattr(leitura, "valor_fgts", None)) or Decimal("0")
    proposto = financiado + fgts

    parcelas = (
        _t(client, PARCELAS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("tipo", "financiamento")
        .execute()
    ).data or []

    if len(parcelas) >= 2:
        return "varias_parcelas_financiamento", None

    now = _now()
    if not parcelas:
        ordem_atual = (
            _t(client, PARCELAS_TABLE)
            .select("ordem")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", str(atendimento_id))
            .execute()
        ).data or []
        ordem = max((r.get("ordem", 0) for r in ordem_atual), default=-1) + 1
        _t(client, PARCELAS_TABLE).insert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "atendimento_id": str(atendimento_id),
                "tipo": "financiamento",
                "valor": str(proposto),
                "confissao_divida": False,
                "dispara_corretagem": False,
                "ordem": ordem,
                "origem": tipo_documento,
                "documento_id": str(documento_id),
                "extraido_em": now,
                "confirmado_por": None,
                "confirmado_em": None,
                "created_at": now,
            }
        ).execute()
        return None, None

    parcela = parcelas[0]
    atual = _dec(parcela.get("valor"))
    if atual is None:
        _t(client, PARCELAS_TABLE).update(
            {
                "valor": str(proposto),
                "origem": tipo_documento,
                "documento_id": str(documento_id),
                "extraido_em": now,
                "confirmado_por": None,
                "confirmado_em": None,
                "updated_at": now,
            }
        ).eq("id", parcela["id"]).execute()
        return None, None

    if atual == proposto:
        return None, None

    novo = campo_conflitos.registrar_conflito(
        client, ATENDIMENTO, org_id, atendimento_id, f"parcela.{parcela['id']}.valor",
        valor_anterior=str(atual),
        origem_anterior=parcela.get("origem"),
        valor_proposto=str(proposto),
        origem_proposto=tipo_documento,
        confianca_proposta=_confianca(leitura, "valor_financiado"),
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _linha_financiamento(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, FINANCIAMENTO_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _gravar_financiamento(
    client: Any, org_id: UUID, atendimento_id: UUID, atual: Optional[dict], patch: dict,
) -> None:
    now = _now()
    if atual is None:
        _t(client, FINANCIAMENTO_TABLE).insert(
            {
                "atendimento_id": str(atendimento_id),
                "org_id": str(org_id),
                "situacao": "pendente",
                "fgts": False,
                "created_at": now,
                **patch,
            }
        ).execute()
    else:
        patch["updated_at"] = now
        _t(client, FINANCIAMENTO_TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "atendimento_id", str(atendimento_id)
        ).execute()


def _aplicar_fgts(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """Fill-empty judged by `fgts_origem IS NULL`, NOT by the boolean's
    value — a NOT NULL boolean's `false` is indistinguishable from unset."""
    if tipo_documento != "contrato_financiamento":
        return None, None
    valor_fgts = _dec(getattr(leitura, "valor_fgts", None))
    if valor_fgts is None or valor_fgts <= 0:
        return None, None

    atual = _linha_financiamento(client, org_id, atendimento_id)
    if atual is None or atual.get("fgts_origem") is None:
        _gravar_financiamento(
            client, org_id, atendimento_id, atual,
            {
                "fgts": True,
                "fgts_origem": tipo_documento,
                "fgts_documento_id": str(documento_id),
                "fgts_em": _now(),
                "fgts_confirmado_por": None,
                "fgts_confirmado_em": None,
            },
        )
        return None, None

    if bool(atual.get("fgts")) == True:  # noqa: E712 - explicit boolean compare, matches proposto
        return None, None

    novo = campo_conflitos.registrar_conflito(
        client, ATENDIMENTO, org_id, atendimento_id, "financiamento.fgts",
        valor_anterior=bool(atual.get("fgts")),
        origem_anterior=atual.get("fgts_origem"),
        valor_proposto=True,
        origem_proposto=tipo_documento,
        confianca_proposta=_confianca(leitura, "valor_fgts"),
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _aplicar_numero_proposta(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    if tipo_documento != "proposta_financiamento":
        return None, None
    proposto = getattr(leitura, "numero_proposta", None)
    if _vazio(proposto):
        return None, None

    atual = _linha_financiamento(client, org_id, atendimento_id)
    if atual is None or atual.get("numero_proposta_origem") is None:
        _gravar_financiamento(
            client, org_id, atendimento_id, atual,
            {
                "numero_proposta": proposto,
                "numero_proposta_origem": tipo_documento,
                "numero_proposta_documento_id": str(documento_id),
                "numero_proposta_em": _now(),
                "numero_proposta_confirmado_por": None,
                "numero_proposta_confirmado_em": None,
            },
        )
        return None, None

    if str(atual.get("numero_proposta")) == str(proposto):
        return None, None

    novo = campo_conflitos.registrar_conflito(
        client, ATENDIMENTO, org_id, atendimento_id, "financiamento.numero_proposta",
        valor_anterior=atual.get("numero_proposta"),
        origem_anterior=atual.get("numero_proposta_origem"),
        valor_proposto=proposto,
        origem_proposto=tipo_documento,
        # Vision-read ⇒ confiança baixa, unconditionally (§B).
        confianca_proposta="baixa",
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _aplicar_agente_financeiro(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """H7 (owner, binding): auto-create the `agentes_financeiros` row when
    the bank code matches none — logged. Ambiguous (>1 active match) still
    gets the aviso, no write."""
    codigo = getattr(leitura, "banco_codigo", None)
    if _vazio(codigo):
        return None, None

    ativos = (
        _t(client, "agentes_financeiros")
        .select("id,codigo_banco")
        .eq("org_id", str(org_id))
        .eq("ativo", True)
        .eq("codigo_banco", str(codigo))
        .execute()
    ).data or []

    if len(ativos) > 1:
        return "agente_financeiro_nao_cadastrado", None

    if not ativos:
        from app.modules.agentes_financeiros import service as agentes_svc

        nome = getattr(leitura, "banco_nome", None) or f"Banco {codigo}"
        criado = agentes_svc.criar(
            client, org_id,
            dados={"nome": nome, "codigo_banco": str(codigo)},
            user_id=None,
            origem="auto",
        )
        logger.info(
            "negociacao_extracao: auto-created agentes_financeiros %s "
            "(codigo_banco=%s) for org %s from %s %s",
            criado["id"], codigo, org_id, tipo_documento, documento_id,
        )
        agente_id = criado["id"]
    else:
        agente_id = ativos[0]["id"]

    atual = _linha_financiamento(client, org_id, atendimento_id)
    if atual is None or atual.get("agente_financeiro_origem") is None:
        _gravar_financiamento(
            client, org_id, atendimento_id, atual,
            {
                "agente_financeiro_id": str(agente_id),
                "agente_financeiro_origem": tipo_documento,
                "agente_financeiro_documento_id": str(documento_id),
                "agente_financeiro_em": _now(),
                "agente_financeiro_confirmado_por": None,
                "agente_financeiro_confirmado_em": None,
            },
        )
        return None, None

    if str(atual.get("agente_financeiro_id")) == str(agente_id):
        return None, None

    novo = campo_conflitos.registrar_conflito(
        # 🔴 `financiamento.agente_financeiro` — bare, no `_id` suffix. The
        # DB COLUMN is `agente_financeiro_id`; the CONFLICT campo string
        # matches S2b's D2 REGISTRO vocabulary (`ENTIDADE_FINANCIAMENTO`'s
        # `agente_financeiro` field), a different namespace on purpose.
        client, ATENDIMENTO, org_id, atendimento_id, "financiamento.agente_financeiro",
        valor_anterior=atual.get("agente_financeiro_id"),
        origem_anterior=atual.get("agente_financeiro_origem"),
        valor_proposto=str(agente_id),
        origem_proposto=tipo_documento,
        confianca_proposta=_confianca(leitura, "banco_codigo"),
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _aplicar_situacao(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """H6 (owner, binding): a signed `contrato_financiamento` sets
    `situacao='aprovado'`. "Signed" is read as `quadro_encontrado=True` (the
    Quadro Resumo prints the terms of an EXECUTED financing operation — see
    this module's docstring).

    D1, same shape as `_aplicar_fgts`: fill-empty judged by `situacao_
    origem IS NULL` (`situacao` itself defaults to `'pendente'`, not NULL,
    so the boolean-style column can't tell "never claimed" from "claimed
    pendente"). `situacao='recusado'` — whoever set it, manual or machine —
    is a genuine disagreement with `'aprovado'`, opened as a conflict, NEVER
    silently overridden; a human's refusal is not silently reopened by a
    later document. `financiamento.situacao` is S2b's D2 REGISTRO vocabulary
    (`ENTIDADE_FINANCIAMENTO`'s own field name).
    """
    if tipo_documento != "contrato_financiamento":
        return None, None
    if not getattr(leitura, "quadro_encontrado", False):
        return None, None

    atual = _linha_financiamento(client, org_id, atendimento_id)
    situacao_atual = (atual or {}).get("situacao", "pendente")
    origem_atual = (atual or {}).get("situacao_origem")

    if origem_atual is None:
        if situacao_atual == "aprovado":
            # Already agrees (e.g. a pre-171 manual approval) — just
            # backfill provenance, no conflict: the values already match.
            _gravar_financiamento(
                client, org_id, atendimento_id, atual,
                {"situacao_origem": tipo_documento, "situacao_documento_id": str(documento_id)},
            )
            return None, None
        _gravar_financiamento(
            client, org_id, atendimento_id, atual,
            {
                "situacao": "aprovado",
                "situacao_em": _now(),
                "situacao_por": None,
                "situacao_origem": tipo_documento,
                "situacao_documento_id": str(documento_id),
            },
        )
        logger.info(
            "negociacao_extracao: %s -> aprovado for atendimento %s (org %s) "
            "— quadro_encontrado on %s",
            situacao_atual, atendimento_id, org_id, documento_id,
        )
        return None, None

    if situacao_atual == "aprovado":
        return None, None

    novo = campo_conflitos.registrar_conflito(
        client, ATENDIMENTO, org_id, atendimento_id, "financiamento.situacao",
        valor_anterior=situacao_atual,
        origem_anterior=origem_atual,
        valor_proposto="aprovado",
        origem_proposto=tipo_documento,
        confianca_proposta=None,
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
        documento_id_proposto=documento_id,
    )
    return None, novo


def _aplicar_favorecido_vendedor(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any, cpfs_negocio: dict[str, dict],
) -> None:
    """H5 (owner, binding): the Quadro Resumo's printed seller credit
    account fills a favorecido, matched to a vendedor by CPF.

    D1 fill-empty ONLY — `atendimento_campo_conflitos.campo`'s closed
    vocabulary (contract §C.6) has no `favorecido.*` entry, so a
    disagreeing bank field on an EXISTING favorecido is left untouched
    rather than conflict-escalated. `NOC-REMEDIATE[favorecido-campo-
    conflito]` names that gap for a future slice.
    """
    if tipo_documento != "contrato_financiamento":
        return
    conta = getattr(leitura, "conta_credito_vendedor", None)
    if conta is None:
        return
    # S1 shape (`ContaCreditoVendedor`): `titular_cpf` / `titular_cpf_valido`
    # — NOT `cpf`/`cpf_cnpj`. A CPF that failed its check-digit is never
    # trusted for a match, same discipline every other person-field in this
    # module applies (`_cpfs_lidos`).
    if not getattr(conta, "titular_cpf_valido", False):
        return
    cpf_vendedor = getattr(conta, "titular_cpf", None)
    if not cpf_vendedor:
        return
    cpf_norm = cpf_docs.only_digits(str(cpf_vendedor))
    parte = cpfs_negocio.get(cpf_norm)
    if parte is None or parte.get("lado") != "vendedor":
        return

    favorecidos = (
        _t(client, FAVORECIDOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("cpf_cnpj", cpf_norm)
        .execute()
    ).data or []

    # `ContaCreditoVendedor` has no `pix` field — the Quadro Resumo prints
    # a bank account, never a PIX key; `atendimento_favorecidos.pix` simply
    # never fills from this source.
    campos_banco = {
        "banco": getattr(conta, "banco_nome", None),
        "agencia": getattr(conta, "agencia", None),
        "conta": getattr(conta, "conta", None),
    }
    now = _now()
    if favorecidos:
        atual = favorecidos[0]
        patch = {
            k: v for k, v in campos_banco.items()
            if v is not None and _vazio(atual.get(k))
        }
        if not patch:
            return
        patch["updated_at"] = now
        if atual.get("origem") is None:
            patch["origem"] = tipo_documento
            patch["documento_id"] = str(documento_id)
            patch["extraido_em"] = now
        _t(client, FAVORECIDOS_TABLE).update(patch).eq("id", atual["id"]).execute()
        return

    _t(client, FAVORECIDOS_TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "atendimento_id": str(atendimento_id),
            "nome": parte.get("nome") or cpf_norm,
            "cpf_cnpj": cpf_norm,
            **campos_banco,
            "origem": tipo_documento,
            "documento_id": str(documento_id),
            "extraido_em": now,
            "confirmado_por": None,
            "confirmado_em": None,
            "created_at": now,
        }
    ).execute()


# ─── (c) light cross-document checks ─────────────────────────────────────


def _avisos_cross_documento(
    client: Any, org_id: UUID, atendimento_id: UUID, tipo_documento: str,
    documento_id: UUID, leitura: Any,
) -> list[str]:
    """Best-effort money cross-checks against the OTHER already-extracted
    documents of this deal (§E2.c). Never opens a conflict on its own — a
    mismatch is surfaced as an `extracao_aviso` on THIS document; the D1
    field map above is the only path that ever writes a DB column.

    🔴 SCOPE CUT: the ITBI inscrição/matrícula vs `imovel_dados` cross-check
    is NOT implemented here — it needs the deal's resolved imóvel plus its
    registry columns, a materially bigger read than the money checks below,
    and was out of this slice's effort budget. `NOC-REMEDIATE[sw-neg-cross-
    doc-imovel-check]` — 2026-09-25.
    """
    avisos: list[str] = []
    outros = (
        _t(client, DOCUMENTOS_TABLE)
        .select("tipo_documento,extracao_dados")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("extracao_status", "ok")
        .is_("deleted_at", "null")
        .neq("id", str(documento_id))
        .execute()
    ).data or []
    leituras_outras = {
        row["tipo_documento"]: row.get("extracao_dados") or {} for row in outros
    }

    if tipo_documento == "guia_itbi":
        transacao = _dec(getattr(leitura, "valor_transacao", None))
        for outro_tipo in ("contrato_financiamento", "proposta_financiamento"):
            dados = leituras_outras.get(outro_tipo)
            if not dados or transacao is None:
                continue
            outro_valor = _dec(dados.get("valor_compra_venda"))
            if outro_valor is not None and outro_valor != transacao:
                avisos.append("itbi_transacao_diverge_contrato")
    elif tipo_documento in ("contrato_financiamento", "proposta_financiamento"):
        compra_venda = _dec(getattr(leitura, "valor_compra_venda", None))
        dados_itbi = leituras_outras.get("guia_itbi")
        if dados_itbi and compra_venda is not None:
            transacao = _dec(dados_itbi.get("valor_transacao"))
            if transacao is not None and transacao != compra_venda:
                avisos.append("itbi_transacao_diverge_contrato")

    return avisos


# ─── orchestration ────────────────────────────────────────────────────────


def aplicar_leitura(
    client: Any, org_id: UUID, atendimento_id: UUID, documento_id: UUID,
    tipo_documento: str, leitura: Any,
) -> dict:
    """(b)-(d) — strictly in this order (contract §E2). Never raises for a
    disagreement (a conflict is a normal outcome); an exception here is the
    caller's (`extrair`'s) job to catch and turn into `erro` (lesson G6).

    Returns `{"status": OK|SEM_DADOS, "aviso": str|None, "conflitos": [...]}`.
    """
    cpfs_negocio = _cpfs_do_negocio(client, org_id, atendimento_id)
    if not _pertence_ao_negocio(leitura, cpfs_negocio):
        return {"status": SEM_DADOS, "aviso": "documento_de_outro_negocio", "conflitos": []}

    # The SEED PARSER's own aviso (e.g. `quadro_resumo_soma_divergente` —
    # §D.5) rides on `leitura.aviso`; this module's own avisos (below) are
    # about what the APPLY step found, a different axis of the same field.
    avisos: list[str] = []
    aviso_seed = getattr(leitura, "aviso", None)
    if aviso_seed:
        avisos.append(aviso_seed)
    avisos.extend(_avisos_cross_documento(
        client, org_id, atendimento_id, tipo_documento, documento_id, leitura,
    ))
    conflitos: list[dict] = []

    for aplicar in (
        _aplicar_valor_negociado,
        _aplicar_financiamento_parcela,
        _aplicar_fgts,
        _aplicar_numero_proposta,
        _aplicar_agente_financeiro,
        _aplicar_situacao,
    ):
        aviso, conflito = aplicar(
            client, org_id, atendimento_id, tipo_documento, documento_id, leitura,
        )
        if aviso:
            avisos.append(aviso)
        if conflito is not None:
            conflitos.append(conflito)

    _aplicar_favorecido_vendedor(
        client, org_id, atendimento_id, tipo_documento, documento_id, leitura, cpfs_negocio,
    )

    # H4 — recompute the derived intermediária suggestion now that
    # valor_negociado and/or the financiamento parcela may have moved.
    cliente_id = _cliente_titular(client, org_id, atendimento_id)
    if cliente_id is not None:
        neg_estruturada.sincronizar_parcela_intermediaria_derivada(
            client, org_id, cliente_id,
        )

    achou_algo = any(
        not _vazio(getattr(leitura, campo, None))
        for campo in fontes.FONTES[tipo_documento].campos
    )
    return {
        "status": OK if achou_algo else SEM_DADOS,
        "aviso": "; ".join(avisos) if avisos else None,
        "conflitos": conflitos,
    }


def _cliente_titular(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[UUID]:
    rows = (
        _t(client, "atendimentos")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    cid = (rows[0] if rows else {}).get("cliente_id")
    return UUID(str(cid)) if cid else None


async def extrair(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    atendimento_id: UUID,
    documento_id: UUID,
    *,
    extractor: Any,
    notification_service: Optional[Any] = None,
) -> dict:
    """The background job the upload/re-run routes schedule — `financiamento
    _service`'s sibling of `empresas.extracao_service.extrair_cartao` /
    `identidade_extracao_service.extrair_identidade`.

    🔴 (a) `extracao_dados`/`extracao_fonte` are written BEFORE `status='ok'`
    — never after (lesson G6: Crednet once stamped `ok` before its side
    effects crashed). An exception in `aplicar_leitura` ends in `erro`,
    with the reading already safely on the document.
    """
    documento = _documento(client, org_id, documento_id)
    if documento is None:
        logger.warning(
            "negociacao_extracao: documento %s not found for org %s", documento_id, org_id,
        )
        return {"status": ERRO, "erro": "documento_nao_encontrado"}
    if documento.get("deleted_at"):
        return {"status": ERRO, "erro": "documento_removido"}
    tipo_documento = documento["tipo_documento"]
    if not financiamento_service.deve_extrair(tipo_documento):
        return {"status": ERRO, "erro": "tipo_nao_extraivel"}

    tentativas = int(documento.get("extracao_tentativas") or 0) + 1
    _marcar_documento(
        client, documento_id,
        extracao_status="processando", extracao_em=_now(), extracao_tentativas=tentativas,
    )

    try:
        blob = await storage.get(bucket=financiamento_service.BUCKET, key=documento["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("negociacao_extracao %s: storage read failed: %s", documento_id, exc)
        _marcar_documento(
            client, documento_id, extracao_status="erro",
            extracao_erro=f"storage: {exc}", extracao_em=_now(),
        )
        return {"status": ERRO, "erro": "storage"}
    if blob is None:
        _marcar_documento(
            client, documento_id, extracao_status="erro",
            extracao_erro="objeto ausente no storage", extracao_em=_now(),
        )
        return {"status": ERRO, "erro": "objeto_ausente"}

    # A content read is logged BEFORE the extraction — same rule every
    # sibling in this product follows. `usuario_id=None`: this is a detached
    # background task, not a request-scoped read.
    financiamento_service.STORE.log_acesso(client, org_id, documento_id, None, "extract")

    leitura = await extractor.extract(
        blob.data, mimetype=documento.get("mime_type"), filename=documento.get("nome_original"),
    )

    erro = getattr(leitura, "error", None)
    if erro:
        # 🔴 THE DPS TRIPWIRE (§D.5/H8): the reading is NEVER persisted —
        # `extracao_dados` stays whatever it already was (nothing, on a
        # first read). Every other error follows the same "never persist a
        # failed reading" rule the sibling extractors already use.
        _marcar_documento(
            client, documento_id, extracao_status="erro",
            extracao_erro=f"{erro}: {getattr(leitura, 'error_message', '') or ''}".strip(": "),
            extracao_fonte=getattr(getattr(leitura, "source", None), "value", getattr(leitura, "source", None)),
            extracao_em=_now(),
        )
        return {"status": ERRO, "erro": erro}

    # 🔴 EVERYTHING FROM HERE ON IS ONE FAILURE DOMAIN. Serialising the
    # reading and applying it are two different operations, but a failure
    # in EITHER must land the same way — `erro`, never an uncaught
    # exception left to crash the detached background task (which would
    # strand the document in `processando` until the D3 sweep's stale
    # timeout, rather than surfacing immediately) and never a false `ok`
    # (lesson G6: Crednet once stamped `ok` before its side effects
    # crashed).
    try:
        _marcar_documento(
            client, documento_id,
            extracao_fonte=getattr(getattr(leitura, "source", None), "value", getattr(leitura, "source", None)),
            extracao_dados=_json_seguro(leitura),
            extracao_em=_now(),
        )
        resultado = aplicar_leitura(client, org_id, atendimento_id, documento_id, tipo_documento, leitura)
    except Exception as exc:  # noqa: BLE001 - lesson G6: never a false 'ok'
        logger.exception(
            "negociacao_extracao %s: apply failed for tipo=%s", documento_id, tipo_documento,
        )
        _marcar_documento(
            client, documento_id, extracao_status="erro",
            extracao_erro=f"aplicar_leitura: {exc}", extracao_em=_now(),
        )
        return {"status": ERRO, "erro": "aplicar_leitura"}

    conflitos = resultado.get("conflitos") or []
    if conflitos:
        async def _notify_one(conflito: dict) -> None:  # pragma: no cover - exercised only with a real notifier
            await notification_service.notify_atendimento_field_conflict(
                org_id=org_id, conflito=conflito,
            )

        await campo_conflitos.notificar_conflitos(
            client, ATENDIMENTO, conflitos,
            _notify_one if notification_service is not None else None,
        )

    # (e) — only NOW the terminal status lands.
    _marcar_documento(
        client, documento_id,
        extracao_status=resultado["status"], extracao_aviso=resultado.get("aviso"),
        extracao_erro=None, extracao_em=_now(),
    )
    return {**resultado, "conflitos": len(conflitos)}


# ─── D2: per-document confirm (§E5.2), conflict resolution (§E5.4) ───────


#: `(tabela, owner_col_alvo)` and the prefix→campo map per D1 surface, so
#: `confirmar_leitura` walks all three tables from one place rather than
#: three near-identical loops.
_QUINTETOS_NEGOCIACAO: tuple[str, ...] = ("valor_negociado",)
_QUINTETOS_FINANCIAMENTO: tuple[str, ...] = ("fgts", "numero_proposta", "agente_financeiro")


def confirmar_leitura(client: Any, org_id: UUID, atendimento_id: UUID, documento_id: UUID, *, confirmado_por: Optional[UUID]) -> dict:
    """`POST .../extracao/confirmar` (§E5.2) — stamps `confirmado_*` on
    every STILL-PENDING value whose `*_documento_id == documento_id`,
    across all three surfaces. Idempotent: a value already confirmed (or
    proposed by a DIFFERENT document) is left untouched."""
    now = _now()
    confirmados = 0

    negociacao = (
        _t(client, NEGOCIACAO_TABLE).select("*").eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id)).limit(1).execute()
    ).data or []
    if negociacao:
        row = negociacao[0]
        if (
            str(row.get("valor_negociado_documento_id")) == str(documento_id)
            and row.get("valor_negociado_confirmado_em") is None
        ):
            _t(client, NEGOCIACAO_TABLE).update(
                {
                    "valor_negociado_confirmado_por": str(confirmado_por) if confirmado_por else None,
                    "valor_negociado_confirmado_em": now,
                }
            ).eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id)).execute()
            confirmados += 1

    parcelas = (
        _t(client, PARCELAS_TABLE).select("id,documento_id,confirmado_em")
        .eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id))
        .eq("documento_id", str(documento_id)).is_("confirmado_em", "null")
        .execute()
    ).data or []
    for parcela in parcelas:
        _t(client, PARCELAS_TABLE).update(
            {
                "confirmado_por": str(confirmado_por) if confirmado_por else None,
                "confirmado_em": now,
            }
        ).eq("id", parcela["id"]).execute()
        confirmados += 1

    financiamento = (
        _t(client, FINANCIAMENTO_TABLE).select("*").eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id)).limit(1).execute()
    ).data or []
    if financiamento:
        row = financiamento[0]
        patch: dict[str, Any] = {}
        for prefixo in _QUINTETOS_FINANCIAMENTO:
            if (
                str(row.get(f"{prefixo}_documento_id")) == str(documento_id)
                and row.get(f"{prefixo}_confirmado_em") is None
            ):
                patch[f"{prefixo}_confirmado_por"] = str(confirmado_por) if confirmado_por else None
                patch[f"{prefixo}_confirmado_em"] = now
        if patch:
            _t(client, FINANCIAMENTO_TABLE).update(patch).eq("org_id", str(org_id)).eq(
                "atendimento_id", str(atendimento_id)
            ).execute()
            confirmados += len(patch) // 2

    return {"confirmados": confirmados}


def listar_conflitos(client: Any, org_id: UUID, atendimento_id: Optional[UUID] = None) -> list[dict]:
    """Every pending `atendimento_campo_conflitos` row — scoped to one deal
    when `atendimento_id` is given, else the whole org's queue (mirrors
    `identidade_extracao_service.conflitos_pendentes`)."""
    q = (
        _t(client, ATENDIMENTO.table)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("status", "pendente")
    )
    if atendimento_id is not None:
        q = q.eq("atendimento_id", str(atendimento_id))
    rows = (q.execute()).data or []
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows


def resolver_conflito(
    client: Any, org_id: UUID, conflito_id: UUID, *, aceitar: bool, decidido_por: Optional[UUID],
) -> dict:
    """Accept or reject a pending `atendimento_campo_conflitos` row.

    ACCEPT applies `valor_proposto` onto the target column/row, confirmed-
    by-construction (`decidido_por` IS the confirming admin). REJECT does
    not touch the target at all — D1 never wrote over the disagreeing value
    in the first place, so `valor_anterior` is already what's live (mirrors
    `identidade_extracao_service.resolver_conflito`'s own contract).
    """
    rows = (
        _t(client, ATENDIMENTO.table).select("*").eq("org_id", str(org_id))
        .eq("id", str(conflito_id)).limit(1).execute()
    ).data or []
    if not rows:
        from noctusai_lib.primitives.exceptions import NotFoundError

        raise NotFoundError(ATENDIMENTO.table, str(conflito_id))
    conflito = rows[0]
    if conflito.get("status") != "pendente":
        from noctusai_lib.primitives.exceptions import ValidationError_

        raise ValidationError_("Este conflito já foi decidido.", field="status")

    now = _now()
    patch = {
        "status": "aceito" if aceitar else "rejeitado",
        "decidido_por": str(decidido_por) if decidido_por else None,
        "decidido_em": now,
    }
    _t(client, ATENDIMENTO.table).update(patch).eq("id", str(conflito_id)).execute()

    if aceitar:
        _aplicar_conflito_aceito(client, org_id, conflito, decidido_por=decidido_por)

    return {**conflito, **patch}


def _aplicar_conflito_aceito(client: Any, org_id: UUID, conflito: dict, *, decidido_por: Optional[UUID]) -> None:
    campo = conflito["campo"]
    atendimento_id = conflito["atendimento_id"]
    now = _now()
    quem = str(decidido_por) if decidido_por else None
    proposto = conflito["valor_proposto"]
    documento_id = conflito.get("fonte_id")

    if campo == "valor_negociado":
        _t(client, NEGOCIACAO_TABLE).update(
            {
                "valor_negociado": proposto,
                "valor_negociado_origem": conflito["origem_proposto"],
                "valor_negociado_documento_id": documento_id,
                "valor_negociado_em": now,
                "valor_negociado_confirmado_por": quem,
                "valor_negociado_confirmado_em": now,
            }
        ).eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id)).execute()
        return

    if campo.startswith("parcela.") and campo.endswith(".valor"):
        parcela_id = campo.split(".", 2)[1]
        _t(client, PARCELAS_TABLE).update(
            {
                "valor": proposto,
                "origem": conflito["origem_proposto"],
                "documento_id": documento_id,
                "extraido_em": now,
                "confirmado_por": quem,
                "confirmado_em": now,
                "updated_at": now,
            }
        ).eq("id", parcela_id).execute()
        return

    if campo.startswith("financiamento."):
        # `campo` (the conflict-table key, S2b's D2 REGISTRO vocabulary) and
        # the DB COLUMN can differ — today only `agente_financeiro` (campo)
        # vs `agente_financeiro_id` (column); every other financiamento
        # campo is spelled identically on both sides.
        prefixo = campo.split(".", 1)[1]
        coluna = "agente_financeiro_id" if prefixo == "agente_financeiro" else prefixo
        _t(client, FINANCIAMENTO_TABLE).update(
            {
                coluna: proposto,
                f"{prefixo}_origem": conflito["origem_proposto"],
                f"{prefixo}_documento_id": documento_id,
                f"{prefixo}_em": now,
                f"{prefixo}_confirmado_por": quem,
                f"{prefixo}_confirmado_em": now,
            }
        ).eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id)).execute()
        return

    logger.warning("resolver_conflito: campo %r has no apply rule — accepted, not applied", campo)


# ─── D3: the recovery sweep, via the shared `extracao_varredura` ─────────
#
# The recurrence rule (contract §E3.3): a FIFTH hand-rolled sweep of the
# same shape `empresas.sweep_service` already had — stale non-terminal /
# never-started / retryable-error, one bad row skipped rather than stopping
# the run — is forbidden. This composes `app.services.extracao_varredura`
# the same way `empresas.sweep_service` was migrated onto it in this slice.

JOB_ID = "negociacao_extracao_sweep"

#: Every hour at :31 — offset from `card_hub` (:17), `empresas` (:23), so
#: no two extraction sweeps land on the same minute.
CRON = "31 * * * *"

_COLUNAS_VARREDURA = (
    "id, org_id, atendimento_id, tipo_documento, extracao_status, "
    "extracao_tentativas, extracao_em, created_at"
)


def _sweep_config(extractor_factory: Optional[Any]) -> Any:
    from app.services import extracao_varredura

    return extracao_varredura.SweepConfig(
        table=DOCUMENTOS_TABLE,
        owner_col="atendimento_id",
        colunas=_COLUNAS_VARREDURA,
        extrair_fn=extrair,
        extractor_factory=extractor_factory,
    )


async def _sweep(admin: Any, storage: Any) -> dict:
    from app.services import extracao_varredura

    from app.modules.card_hub.deps import get_identity_extractor_factory

    return await extracao_varredura.varrer(
        admin, storage, _sweep_config(get_identity_extractor_factory()),
        # NOC-REMEDIATE[atendimento-conflito-notificacao] — see `extrair`'s
        # own note; no atendimento-scoped notifier exists yet.
        notification_service=None,
    )


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent. Must run
    at IMPORT time, before `start_scheduler()` fires in `app/lifespan.py`
    (`card_hub.__init__.register()` is where every sibling sweep in this
    module does exactly that)."""
    from app.services.extraction_sweep import configure_sweep

    configure_sweep(job_id=JOB_ID, cron=CRON, label="negociacao_extracao", sweep=_sweep)


__all__ = [
    "ATENDIMENTO",
    "CRON",
    "ERRO",
    "ERRO_DPS",
    "JOB_ID",
    "OK",
    "SEM_DADOS",
    "aplicar_leitura",
    "configure",
    "confirmar_leitura",
    "extrair",
    "listar_conflitos",
    "resolver_conflito",
]
