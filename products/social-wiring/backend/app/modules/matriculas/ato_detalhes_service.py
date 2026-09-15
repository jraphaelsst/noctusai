"""The typed details of a matrícula's acts (migration 115) — persistence only.

WHAT THE ROWS ARE
-----------------
One `matricula_ato_detalhes` row per R/AV act (the abertura is not an act).
`origem='sugestao'` rows are the seed extractor's reading
(`noctusai_lib.integrations.documents.extrair_detalhes_ato`) of the act's
literal slice; `'confirmado'` rows carry an operator's confirmation. The
extractor NEVER overwrites a row once it exists — a suggestion is minted once
per act, exactly like the acts themselves (`estrutura_service.persistir_atos`).

WHEN THEY ARE WRITTEN
---------------------
- At segmentation: `estrutura_service.persistir_atos` hands the fresh act rows
  to `persistir_sugestoes`.
- On read (the BACKFILL): `detalhes_por_ato` mints the missing suggestions of
  any act that has none — acts segmented before migration 115, or whose
  detail insert failed. Same heal-on-read 109 uses for the acts. Migration
  115 does not backfill in SQL because the extractor is Python, and an
  all-NULL row would claim the extractor found nothing.

🔴 LGPD
-------
Party names and CPFs read out of a matrícula are personal data (KB
PATTERNS/security/lgpd.md §10). A route that returns details WITHOUT also
returning the act text logs `detalhes_view` via `log_leitura_detalhes` —
mirroring 111's `text_view`. Retention follows the `imovel` surface:
`purgar_da_extracao` runs when `estrutura_service.purgar_texto_expirado`
retires the transcription the details were read from.

This module deliberately imports nothing from `estrutura_service` — that
module calls into this one, and the orchestration that needs both lives in
`titulo_service`.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    NATUREZAS_ATO,
    AtoDetalhes,
    extrair_detalhes_ato,
    formatar_cpf_cnpj,
)
from noctusai_lib.integrations.documents.matricula_ato_detalhes import ALTA, NENHUMA
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.imovel_hub import documentos_service as docs_svc
from app.services import table_reads
from app.services.documento_store import log_acesso_extracao, now_iso

logger = logging.getLogger(__name__)

DETALHES_TABLE = "matricula_ato_detalhes"

#: A read of the details alone (migration 115) — see `log_leitura_detalhes`.
ACAO_DETALHES_VIEW = "detalhes_view"

ORIGEM_SUGESTAO = "sugestao"
ORIGEM_CONFIRMADO = "confirmado"

#: What an operator may confirm or edit. Each has a `<campo>_confianca`.
CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "natureza",
    "data_registro",
    "valor",
    "transmitentes",
    "adquirentes",
    "credor",
    "instrumento",
    "atos_referidos",
)

_CAMPOS_INSTRUMENTO_TEXTO = ("tipo", "tabelionato", "livro", "folhas", "cidade")


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def log_leitura_detalhes(
    client: Any, org_id: UUID, extracao_id: Any, usuario_id: Optional[Any]
) -> None:
    """Append a `detalhes_view` row keyed to the extraction the details were
    read from. Written before the caller returns them; a failed write fails
    the request, same contract as `estrutura_service.log_leitura_texto`."""
    log_acesso_extracao(
        client,
        docs_svc.STORE.acessos_table,
        org_id,
        extracao_id,
        usuario_id,
        ACAO_DETALHES_VIEW,
    )


def _linha_vazia(org_id: str, extracao_id: str, ato_id: str) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": org_id,
        "extracao_id": extracao_id,
        "ato_id": ato_id,
        **AtoDetalhes().to_json(),
        "origem": ORIGEM_SUGESTAO,
        "confirmado_por": None,
        "confirmado_em": None,
        "created_at": now_iso(),
    }


def linha_de_detalhes(
    org_id: str, extracao_id: str, ato_row: dict, texto: str
) -> Optional[dict]:
    """The `sugestao` row for one act row, or None for the abertura.

    Reads the act's literal slice and refuses offsets that do not fit the
    text — a clamped slice would silently read a shorter act.
    """
    if ato_row["kind"] == "abertura":
        return None
    inicio, fim = int(ato_row["char_inicio"]), int(ato_row["char_fim"])
    if not (0 <= inicio <= fim <= len(texto)):
        raise ValueError(
            f"ato {ato_row['id']}: offsets [{inicio}:{fim}] fora do texto "
            f"(len={len(texto)}) — atos e texto_extraido divergiram"
        )
    linha = _linha_vazia(org_id, extracao_id, str(ato_row["id"]))
    linha.update(extrair_detalhes_ato(texto[inicio:fim]).to_json())
    return linha


def persistir_sugestoes(
    db: Any, org_id: Any, extracao_id: Any, texto: str, ato_rows: list[dict]
) -> int:
    """Insert one `sugestao` row per R/AV act in `ato_rows`. Returns the count.

    The caller guarantees none of these acts has a row yet (fresh acts at
    segmentation; the missing ones in `detalhes_por_ato`). The UNIQUE
    `(ato_id)` index is the backstop for a concurrent double-heal.
    """
    linhas = [
        linha
        for linha in (
            linha_de_detalhes(str(org_id), str(extracao_id), row, texto) for row in ato_rows
        )
        if linha is not None
    ]
    if linhas:
        _t(db, DETALHES_TABLE).insert(linhas).execute()
    return len(linhas)


def linhas_da_extracao(client: Any, org_id: UUID, extracao_id: Any) -> list[dict]:
    return table_reads.paged_rows(
        client, DETALHES_TABLE, org_id, eq_filters={"extracao_id": str(extracao_id)}
    )


def detalhes_por_ato(
    client: Any, org_id: UUID, extracao: dict, ato_rows: list[dict]
) -> dict[str, dict]:
    """`{ato_id: row}` for the extraction — minting the missing suggestions
    (the backfill; see module docstring). An extraction whose text was purged
    heals nothing: there is no text left to read."""
    existentes = {str(r["ato_id"]): r for r in linhas_da_extracao(client, org_id, extracao["id"])}
    texto = extracao.get("texto_extraido")
    faltando = [
        r for r in ato_rows if r["kind"] != "abertura" and str(r["id"]) not in existentes
    ]
    if faltando and texto:
        escritos = persistir_sugestoes(client, org_id, extracao["id"], texto, faltando)
        logger.info(
            "matricula %s: backfilled %d ato detail suggestions on read",
            extracao["id"],
            escritos,
        )
        existentes = {
            str(r["ato_id"]): r for r in linhas_da_extracao(client, org_id, extracao["id"])
        }
    return existentes


def linha_do_ato(client: Any, org_id: UUID, ato_id: Any) -> Optional[dict]:
    rows = (
        _t(client, DETALHES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("ato_id", str(ato_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _valor_saida(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return str(Decimal(str(valor)).quantize(Decimal("0.01")))


def detalhes_saida(row: Optional[dict], resolved: dict) -> Optional[dict]:
    """The API shape of one row (`valor` as a 2-place decimal string)."""
    if row is None:
        return None
    saida: dict[str, Any] = {"id": row["id"], "ato_id": row["ato_id"]}
    for campo in CAMPOS_EDITAVEIS:
        valor = row.get(campo)
        if campo == "valor":
            valor = _valor_saida(valor)
        elif campo in ("transmitentes", "adquirentes", "atos_referidos"):
            valor = valor or []
        saida[campo] = valor
        saida[f"{campo}_confianca"] = row.get(f"{campo}_confianca") or NENHUMA
    saida.update(
        {
            "origem": row.get("origem") or ORIGEM_SUGESTAO,
            "confirmado_por": table_reads.actor(resolved, row.get("confirmado_por")),
            "confirmado_em": row.get("confirmado_em"),
        }
    )
    return saida


# ─── operator confirmation ────────────────────────────────────────────────


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _parte(parte: dict) -> dict:
    nome = _texto(parte.get("nome"))
    if not nome:
        raise ValidationError_("Toda parte precisa de um nome.", field="nome")
    documento = _texto(parte.get("cpf_cnpj"))
    return {
        "nome": nome,
        "cpf_cnpj": (formatar_cpf_cnpj(documento) or documento) if documento else None,
    }


def _data_iso(valor: Any) -> Optional[str]:
    if isinstance(valor, date):
        return valor.isoformat()
    return _texto(valor)


def _normalizar(campo: str, valor: Any) -> Any:
    if campo == "natureza":
        if valor is not None and valor not in NATUREZAS_ATO:
            raise ValidationError_(f"Natureza desconhecida: {valor}", field="natureza")
        return valor
    if campo == "data_registro":
        return _data_iso(valor)
    if campo == "valor":
        return _valor_saida(valor)
    if campo in ("transmitentes", "adquirentes"):
        return [_parte(p) for p in (valor or [])]
    if campo == "credor":
        return _texto(valor)
    if campo == "instrumento":
        if not valor:
            return None
        instrumento = {k: _texto(valor.get(k)) for k in _CAMPOS_INSTRUMENTO_TEXTO}
        instrumento["data"] = _data_iso(valor.get("data"))
        return instrumento if any(instrumento.values()) else None
    if campo == "atos_referidos":
        return [{"kind": a["kind"], "numero": int(a["numero"])} for a in (valor or [])]
    raise ValueError(f"campo de detalhe desconhecido: {campo}")


def confirmar(
    client: Any,
    org_id: UUID,
    *,
    extracao: dict,
    ato_row: dict,
    existente: Optional[dict],
    valores: dict,
    usuario_id: Optional[Any],
) -> dict:
    """Confirm (and optionally edit) an act's details. Returns the row.

    Only keys present in `valores` are replaced; an empty `valores` confirms
    the suggestion as it stands. The request IS the confirmation: `origem`
    becomes `confirmado` and `confirmado_por/em` are stamped. An edited field's
    confidence becomes `alta` (a human typed it) or `nenhuma` when cleared.
    """
    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )
    if ato_row["kind"] == "abertura":
        raise ValidationError_(
            "A abertura da matrícula não é um ato — não tem detalhes.", field="ato_id"
        )

    agora = now_iso()
    patch: dict[str, Any] = {}
    for campo, valor in valores.items():
        normal = _normalizar(campo, valor)
        patch[campo] = normal
        patch[f"{campo}_confianca"] = ALTA if normal not in (None, [], {}) else NENHUMA
    patch.update(
        {
            "origem": ORIGEM_CONFIRMADO,
            "confirmado_por": str(usuario_id) if usuario_id else None,
            "confirmado_em": agora,
            "updated_at": agora,
        }
    )

    if existente is not None:
        _t(client, DETALHES_TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(existente["id"])
        ).execute()
        return {**existente, **patch}

    texto = extracao.get("texto_extraido")
    base = (
        linha_de_detalhes(str(org_id), str(extracao["id"]), ato_row, texto)
        if texto
        else _linha_vazia(str(org_id), str(extracao["id"]), str(ato_row["id"]))
    )
    linha = {**base, **patch}
    _t(client, DETALHES_TABLE).insert(linha).execute()
    return linha


def purgar_da_extracao(client: Any, org_id: UUID, extracao_id: Any) -> None:
    """Delete every detail row read from `extracao_id` — called when its text
    is purged, so a CPF lifted out of the text cannot outlive it."""
    _t(client, DETALHES_TABLE).delete().eq("org_id", str(org_id)).eq(
        "extracao_id", str(extracao_id)
    ).execute()


__all__ = [
    "ACAO_DETALHES_VIEW",
    "CAMPOS_EDITAVEIS",
    "DETALHES_TABLE",
    "ORIGEM_CONFIRMADO",
    "ORIGEM_SUGESTAO",
    "confirmar",
    "detalhes_por_ato",
    "detalhes_saida",
    "linha_de_detalhes",
    "linha_do_ato",
    "linhas_da_extracao",
    "log_leitura_detalhes",
    "persistir_sugestoes",
    "purgar_da_extracao",
]
