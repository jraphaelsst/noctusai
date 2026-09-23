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
- previous owners  <- the transmitentes of the CONFIRMED título aquisitivo
  act, when its nature is one that transfers ownership for consideration
  (`NATUREZAS_ULTIMA_TRANSFERENCIA`); otherwise the LAST such act anywhere in
  the imóvel's título extraction (or its newest concluded extraction), by
  `ordem`. [migration 152] When neither exists, an operator's manual
  override (a typed date, or an explicit "não consta transferência
  registrada" statement) answers it instead.

🔴 UPDATED FOR MIGRATION 154's D1 WRITE POLICY (2026-09-23, migration 166).
`obter_titulo`/`obter_onus_credor` below still recompute a live SUGGESTION on
every read (`sugestao`, from the acts) and never store it directly — but
`imovel_dados.titulo_aquisitivo_texto` / `onus_credor` are no longer
confirmed-only, as 115 originally shipped them. Two paths write the stored
value now, exactly like every other contract-feeding `imovel_dados` field:
`preenchimento_service.preencher_sincrono` (154) machine-fills it from the
confirmed título act's instrumento — MACHINE-PENDING (`_origem` set,
`_confirmado_em` NULL, D2) until a human validates it — and
`confirmar_titulo`/`confirmar_onus_credor` below is the human's own edit,
always stamped `origem='manual'` + the confirmation together
(`_patch_confirmacao`). `imovel_dados_titulo_aquisitivo_texto_pareado` /
`imovel_dados_onus_credor_pareado` (migration 166, replacing 115's
confirmed-only CHECKs) enforce that the value and `_origem` always travel
together and a confirmation timestamp never appears without a value — NOT
that the value is always confirmed. The CONTRACT still only accepts the
CONFIRMED wording (`contrato_gerador.validacao_extracao`'s
`CAMPOS_IMOVEL` — a machine-pending phrase alone does not satisfy the
readiness gate), so "the confirmation is what the contract uses" remains
true; what changed is that a stored, unconfirmed suggestion is now a
legal, expected intermediate state instead of a database contradiction.

🔴 OFFICE RULE — CERTIDÕES OF THE PREVIOUS OWNERS
------------------------------------------------
Required when the last registered TRANSFER OF OWNERSHIP is LESS than
`ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS` years old (exactly five years is not
"less than five"). When a transfer IS found but its registration date is
unknown, `exige_certidoes` is TRUE and `data_desconhecida` says why: an
unreadable date must lead to asking for the certidões, never to silently
waiving them.

[Owner directive, 2026-09-22] "The last registered compra e venda" was too
narrow: a matrícula whose last transfer is a PERMUTA (or a dação em
pagamento / arrematação) could never satisfy this. `NATUREZAS_ULTIMA_
TRANSFERENCIA` widens it to every nature that moves ownership for
consideration — still NOT the seed's full `NATUREZAS_TRANSFERENCIA` (which
also counts `doacao`/`partilha`): re-classifying an act as `doacao` is how
an operator tells this feature "this did not transfer for consideration, do
not treat it as the sale" (`test_the_confirmed_nature_decides_what_a_sale_
is`), so a donation or an inheritance partition must not silently
substitute for it either.

🔴 LGPD: every route here that returns details without the act text logs
`detalhes_view` (`ato_detalhes_service.log_leitura_detalhes`) before answering.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import (
    Instrumento,
    NATUREZAS_TRANSFERENCIA,
    frase_titulo_aquisitivo,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads
from app.services.documento_store import now_iso, today

ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS = 5

NATUREZA_COMPRA_E_VENDA = "compra_e_venda"

#: [Q9] Natures that count as "the imóvel changed hands" for the previous-
#: owner certidões rule — a SUBSET of the seed's broader
#: `NATUREZAS_TRANSFERENCIA` (which also includes `doacao`/`partilha`; see
#: this module's docstring for why those two stay excluded here). Migration
#: 152's manual-override `natureza` select offers exactly these 4.
NATUREZAS_ULTIMA_TRANSFERENCIA: frozenset[str] = NATUREZAS_TRANSFERENCIA & {
    NATUREZA_COMPRA_E_VENDA,
    "permuta",
    "dacao",
    "arrematacao",
}

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
        # Migration 154 — `matricula` when the value was machine-filled from
        # the acts and not yet confirmed (the D2 gate lists it as pending).
        "origem": linha.get(f"{coluna}_origem"),
    }


def _patch_confirmacao(coluna: str, valor: Optional[str], usuario_id: Optional[Any]) -> dict:
    """An operator's PUT: the value, `manual` provenance (migration 154 — so a
    later extraction reading a different phrase opens a conflict instead of
    overwriting), and the confirmation. Clearing clears all of it."""
    texto = (valor or "").strip() or None
    return {
        coluna: texto,
        f"{coluna}_origem": "manual" if texto else None,
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


def _manual_ultima_transferencia(linha: dict) -> Optional[dict]:
    """The RAW manual-override state (migration 152) — always returned so the
    property page can show/edit it regardless of whether a derivation below
    is currently the effective source. `None` means no override was ever
    confirmed."""
    confirmado_em = linha.get("ultima_transferencia_manual_confirmado_em")
    if confirmado_em is None:
        return None
    resolved = table_reads.resolve_actors(
        {linha.get("ultima_transferencia_manual_confirmado_por")} - {None}
    )
    bruto = linha.get("ultima_transferencia_manual_data")
    return {
        "data_registro": str(bruto)[:10] if bruto else None,
        "natureza": linha.get("ultima_transferencia_manual_natureza"),
        "sem_registro": bool(linha.get("ultima_transferencia_manual_sem_registro")),
        "confirmado_por": table_reads.actor(
            resolved, linha.get("ultima_transferencia_manual_confirmado_por")
        ),
        "confirmado_em": confirmado_em,
    }


def antigos_proprietarios(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    usuario_id: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> dict:
    """Who sold the imóvel in its last registered transfer of ownership,
    when, and whether the office rule requires their certidões.

    Priority for `ultima_transferencia` [migration 152]:
    1. The CONFIRMED título aquisitivo act, when its `natureza` is one of
       `NATUREZAS_ULTIMA_TRANSFERENCIA` — an operator already verified this
       act IS how the current owner acquired, so it is trusted over a blind
       re-scan (fixes the permuta dead end: a confirmed título act whose
       nature is `permuta` was invisible to the old compra-e-venda-only
       search).
    2. Otherwise, the LATEST such act anywhere in the extraction (by
       `ordem`) — the original heuristic, now recognising every nature in
       `NATUREZAS_ULTIMA_TRANSFERENCIA` instead of `compra_e_venda` alone.
    3. Otherwise, the operator's manual override: a typed date, or an
       explicit "não consta transferência registrada" statement that
       resolves `exige_certidoes` to `False` instead of leaving it unknown.
    `manual` in the response always reports the raw override state, even
    when a derivation above wins — the property page shows/edits it either
    way.
    """
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
        "sem_registro": False,
        "origem": None,
        "manual": _manual_ultima_transferencia(linha),
    }

    ato: Optional[dict] = None
    det: Optional[dict] = None
    origem_derivacao: Optional[str] = None

    if extracao is not None and extracao.get("status") == estrutura_svc.STATUS_CONCLUIDA:
        por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)

        ato_id_titulo = linha.get("titulo_aquisitivo_ato_id")
        det_titulo = detalhes.get(str(ato_id_titulo)) if ato_id_titulo else None
        if (
            ato_id_titulo
            and str(ato_id_titulo) in por_id
            and det_titulo is not None
            and det_titulo.get("natureza") in NATUREZAS_ULTIMA_TRANSFERENCIA
        ):
            ato, det, origem_derivacao = (
                por_id[str(ato_id_titulo)],
                det_titulo,
                "titulo_confirmado",
            )
        else:
            transferencias = [
                por_id[ato_id]
                for ato_id, d in detalhes.items()
                if d.get("natureza") in NATUREZAS_ULTIMA_TRANSFERENCIA and ato_id in por_id
            ]
            if transferencias:
                ato = max(transferencias, key=lambda r: r["ordem"])
                det = detalhes[str(ato["id"])]
                origem_derivacao = "extracao"

    if ato is not None and det is not None:
        detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
        bruto = det.get("data_registro")
        data_registro = date.fromisoformat(str(bruto)[:10]) if bruto else None
        limite = _anos_antes(hoje, ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS)
        saida.update(
            {
                "ultima_transferencia": {
                    "ato_id": str(ato["id"]),
                    "ato_ref": _ato_ref(ato),
                    "natureza": det.get("natureza"),
                    "data_registro": data_registro.isoformat() if data_registro else None,
                    "detalhes_origem": det.get("origem"),
                },
                "transmitentes": [
                    {"nome": p.get("nome"), "cpf_cnpj": p.get("cpf_cnpj")}
                    for p in det.get("transmitentes") or []
                ],
                "exige_certidoes": data_registro is None or data_registro > limite,
                "data_desconhecida": data_registro is None,
                "origem": origem_derivacao,
            }
        )
        return saida

    manual = saida["manual"]
    if manual and manual.get("sem_registro"):
        saida["sem_registro"] = True
        saida["origem"] = "manual"
        return saida
    if manual and manual.get("data_registro"):
        data_registro = date.fromisoformat(manual["data_registro"])
        limite = _anos_antes(hoje, ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS)
        saida.update(
            {
                "ultima_transferencia": {
                    "ato_id": None,
                    "ato_ref": None,
                    "natureza": manual.get("natureza"),
                    "data_registro": manual["data_registro"],
                    "detalhes_origem": "manual",
                },
                "exige_certidoes": data_registro > limite,
                "data_desconhecida": False,
                "origem": "manual",
            }
        )
    return saida


def confirmar_ultima_transferencia_manual(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    data: Optional[date],
    natureza: Optional[str],
    sem_registro: bool,
    usuario_id: Optional[Any],
) -> dict:
    """`PUT /imoveis/{codigo}/ultima-transferencia` [migration 152] — the
    manual fallback for [Q9]'s previous-owner rule, always available on the
    property page next to "Antigos proprietários": a typed date (+ optional
    nature), or an explicit "não consta transferência registrada" statement
    — which the gate must treat as an ANSWER (`exige_antigo_proprietario`
    resolves to `False`), never as still-unknown. `data=None, natureza=None,
    sem_registro=False` clears the override.
    """
    codigo = _codigo(codigo)
    if data is not None and sem_registro:
        raise ValidationError_(
            "Informe uma data OU marque que não consta transferência registrada — não os dois.",
            field="sem_registro",
        )
    if natureza is not None and data is None:
        raise ValidationError_(
            "A natureza da transferência exige uma data de registro.", field="natureza"
        )
    if natureza is not None and natureza not in NATUREZAS_ULTIMA_TRANSFERENCIA:
        raise ValidationError_(
            f"Natureza inválida para a última transferência: {natureza}", field="natureza"
        )

    limpar = data is None and not sem_registro
    patch = {
        "ultima_transferencia_manual_data": data,
        "ultima_transferencia_manual_natureza": natureza if data is not None else None,
        "ultima_transferencia_manual_sem_registro": bool(sem_registro),
        "ultima_transferencia_manual_confirmado_por": (
            None if limpar else (str(usuario_id) if usuario_id else None)
        ),
        "ultima_transferencia_manual_confirmado_em": None if limpar else now_iso(),
    }
    dados_service.gravar_ultima_transferencia_manual(client, org_id, codigo, patch)
    return antigos_proprietarios(client, org_id, codigo, usuario_id=usuario_id)


__all__ = [
    "ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS",
    "NATUREZAS_ULTIMA_TRANSFERENCIA",
    "antigos_proprietarios",
    "confirmar_detalhes_ato",
    "confirmar_onus_credor",
    "confirmar_titulo",
    "confirmar_ultima_transferencia_manual",
    "obter_onus_credor",
    "obter_titulo",
]
