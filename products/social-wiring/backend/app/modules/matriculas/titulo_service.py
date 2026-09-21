"""What the contract asks of a matrícula's acts (migration 115): confirmed act
details, the título aquisitivo phrase, the ônus creditor, and the previous
owners of the last registered sale.

WHERE THE ANSWERS COME FROM
---------------------------
Never from free text and never from a guess — from the TYPED DETAILS of the
acts the operator already chose in 109:

- título phrase    <- `imovel_dados.titulo_aquisitivo_ato_id`'s instrumento,
  rendered by the seed's `frase_titulo_aquisitivo`;
- ônus creditor    <- the `credor` of each act in `imovel_dados.onus_fonte_atos`;
- previous owners  <- the transmitentes of the LAST `compra_e_venda` act of the
  imóvel's título extraction (or its newest concluded extraction).

A suggestion is recomputed on every read and is never stored. What IS stored
is the operator's confirmation (`imovel_dados.titulo_aquisitivo_texto` /
`onus_credor`, migration 115) — the confirmed wording may differ from the
suggestion, and the confirmation is what the contract uses.

🔴 OFFICE RULE — CERTIDÕES OF THE PREVIOUS OWNERS
------------------------------------------------
Required when the last registered compra e venda is LESS than
`ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS` years old (exactly five years is not
"less than five"). When a sale IS found but its registration date is unknown,
`exige_certidoes` is TRUE and `data_desconhecida` says why: an unreadable date
must lead to asking for the certidões, never to silently waiving them.

🔴 LGPD: every route here that returns details without the act text logs
`detalhes_view` (`ato_detalhes_service.log_leitura_detalhes`) before answering.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import Instrumento, frase_titulo_aquisitivo
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads
from app.services.documento_store import now_iso, today

ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS = 5

NATUREZA_COMPRA_E_VENDA = "compra_e_venda"

#: Why a GET has no suggestion — a machine-readable reason for the FE.
MOTIVO_SEM_TITULO = "sem_titulo_confirmado"
MOTIVO_SEM_ONUS = "sem_onus_confirmado"
MOTIVO_SEM_DETALHES = "sem_detalhes"
MOTIVO_SEM_INSTRUMENTO = "sem_instrumento"
MOTIVO_SEM_CREDOR = "sem_credor"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _codigo(codigo: str) -> str:
    canonico = (codigo or "").strip().upper()
    if not canonico:
        raise ValidationError_("O código do imóvel é obrigatório.", field="codigo")
    return canonico


def _ato_ref(ato: dict) -> Optional[str]:
    if ato.get("numero") is None:
        return None
    return f"{ato['kind']}-{ato['numero']}"


def _atos_e_detalhes(
    client: Any, org_id: UUID, extracao: dict
) -> tuple[dict[str, dict], dict[str, dict]]:
    atos = estrutura_svc.atos_da_extracao(client, org_id, extracao)
    return (
        {str(r["id"]): r for r in atos},
        detalhes_svc.detalhes_por_ato(client, org_id, extracao, atos),
    )


def _confirmacao(linha: dict, coluna: str, chave: str) -> Optional[dict]:
    valor = linha.get(coluna)
    if valor is None:
        return None
    resolved = table_reads.resolve_actors({linha.get(f"{coluna}_confirmado_por")} - {None})
    return {
        chave: valor,
        "confirmado_por": table_reads.actor(resolved, linha.get(f"{coluna}_confirmado_por")),
        "confirmado_em": linha.get(f"{coluna}_confirmado_em"),
    }


def _patch_confirmacao(coluna: str, valor: Optional[str], usuario_id: Optional[Any]) -> dict:
    texto = (valor or "").strip() or None
    return {
        coluna: texto,
        f"{coluna}_confirmado_por": str(usuario_id) if texto and usuario_id else None,
        f"{coluna}_confirmado_em": now_iso() if texto else None,
    }


# ─── act details ──────────────────────────────────────────────────────────


def confirmar_detalhes_ato(
    client: Any,
    org_id: UUID,
    ato_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[Any],
) -> dict:
    """`PUT /atos/{ato_id}/detalhes` — confirm/edit one act's details."""
    rows = (
        _t(client, estrutura_svc.ATOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(ato_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(estrutura_svc.ATOS_TABLE, str(ato_id))
    ato = rows[0]
    extracao = estrutura_svc.exigir_extracao(client, org_id, ato["extracao_id"])
    linha = detalhes_svc.confirmar(
        client,
        org_id,
        extracao=extracao,
        ato_row=ato,
        existente=detalhes_svc.linha_do_ato(client, org_id, ato["id"]),
        valores=valores,
        usuario_id=usuario_id,
    )
    detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
    resolved = table_reads.resolve_actors({linha.get("confirmado_por")} - {None})
    return {
        "ato_id": str(ato["id"]),
        "extracao_id": str(extracao["id"]),
        "kind": ato["kind"],
        "numero": ato.get("numero"),
        "ato_ref": _ato_ref(ato),
        "detalhes": detalhes_svc.detalhes_saida(linha, resolved),
    }


# ─── título aquisitivo phrase ─────────────────────────────────────────────


def obter_titulo(
    client: Any, org_id: UUID, codigo: str, *, usuario_id: Optional[Any] = None
) -> dict:
    """The suggested título phrase (from the confirmed título act) + the
    operator's confirmed wording."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = dados_service.linha(client, org_id, codigo) or {}

    ato_saida: Optional[dict] = None
    sugestao: Optional[str] = None
    motivo: Optional[str] = None
    ato_id = linha.get("titulo_aquisitivo_ato_id")
    if not ato_id:
        motivo = MOTIVO_SEM_TITULO
    else:
        extracao = estrutura_svc.exigir_extracao(
            client, org_id, linha["titulo_aquisitivo_extracao_id"]
        )
        por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
        ato = por_id.get(str(ato_id))
        if ato is None:
            # 109's RESTRICT FK makes this unreachable in the database.
            raise ValueError(
                f"imóvel {codigo}: título aponta para o ato {ato_id}, ausente da "
                f"extração {extracao['id']}"
            )
        det = detalhes.get(str(ato_id))
        ato_saida = {
            "extracao_id": str(extracao["id"]),
            "ato_id": str(ato["id"]),
            "kind": ato["kind"],
            "numero": ato.get("numero"),
            "ato_ref": _ato_ref(ato),
            "detalhes_origem": det.get("origem") if det else None,
        }
        if det is None:
            motivo = MOTIVO_SEM_DETALHES
        else:
            detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
            sugestao = frase_titulo_aquisitivo(
                Instrumento.from_json(det.get("instrumento")),
                kind=ato["kind"],
                numero=int(ato["numero"]),
            )
            if sugestao is None:
                motivo = MOTIVO_SEM_INSTRUMENTO

    return {
        "codigo": codigo,
        "ato": ato_saida,
        "sugestao": sugestao,
        "motivo_sem_sugestao": motivo,
        "confirmado": _confirmacao(linha, "titulo_aquisitivo_texto", "texto"),
    }


def confirmar_titulo(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    texto: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    dados_service.gravar_texto_contrato(
        client, org_id, codigo, _patch_confirmacao("titulo_aquisitivo_texto", texto, usuario_id)
    )
    return obter_titulo(client, org_id, codigo, usuario_id=usuario_id)


# ─── endereço do registro (migration 139) ─────────────────────────────────


def obter_endereco_registro(client: Any, org_id: UUID, codigo: str) -> dict:
    """The operator's confirmed short address ("situado à ...") — NEVER a
    recomputed suggestion (see `imovel_dados.endereco_registro_texto`'s
    column comment): a wrong split of free legal prose into a compact
    address is exactly the guess this feature must not make.

    🔴 Does NOT reuse `_confirmacao`/`_patch_confirmacao`: those assume the
    confirmation columns are `{coluna}_confirmado_por/em` — true for
    `titulo_aquisitivo_texto`/`onus_credor`, but migration 139 named this
    pair `endereco_registro_confirmado_por/em`, dropping the `_texto`
    infix. Reusing the generic helper here reached for a column
    (`endereco_registro_texto_confirmado_por`) that does not exist —
    `dados_service.gravar_texto_contrato`'s own refusal-by-name caught it.
    """
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = dados_service.linha(client, org_id, codigo) or {}
    valor = linha.get("endereco_registro_texto")
    confirmado = None
    if valor is not None:
        resolved = table_reads.resolve_actors(
            {linha.get("endereco_registro_confirmado_por")} - {None}
        )
        confirmado = {
            "texto": valor,
            "confirmado_por": table_reads.actor(
                resolved, linha.get("endereco_registro_confirmado_por")
            ),
            "confirmado_em": linha.get("endereco_registro_confirmado_em"),
        }
    return {"codigo": codigo, "confirmado": confirmado}


def confirmar_endereco_registro(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    texto: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    valor = (texto or "").strip() or None
    patch = {
        "endereco_registro_texto": valor,
        "endereco_registro_confirmado_por": str(usuario_id) if valor and usuario_id else None,
        "endereco_registro_confirmado_em": now_iso() if valor else None,
    }
    dados_service.gravar_texto_contrato(client, org_id, codigo, patch)
    return obter_endereco_registro(client, org_id, codigo)


# ─── ônus creditor ────────────────────────────────────────────────────────


def obter_onus_credor(
    client: Any, org_id: UUID, codigo: str, *, usuario_id: Optional[Any] = None
) -> dict:
    """The creditor(s) read from the confirmed ônus acts + the confirmation."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = dados_service.linha(client, org_id, codigo) or {}

    atos_saida: list[dict] = []
    credores: list[str] = []
    motivo: Optional[str] = None
    extracao_id = linha.get("onus_fonte_extracao_id")
    fonte = linha.get("onus_fonte_atos") or []
    if not extracao_id or not fonte:
        motivo = MOTIVO_SEM_ONUS
    else:
        extracao = estrutura_svc.exigir_extracao(client, org_id, extracao_id)
        por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
        leu = False
        for ref in fonte:
            ato = por_id.get(str(ref["ato_id"]))
            if ato is None:
                raise ValueError(
                    f"imóvel {codigo}: ônus aponta para o ato {ref['ato_id']}, ausente "
                    f"da extração {extracao['id']}"
                )
            det = detalhes.get(str(ato["id"]))
            leu = leu or det is not None
            credor = det.get("credor") if det else None
            atos_saida.append(
                {
                    "ato_id": str(ato["id"]),
                    "kind": ato["kind"],
                    "numero": ato.get("numero"),
                    "ato_ref": _ato_ref(ato),
                    "natureza": det.get("natureza") if det else None,
                    "credor": credor,
                    "credor_confianca": (det.get("credor_confianca") if det else None)
                    or "nenhuma",
                    "detalhes_origem": det.get("origem") if det else None,
                }
            )
            if credor and credor not in credores:
                credores.append(credor)
        if leu:
            detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
        if not credores:
            motivo = MOTIVO_SEM_CREDOR

    return {
        "codigo": codigo,
        "extracao_id": extracao_id,
        "atos": atos_saida,
        "sugestao": "; ".join(credores) or None,
        "motivo_sem_sugestao": motivo,
        "confirmado": _confirmacao(linha, "onus_credor", "credor"),
    }


def confirmar_onus_credor(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    credor: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    dados_service.gravar_texto_contrato(
        client, org_id, codigo, _patch_confirmacao("onus_credor", credor, usuario_id)
    )
    return obter_onus_credor(client, org_id, codigo, usuario_id=usuario_id)


# ─── previous owners ──────────────────────────────────────────────────────


def _anos_antes(dia: date, anos: int) -> date:
    try:
        return dia.replace(year=dia.year - anos)
    except ValueError:  # 29 Feb -> 28 Feb
        return dia.replace(year=dia.year - anos, day=28)


def _extracao_do_imovel(
    client: Any, org_id: UUID, codigo: str, linha: dict
) -> Optional[dict]:
    """The título's own extraction when one is confirmed; otherwise the
    imóvel's newest concluded transcription."""
    if linha.get("titulo_aquisitivo_extracao_id"):
        return estrutura_svc.exigir_extracao(
            client, org_id, linha["titulo_aquisitivo_extracao_id"]
        )
    rows = (
        _t(client, estrutura_svc.EXTRACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("status", estrutura_svc.STATUS_CONCLUIDA)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def antigos_proprietarios(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    usuario_id: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> dict:
    """Who sold the imóvel in its last registered compra e venda, when, and
    whether the office rule requires their certidões."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = dados_service.linha(client, org_id, codigo) or {}
    hoje = hoje or today()

    extracao = _extracao_do_imovel(client, org_id, codigo, linha)
    saida: dict[str, Any] = {
        "codigo": codigo,
        "extracao_id": str(extracao["id"]) if extracao else None,
        "ultima_transferencia": None,
        "transmitentes": [],
        "exige_certidoes": False,
        "data_desconhecida": False,
    }
    if extracao is None or extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA:
        return saida

    por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
    vendas = [
        por_id[ato_id]
        for ato_id, det in detalhes.items()
        if det.get("natureza") == NATUREZA_COMPRA_E_VENDA and ato_id in por_id
    ]
    if not vendas:
        return saida

    ultima = max(vendas, key=lambda r: r["ordem"])
    det = detalhes[str(ultima["id"])]
    detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)

    bruto = det.get("data_registro")
    data_registro = date.fromisoformat(str(bruto)[:10]) if bruto else None
    limite = _anos_antes(hoje, ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS)
    saida.update(
        {
            "ultima_transferencia": {
                "ato_id": str(ultima["id"]),
                "ato_ref": _ato_ref(ultima),
                "data_registro": data_registro.isoformat() if data_registro else None,
                "detalhes_origem": det.get("origem"),
            },
            "transmitentes": [
                {"nome": p.get("nome"), "cpf_cnpj": p.get("cpf_cnpj")}
                for p in det.get("transmitentes") or []
            ],
            "exige_certidoes": data_registro is None or data_registro > limite,
            "data_desconhecida": data_registro is None,
        }
    )
    return saida


__all__ = [
    "ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS",
    "antigos_proprietarios",
    "confirmar_detalhes_ato",
    "confirmar_onus_credor",
    "confirmar_titulo",
    "obter_onus_credor",
    "obter_titulo",
]
