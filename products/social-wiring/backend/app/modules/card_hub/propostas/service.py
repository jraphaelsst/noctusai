"""Propostas CRUD (CONTRACT §4.2) — list / create(prefilled) / get / patch /
enviar / recusar / delete, and the `Proposta` output shape.

Aceitar and the post-aceite re-run live in `aceite.py` (another slice) and are
reached from the router only.

Nothing here BLOCKS a save on incompleteness: `saldo_nao_alocado` and
`completude` are reported. What is refused is a WRONG value (400), an unknown
id (404) or a state conflict (409, machine `code`).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import ValidationError as PydanticValidationError

from noctusai_lib.primitives.exceptions import (
    AppException,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import negociacao_service
from app.modules.card_hub import services as svc
from app.modules.card_hub.propostas.schemas import (
    REF_FAVORECIDO,
    REF_PARCELA,
    SNAPSHOT_MODELS,
    PropostaCreateBody,
    PropostaPatchBody,
    dump_snapshot,
)
from app.modules.imovel_hub import busca_service as imovel_busca
from app.services import imobiliarias_service
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

TABLE = "atendimento_propostas"
TESTEMUNHAS_REGISTRO = "org_testemunhas"
VISITAS_TABLE = "visitas"
ROTEIROS_TABLE = "roteiros"

STATUS_ABERTOS = ("rascunho", "enviada")
STATUS_FECHADOS = ("aceita", "recusada", "cancelada")

EVENTO_PROPOSTA_CRIADA = "proposta_criada"


# ─── errors (machine `code` per CONTRACT §4.2) ─────────────────────────────


class PropostaConflito(AppException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class SnapshotInvalido(AppException):
    """400 `snapshot_invalido` — `details.campos` = [{path, mensagem}]."""

    def __init__(self, campos: list[dict]) -> None:
        super().__init__(
            code="snapshot_invalido",
            message="Os dados da proposta têm campos inválidos: "
            + "; ".join(c["path"] for c in campos[:5])
            + ("…" if len(campos) > 5 else ""),
            status_code=400,
            details={"campos": campos},
        )


class MotivoObrigatorio(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="motivo_obrigatorio",
            message="Informe o motivo da recusa.",
            status_code=400,
            details={"field": "motivo"},
        )


def _proposta_fechada(status: str) -> PropostaConflito:
    return PropostaConflito(
        "proposta_fechada",
        f"A proposta está {status} e não pode mais ser alterada.",
    )


# ─── helpers ────────────────────────────────────────────────────────────────


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _str_num(value: Any) -> Optional[str]:
    d = _dec(value)
    return None if d is None else str(d)


def _ator(user_id: Any) -> Optional[str]:
    return str(user_id) if user_id else None


def _atendimento_id(client: Any, org_id: UUID, cliente_id: UUID) -> UUID:
    return UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))


# ─── refs into the snapshot ─────────────────────────────────────────────────


def _checar_ref(ref: Any, prefixo: str, total: int, campo: str, erros: list[dict]) -> None:
    if ref in (None, ""):
        return
    partes = str(ref).split(":")
    if len(partes) != 2 or partes[0] != prefixo or not partes[1].isdigit():
        erros.append({"path": campo, "mensagem": f'Referência inválida: use "{prefixo}:<índice>".'})
    elif int(partes[1]) >= total:
        erros.append({"path": campo, "mensagem": f"{ref} não existe neste rascunho."})


def _erros_refs(
    parcelas: list[dict], favorecidos: list[dict], intermediarios: list[dict], termos: dict
) -> list[dict]:
    """Every client-side ref points at an existing index of the snapshot."""
    erros: list[dict] = []
    nf, np_ = len(favorecidos), len(parcelas)
    for i, p in enumerate(parcelas):
        _checar_ref(p.get("favorecido_ref"), REF_FAVORECIDO, nf, f"parcelas.{i}.favorecido_ref", erros)
        for j, d in enumerate(p.get("favorecidos_divisao") or []):
            _checar_ref(
                d.get("favorecido_ref"), REF_FAVORECIDO, nf,
                f"parcelas.{i}.favorecidos_divisao.{j}.favorecido_ref", erros,
            )
    for i, it in enumerate(intermediarios):
        _checar_ref(it.get("favorecido_ref"), REF_FAVORECIDO, nf, f"intermediarios.{i}.favorecido_ref", erros)
    for campo in ("posse_marco_parcela_ref", "permuta_posse_marco_parcela_ref"):
        _checar_ref(termos.get(campo), REF_PARCELA, np_, f"termos.{campo}", erros)
    return erros


def _erros_modelo(modelo: Any, valor: Any, prefixo: str) -> tuple[Any, list[dict]]:
    try:
        return dump_snapshot(modelo.model_validate(valor)), []
    except PydanticValidationError as exc:
        return None, [
            {
                "path": ".".join([prefixo, *(str(x) for x in e["loc"])]),
                "mensagem": e["msg"],
            }
            for e in exc.errors()
        ]


def validar_snapshots(enviados: dict[str, Any], atual: dict) -> dict[str, Any]:
    """Validate the snapshot keys present in `enviados` against the live-set
    shapes, then every ref of the MERGED state. Returns the JSON-safe values to
    store; raises `SnapshotInvalido` listing ALL failing paths."""
    erros: list[dict] = []
    saida: dict[str, Any] = {}
    for chave, modelo in SNAPSHOT_MODELS.items():
        if chave not in enviados:
            continue
        valor = enviados[chave]
        if chave == "termos":
            saida[chave], e = _erros_modelo(modelo, valor, chave)
            erros += e
            continue
        itens = []
        for i, item in enumerate(valor):
            ok, e = _erros_modelo(modelo, item, f"{chave}.{i}")
            itens.append(ok)
            erros += e
        saida[chave] = itens
    if not erros:
        mesclado = {**atual, **saida}
        erros = _erros_refs(
            mesclado.get("parcelas") or [], mesclado.get("favorecidos") or [],
            mesclado.get("intermediarios") or [], mesclado.get("termos") or {},
        )
    if erros:
        raise SnapshotInvalido(erros)
    return saida


# ─── lookups (batched) ──────────────────────────────────────────────────────


def _endereco(imovel: dict) -> Optional[str]:
    rua = " ".join(str(x) for x in (imovel.get("logradouro"), imovel.get("numero")) if x)
    cidade = "/".join(str(x) for x in (imovel.get("cidade"), imovel.get("uf")) if x)
    partes = [p for p in (rua, imovel.get("bairro"), cidade) if p]
    return ", ".join(partes) or None


def carregar_contexto(client: Any, org_id: UUID, rows: list[dict]) -> dict:
    """Every lookup `proposta_out` needs for `rows`, one batched read per source."""
    codigos = sorted({str(r["imovel_codigo"]) for r in rows if r.get("imovel_codigo")})
    imoveis = imovel_busca.enriquecer(client, org_id, codigos) if codigos else {}

    visita_ids = sorted({str(r["visita_id"]) for r in rows if r.get("visita_id")})
    visitas = {
        str(v["id"]): v
        for v in table_reads.in_batched_rows(client, VISITAS_TABLE, org_id, "id", visita_ids)
    }
    roteiro_ids = sorted({str(v["roteiro_id"]) for v in visitas.values() if v.get("roteiro_id")})
    roteiros = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(client, ROTEIROS_TABLE, org_id, "id", roteiro_ids)
    }

    imob_ids = sorted({str(r["imobiliaria_id"]) for r in rows if r.get("imobiliaria_id")})
    imobiliarias = {
        str(i["id"]): i
        for i in table_reads.in_batched_rows(
            client, imobiliarias_service.TABLE, org_id, "id", imob_ids
        )
    }

    test_ids = sorted({str(t) for r in rows for t in (r.get("testemunha_ids") or [])})
    testemunhas = {
        str(t["id"]): t
        for t in table_reads.in_batched_rows(client, TESTEMUNHAS_REGISTRO, org_id, "id", test_ids)
    }

    # The "only active company" auto-selection used by completude.
    ativas = (
        _t(client, imobiliarias_service.TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .limit(2)
        .execute()
    ).data or []
    return {
        "imoveis": imoveis,
        "visitas": visitas,
        "roteiros": roteiros,
        "imobiliarias": imobiliarias,
        "testemunhas": testemunhas,
        "unica_imobiliaria_ativa": len(ativas) == 1,
    }


def saldo_nao_alocado(row: dict) -> Optional[str]:
    valor = _dec(row.get("valor_proposto"))
    if valor is None:
        return None
    alocado = sum((_dec(p.get("valor")) or Decimal("0")) for p in (row.get("parcelas") or []))
    return str(valor - alocado)


def completude(row: dict, ctx: dict) -> list[str]:
    """What the contract would still lack — reported, never blocking."""
    falta: list[str] = []
    if _dec(row.get("valor_proposto")) is None:
        falta.append("Valor da proposta")
    if _dec(row.get("pct_comissao")) is None:
        falta.append("Percentual de comissão")
    parcelas = row.get("parcelas") or []
    if not parcelas:
        falta.append("Parcelas do pagamento")
    else:
        saldo = _dec(saldo_nao_alocado(row))
        if saldo is not None and saldo != 0:
            falta.append(f"Parcelas não cobrem o valor (saldo não alocado: {saldo})")
        if any(p.get("tipo") != "financiamento" and p.get("tipo") != "fgts"
               and not p.get("favorecido_ref") and not p.get("favorecidos_divisao")
               for p in parcelas):
            falta.append("Favorecido de cada parcela")
    termos = row.get("termos") or {}
    if not termos.get("posse_marco"):
        falta.append("Marco da posse")
    if not termos.get("onus_quitacao"):
        falta.append("Quitação de ônus")
    if not termos.get("itens_integrantes") and not termos.get("itens_integrantes_ausente_confirmado"):
        falta.append("Itens integrantes")
    if not termos.get("corretagem_contratantes"):
        falta.append("Contratantes da corretagem")
    if not row.get("imobiliaria_id") and not ctx.get("unica_imobiliaria_ativa"):
        falta.append("Imobiliária que assina o contrato")
    return falta


def proposta_out(client: Any, org_id: UUID, row: dict, ctx: Optional[dict] = None) -> dict:
    """The full `Proposta` shape of CONTRACT §4.2."""
    if ctx is None:
        ctx = carregar_contexto(client, org_id, [row])
    codigo = row.get("imovel_codigo")
    imovel = ctx["imoveis"].get(imovel_busca.canonical(str(codigo))) if codigo else None
    visita = ctx["visitas"].get(str(row["visita_id"])) if row.get("visita_id") else None
    data_visita = None
    if visita:
        data_visita = (ctx["roteiros"].get(str(visita.get("roteiro_id"))) or {}).get("data_visita")
    imob = ctx["imobiliarias"].get(str(row["imobiliaria_id"])) if row.get("imobiliaria_id") else None
    testemunhas = []
    for tid in row.get("testemunha_ids") or []:
        t = ctx["testemunhas"].get(str(tid))
        testemunhas.append({"id": str(tid), "nome": (t or {}).get("nome")})

    return {
        "id": row["id"],
        "org_id": row.get("org_id"),
        "atendimento_id": row.get("atendimento_id"),
        "cliente_id": row.get("cliente_id"),
        "visita_id": row.get("visita_id"),
        "imovel_codigo": codigo,
        "status": row.get("status"),
        "valor_proposto": _str_num(row.get("valor_proposto")),
        "pct_comissao": _str_num(row.get("pct_comissao")),
        "financiamento": row.get("financiamento"),
        "fgts": row.get("fgts"),
        "validade_ate": row.get("validade_ate"),
        "observacoes": row.get("observacoes"),
        "parcelas": row.get("parcelas") or [],
        "favorecidos": row.get("favorecidos") or [],
        "intermediarios": row.get("intermediarios") or [],
        "termos": row.get("termos") or {},
        "imobiliaria_id": row.get("imobiliaria_id"),
        "testemunha_ids": [str(t) for t in (row.get("testemunha_ids") or [])],
        "enviada_em": row.get("enviada_em"),
        "aceita_em": row.get("aceita_em"),
        "aceita_por": row.get("aceita_por"),
        "recusada_em": row.get("recusada_em"),
        "recusada_por": row.get("recusada_por"),
        "motivo_recusa": row.get("motivo_recusa"),
        "contrato_id": row.get("contrato_id"),
        "created_at": row.get("created_at"),
        "created_por": row.get("created_por"),
        "updated_at": row.get("updated_at"),
        "updated_por": row.get("updated_por"),
        "imovel": {
            "codigo": codigo,
            "titulo": (imovel or {}).get("titulo"),
            "endereco": _endereco(imovel) if imovel else None,
        },
        "visita": {"id": row["visita_id"], "data_visita": data_visita} if visita else None,
        "imobiliaria": (
            {"id": imob.get("id"), "razao_social": imob.get("razao_social")} if imob else None
        ),
        "testemunhas": testemunhas,
        "saldo_nao_alocado": saldo_nao_alocado(row),
        "completude": completude(row, ctx),
    }


# ─── reads ──────────────────────────────────────────────────────────────────


def obter_linha(client: Any, org_id: UUID, atendimento_id: UUID, proposta_id: UUID) -> dict:
    """The proposta row, scoped to this org AND this atendimento (404 otherwise)."""
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("id", str(proposta_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("Proposta", str(proposta_id))
    return rows[0]


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    rows = table_reads.paged_rows(
        client, TABLE, org_id, eq_filters={"atendimento_id": str(atendimento_id)}
    )
    rows.sort(key=lambda r: (r.get("created_at") or "", str(r.get("id"))), reverse=True)
    ctx = carregar_contexto(client, org_id, rows)
    return [proposta_out(client, org_id, r, ctx) for r in rows]


def obter(client: Any, org_id: UUID, cliente_id: UUID, proposta_id: UUID) -> dict:
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    return proposta_out(client, org_id, obter_linha(client, org_id, atendimento_id, proposta_id))


# ─── create ─────────────────────────────────────────────────────────────────


def _visita_do_atendimento(client: Any, org_id: UUID, atendimento_id: UUID, visita_id: UUID) -> dict:
    visitas = (
        _t(client, VISITAS_TABLE).select("*").eq("org_id", str(org_id))
        .eq("id", str(visita_id)).limit(1).execute()
    ).data or []
    visita = visitas[0] if visitas else None
    if visita is None or visita.get("deleted_at"):
        raise NotFoundError("Visita", str(visita_id))
    roteiros = (
        _t(client, ROTEIROS_TABLE).select("atendimento_id,deleted_at").eq("org_id", str(org_id))
        .eq("id", str(visita.get("roteiro_id"))).limit(1).execute()
    ).data or []
    if (
        not roteiros
        or roteiros[0].get("deleted_at")
        or str(roteiros[0].get("atendimento_id")) != str(atendimento_id)
    ):
        raise NotFoundError("Visita", str(visita_id))
    return visita


def _pct_comissao_padrao(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[Decimal]:
    """`atendimento_negociacao.pct_comissao`, else the org default; None when
    neither is set (reported in `completude`, never guessed)."""
    rows = (
        _t(client, negociacao_service.TABLE).select("pct_comissao").eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id)).limit(1).execute()
    ).data or []
    atual = _dec(rows[0].get("pct_comissao")) if rows else None
    if atual is not None:
        return atual
    return negociacao_service.resolver_defaults(client, org_id).get("pct_comissao")


def _emitir_funil(client: Any, org_id: UUID, atendimento_id: UUID, actor: Any) -> dict:
    """`proposta_criada` -> funnel (CONTRACT §6). Owned by another session and
    may not exist yet; a failure here never fails the create. Returns the
    `{moveu, de, para, motivo}` outcome so the caller can surface a refusal."""
    try:
        from app.modules.pipeline.funil_eventos import mover_por_evento
    except ImportError:
        logger.warning("funil_eventos indisponível: evento %s não emitido", EVENTO_PROPOSTA_CRIADA)
        return {"moveu": False, "de": None, "para": None, "motivo": "funil_indisponivel"}
    try:
        res = mover_por_evento(client, org_id, atendimento_id, EVENTO_PROPOSTA_CRIADA, actor)
    except Exception:  # noqa: BLE001 — the proposta is already saved; report, don't fail
        logger.warning("funil: %s falhou", EVENTO_PROPOSTA_CRIADA, exc_info=True)
        return {"moveu": False, "de": None, "para": None, "motivo": "erro_funil"}
    res = res or {}
    if not res.get("moveu"):
        logger.warning("funil: %s não moveu (%s)", EVENTO_PROPOSTA_CRIADA, res.get("motivo"))
    return res


def criar(client: Any, org_id: UUID, cliente_id: UUID, body: PropostaCreateBody, *, usuario_id: Any) -> dict:
    if body.visita_id is None and not (body.imovel_codigo or "").strip():
        raise ValidationError_(
            "Informe a visita ou o código do imóvel da proposta.", field="visita_id"
        )
    atendimento_id = _atendimento_id(client, org_id, cliente_id)

    visita = None
    codigo = imovel_busca.canonical(body.imovel_codigo) if body.imovel_codigo else None
    if body.visita_id is not None:
        visita = _visita_do_atendimento(client, org_id, atendimento_id, body.visita_id)
        if visita.get("status") != "realizada":
            raise PropostaConflito(
                "visita_nao_realizada",
                "Só é possível criar a proposta de uma visita realizada.",
            )
        codigo_visita = imovel_busca.canonical(str(visita["codigo"]))
        if codigo and codigo != codigo_visita:
            raise ValidationError_(
                "O imóvel informado não é o da visita.", field="imovel_codigo"
            )
        codigo = codigo_visita

    imovel = imovel_busca.enriquecer(client, org_id, [codigo]).get(codigo)
    if not imovel or not imovel.get("registrado"):
        raise NotFoundError("Imóvel", codigo)

    valor = _dec(imovel.get("valor_venda"))
    valor = valor if valor is not None and valor > 0 else None
    imobiliarias = imobiliarias_service.listar_ativas(client, org_id)
    agora = now_iso()
    ator = _ator(usuario_id)
    linha = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "cliente_id": str(cliente_id),
        "visita_id": str(body.visita_id) if body.visita_id else None,
        "imovel_codigo": codigo,
        "status": "rascunho",
        "valor_proposto": str(valor) if valor is not None else None,
        "pct_comissao": _str_num(_pct_comissao_padrao(client, org_id, atendimento_id)),
        "imobiliaria_id": str(imobiliarias[0]["id"]) if len(imobiliarias) == 1 else None,
        "parcelas": [],
        "favorecidos": [],
        "intermediarios": [],
        "termos": {},
        "testemunha_ids": [],
        "created_at": agora,
        "created_por": ator,
    }
    _t(client, TABLE).insert(linha).execute()

    if visita is not None and visita.get("proposta_em") is None:
        _t(client, VISITAS_TABLE).update({"proposta_em": agora, "proposta_por": ator}).eq(
            "org_id", str(org_id)
        ).eq("id", str(visita["id"])).execute()

    funil = _emitir_funil(client, org_id, atendimento_id, usuario_id)
    out = proposta_out(client, org_id, obter_linha(client, org_id, atendimento_id, UUID(linha["id"])))
    # Only on the create response (like roteiro.funil): the caller surfaces a refusal.
    return {**out, "funil": funil}


# ─── patch ──────────────────────────────────────────────────────────────────


def _validar_imobiliaria(client: Any, org_id: UUID, atual: Any, novo: Any) -> None:
    alvo = imobiliarias_service.obter(client, org_id, novo)
    if alvo is None:
        raise NotFoundError("Imobiliária", str(novo))
    if alvo.get("excluida_em") and str(atual or "") != str(novo):
        raise ValidationError_(
            "Esta imobiliária foi removida do cadastro e não pode ser escolhida.",
            field="imobiliaria_id",
        )


def _validar_testemunhas(client: Any, org_id: UUID, ids: list[UUID]) -> list[str]:
    unicos = list(dict.fromkeys(str(i) for i in ids))
    achados = {
        str(r["id"])
        for r in table_reads.in_batched_rows(client, TESTEMUNHAS_REGISTRO, org_id, "id", unicos)
    }
    for i in unicos:
        if i not in achados:
            raise NotFoundError("Testemunha", i)
    return unicos


def atualizar(
    client: Any, org_id: UUID, cliente_id: UUID, proposta_id: UUID,
    body: PropostaPatchBody, *, usuario_id: Any,
) -> dict:
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    atual = obter_linha(client, org_id, atendimento_id, proposta_id)
    if atual["status"] in STATUS_FECHADOS:
        raise _proposta_fechada(atual["status"])

    enviado = body.model_fields_set
    patch: dict[str, Any] = {}
    for campo in ("valor_proposto", "pct_comissao"):
        if campo in enviado:
            patch[campo] = _str_num(getattr(body, campo))
    for campo in ("financiamento", "fgts", "observacoes"):
        if campo in enviado:
            patch[campo] = getattr(body, campo)
    if "validade_ate" in enviado:
        patch["validade_ate"] = body.validade_ate.isoformat() if body.validade_ate else None
    if "imovel_codigo" in enviado:
        if body.imovel_codigo is None:
            raise ValidationError_("O imóvel da proposta é obrigatório.", field="imovel_codigo")
        codigo = imovel_busca.canonical(body.imovel_codigo)
        imovel = imovel_busca.enriquecer(client, org_id, [codigo]).get(codigo)
        if not imovel or not imovel.get("registrado"):
            raise NotFoundError("Imóvel", codigo)
        patch["imovel_codigo"] = codigo
    if "imobiliaria_id" in enviado:
        if body.imobiliaria_id is not None:
            _validar_imobiliaria(client, org_id, atual.get("imobiliaria_id"), body.imobiliaria_id)
        patch["imobiliaria_id"] = str(body.imobiliaria_id) if body.imobiliaria_id else None
    if "testemunha_ids" in enviado:
        patch["testemunha_ids"] = _validar_testemunhas(client, org_id, body.testemunha_ids)
    snapshots = {c: getattr(body, c) for c in SNAPSHOT_MODELS if c in enviado}
    patch.update(validar_snapshots(snapshots, atual))

    patch["updated_at"] = now_iso()
    patch["updated_por"] = _ator(usuario_id)
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq("id", str(proposta_id)).execute()
    return proposta_out(client, org_id, obter_linha(client, org_id, atendimento_id, proposta_id))


# ─── lifecycle ──────────────────────────────────────────────────────────────


def _transicionar(
    client: Any, org_id: UUID, atendimento_id: UUID, proposta_id: UUID, valores: dict
) -> dict:
    _t(client, TABLE).update({**valores, "updated_at": now_iso()}).eq("org_id", str(org_id)).eq(
        "id", str(proposta_id)
    ).execute()
    return proposta_out(client, org_id, obter_linha(client, org_id, atendimento_id, proposta_id))


def enviar(client: Any, org_id: UUID, cliente_id: UUID, proposta_id: UUID, *, usuario_id: Any) -> dict:
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    atual = obter_linha(client, org_id, atendimento_id, proposta_id)
    if atual["status"] in STATUS_FECHADOS:
        raise _proposta_fechada(atual["status"])
    if atual["status"] == "enviada":  # idempotent
        return proposta_out(client, org_id, atual)
    return _transicionar(
        client, org_id, atendimento_id, proposta_id,
        {"status": "enviada", "enviada_em": now_iso(), "updated_por": _ator(usuario_id)},
    )


def recusar(
    client: Any, org_id: UUID, cliente_id: UUID, proposta_id: UUID, motivo: Optional[str],
    *, usuario_id: Any,
) -> dict:
    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise MotivoObrigatorio()
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    atual = obter_linha(client, org_id, atendimento_id, proposta_id)
    if atual["status"] in STATUS_FECHADOS:
        raise _proposta_fechada(atual["status"])
    return _transicionar(
        client, org_id, atendimento_id, proposta_id,
        {
            "status": "recusada", "recusada_em": now_iso(),
            "recusada_por": _ator(usuario_id), "motivo_recusa": motivo_limpo,
            "updated_por": _ator(usuario_id),
        },
    )


def excluir(client: Any, org_id: UUID, cliente_id: UUID, proposta_id: UUID) -> None:
    atendimento_id = _atendimento_id(client, org_id, cliente_id)
    atual = obter_linha(client, org_id, atendimento_id, proposta_id)
    if atual["status"] != "rascunho":
        raise PropostaConflito(
            "proposta_nao_rascunho", "Só um rascunho pode ser excluído."
        )
    _t(client, TABLE).delete().eq("org_id", str(org_id)).eq("id", str(proposta_id)).execute()


def contexto_atendimento(client: Any, org_id: UUID, cliente_id: UUID) -> UUID:
    """For the router's aceite seam: the card's atendimento id."""
    return _atendimento_id(client, org_id, cliente_id)
