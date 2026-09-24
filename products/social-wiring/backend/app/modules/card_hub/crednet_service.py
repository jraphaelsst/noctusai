"""Serasa Crednet — one upload, four writes (P0c contract §C4).

`identidade_extracao_service.extrair_identidade` routes `tipo_documento ==
'serasa_crednet'` here (step 3 of the contract's §C), right after the blob
read and access log it already did — this module never re-fetches either.

`aplicar_leitura`, in order:

    (a) record the reading on the DOCUMENT — `extracao_status/_fonte`,
        `extracao_nome/_cpf/_data_nascimento/_nome_mae` (+confiança/rótulo),
        and the full reading (`extracao_crednet`) — before touching the
        cliente at all;
    (b) D1: `identidade_extracao_service.aplicar_campos_ao_cliente` with a
        FOUR-field `CAMPOS_CREDNET` (nome_oficial, cpf, data_nascimento,
        nome_mae) — the same field-level policy every other identity
        extraction gets: empty → fill machine-pending, set → disagree →
        conflict, never a silent overwrite;
    (c) per participação with a VALID CNPJ, upsert `empresas` by
        `(org_id, cnpj)` — insert-only `razao_social`/group provenance, NEVER
        `situação` (contract §H4 — only a Cartão CNPJ is trusted for that)
        and NEVER `uf` (owner decision, 2026-09-24: Crednet's "Participação
        Societária UF" column is not even the EMPRESA's own registered UF —
        `empresas` models no address/UF at all). Then upsert the
        participação, fill-empty. An invalid-CNPJ participação is never
        linked — it rides in `extracao_crednet.participacoes_rejeitadas`
        instead, so nothing is silently dropped;
    (d) `certidoes.service.registrar_serasa_de_crednet` — the SAME stored
        PDF also fills the cliente's certidão 9 (Serasa) resultado, deferred
        when no matching consulta exists yet (§C5/§E7).

🔴 `leitura` IS `noctusai_lib.integrations.documents.serasa_crednet.
CrednetFields` — a SIBLING worktree/branch's deliverable (S1) at the time
this module was written, per the P0c contract's own collision notes. This
module is written against §B's names/signatures but never imports that
module at module scope — the extractor itself is injected (`extractor:
CrednetExtractor`, DI, `KB § PATTERNS/backend/di-test-seam.md`), so a test
overrides it with a Fake/Scripted double, never a monkeypatch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.services import _now, _t

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"
EMPRESAS_TABLE = "empresas"
PARTICIPACOES_TABLE = "cliente_empresa_participacoes"

#: The four `CampoExtraido`s a Crednet reading may write onto `clientes`
#: (contract §C4b) — three of `identidade_extracao_service.CAMPOS`' own
#: entries, reused verbatim (same D1 policy, same provenance columns) plus
#: the Crednet-only `nome_mae` (`CAMPO_POR_CHAVE`, not `CAMPOS` itself —
#: see that constant's own docstring for why).
CAMPOS_CREDNET: tuple = tuple(
    identidade_svc.CAMPO_POR_CHAVE[chave]
    for chave in ("nome_oficial", "cpf", "data_nascimento", "nome_mae")
)


def _confianca_de(fields: Any, chave: str) -> str:
    valor = (fields.confiancas or {}).get(chave)
    return getattr(valor, "value", valor) or "nenhuma"


def _rotulo_de(fields: Any, chave: str) -> Optional[str]:
    return (fields.rotulos or {}).get(chave)


def _lidos(fields: Any) -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """`CAMPOS_CREDNET`'s `item_key -> (valor, confianca, rotulo,
    pode_persistir)` — the same shape `identidade_extracao_service.
    _valores_lidos` builds for an identity document, built here from
    `CrednetFields` instead.

    `cpf` is gated on `cpf_valido`: a failed check digit is recorded on the
    document (step a already wrote `extracao_cpf`) but never offered to
    `aplicar_campos_ao_cliente` — the seed extractor's own contract is
    "never corrected", not "never trusted downstream", so this module is
    the one that declines to apply it, the same way `empresas` upsert below
    declines an invalid `cnpj_valido`.
    """
    nome_ok = bool(fields.nome)
    cpf_ok = bool(fields.cpf) and bool(fields.cpf_valido)
    nascimento_ok = fields.data_nascimento is not None
    mae_ok = bool(fields.nome_mae)
    return {
        "nome_oficial": (fields.nome, _confianca_de(fields, "nome_oficial"), _rotulo_de(fields, "nome_oficial"), nome_ok),
        "cpf": (fields.cpf, _confianca_de(fields, "cpf"), _rotulo_de(fields, "cpf"), cpf_ok),
        "data_nascimento": (
            fields.data_nascimento.isoformat() if fields.data_nascimento else None,
            _confianca_de(fields, "data_nascimento"),
            _rotulo_de(fields, "data_nascimento"),
            nascimento_ok,
        ),
        "nome_mae": (fields.nome_mae, _confianca_de(fields, "nome_mae"), _rotulo_de(fields, "nome_mae"), mae_ok),
    }


def _ocorrencia_dict(oc: Any) -> dict:
    return {
        "constam": oc.constam,
        "quantidade": oc.quantidade,
        "valor": float(oc.valor) if oc.valor is not None else None,
        "ultimo_registro": oc.ultimo_registro.isoformat() if oc.ultimo_registro else None,
    }


def _participacao_dict(p: Any) -> dict:
    return {
        "razao_social": p.razao_social,
        "cnpj": p.cnpj,
        "cnpj_valido": p.cnpj_valido,
        "participacao_pct": float(p.participacao_pct) if p.participacao_pct is not None else None,
        "uf": p.uf,
        "situacao_texto": p.situacao_texto,
        "situacao_em": p.situacao_em.isoformat() if p.situacao_em else None,
        "desde": p.desde,
        "confianca": getattr(p.confianca, "value", p.confianca),
    }


def _serializar_crednet(fields: Any) -> dict:
    """The whole reading, JSON-safe — `cliente_documentos.extracao_crednet`
    (contract §A.8, mirroring `extracao_conjuges`). `ocorrencias_constam` is
    stored PRE-COMPUTED (not re-derivable from the nested ocorrências alone
    without the seed's own method) — `certidoes.service.
    aplicar_crednet_pendente` reads exactly this key back.
    """
    return {
        "protocolo": fields.protocolo,
        "cpf": fields.cpf,
        "cpf_valido": fields.cpf_valido,
        "consulta_em": fields.consulta_em.isoformat() if fields.consulta_em else None,
        "nome": fields.nome,
        "nome_mae": fields.nome_mae,
        "data_nascimento": fields.data_nascimento.isoformat() if fields.data_nascimento else None,
        "cpf_situacao": fields.cpf_situacao,
        "cpf_situacao_em": fields.cpf_situacao_em.isoformat() if fields.cpf_situacao_em else None,
        "ocorrencias_constam": fields.ocorrencias_constam(),
        "pendencias_internas": _ocorrencia_dict(fields.pendencias_internas),
        "pendencias_financeiras": _ocorrencia_dict(fields.pendencias_financeiras),
        "protesto_estadual": _ocorrencia_dict(fields.protesto_estadual),
        "cheques_sem_fundo": _ocorrencia_dict(fields.cheques_sem_fundo),
        "participacoes": [_participacao_dict(p) for p in fields.participacoes],
        "aviso": fields.aviso,
        "source": getattr(fields.source, "value", fields.source),
    }


def _marcar(client: Any, documento_id: UUID, **campos: Any) -> None:
    _t(client, DOCUMENTOS_TABLE).update(campos).eq("id", str(documento_id)).execute()


def _upsert_empresa(client: Any, org_id: UUID, participacao: Any) -> dict:
    """Upsert by `(org_id, cnpj)` — insert-only `razao_social`/group
    provenance, NEVER `situação` (contract §H4: the Crednet closing date is
    known-wrong on case 883; only a Cartão CNPJ earns that field). An
    EXISTING empresa is returned untouched here — always, no field-level
    exception (`empresas` models no `uf`/address at all).

    🔴 P1/883 live bug (2026-09-24): `dados_documento_id` STAYS `None` here
    — this function takes no `documento_id` on purpose (it used to, and
    wrote it here; that was the bug). `empresas.dados_documento_id`'s FK
    targets `empresa_documentos` (a Cartão CNPJ upload) — writing the
    caller's `documento_id` (a `cliente_documentos` row, the Crednet PDF)
    into it 500s on insert (`23503`, the FK has no such row to point at).
    Per contract §C4(c) a Crednet-created empresa gets
    `dados_origem='serasa_crednet'` and `dados_documento_id=NULL`; the
    Crednet provenance lives on `cliente_empresa_participacoes.
    fonte_documento_id` (set by `_upsert_participacao` below), never here.
    `dados_service.criar` (`empresas/dados_service.py`) is the ONLY writer
    allowed to set `dados_documento_id`, and only when
    `fonte_tabela='empresa_documentos'` — see that module's own D1 policy.
    """
    cnpj_norm = normalize_cnpj(participacao.cnpj)
    existentes = (
        _t(client, EMPRESAS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cnpj", cnpj_norm)
        .limit(1)
        .execute()
    ).data or []
    if existentes:
        return existentes[0]
    now = _now()
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "cnpj": cnpj_norm,
        "razao_social": participacao.razao_social,
        "dados_origem": "serasa_crednet",
        "dados_documento_id": None,
        "dados_em": now,
        "dados_confirmado_por": None,
        "dados_confirmado_em": None,
        "created_at": now,
    }
    _t(client, EMPRESAS_TABLE).insert(row).execute()
    return row


def _upsert_participacao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    empresa_id: str,
    participacao: Any,
    documento_id: UUID,
) -> dict:
    """Upsert by `(cliente_id, empresa_id)`, fill-empty on `participacao_pct`
    / `desde` — a later Crednet re-read never overwrites a value a human
    (or an earlier read) already set. No `uf` column (owner decision,
    2026-09-24) — the raw value still rides inside `_participacao_dict`'s
    JSON, on `cliente_documentos.extracao_crednet`."""
    existentes = (
        _t(client, PARTICIPACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("empresa_id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    pct = float(participacao.participacao_pct) if participacao.participacao_pct is not None else None
    if not existentes:
        row = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "empresa_id": str(empresa_id),
            "participacao_pct": pct,
            "desde": participacao.desde,
            "fonte_documento_id": str(documento_id),
            "origem": "serasa_crednet",
            "confirmado_por": None,
            "confirmado_em": None,
            "created_at": _now(),
        }
        _t(client, PARTICIPACOES_TABLE).insert(row).execute()
        return row
    existente = existentes[0]
    patch: dict[str, Any] = {}
    if existente.get("participacao_pct") is None and pct is not None:
        patch["participacao_pct"] = pct
    if not existente.get("desde") and participacao.desde:
        patch["desde"] = participacao.desde
    if patch:
        _t(client, PARTICIPACOES_TABLE).update(patch).eq("id", existente["id"]).execute()
    return {**existente, **patch}


async def aplicar_leitura(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    doc: dict,
    blob_data: bytes,
    *,
    extractor: Any,
    notification_service: Optional[Any] = None,
) -> dict:
    """The whole §C4 sequence. `doc` is the already-fetched `cliente_
    documentos` row, `blob_data` the already-fetched bytes — `identidade_
    extracao_service.extrair_identidade` does both before branching here, so
    this module never re-reads storage. Never raises — every failure path
    ends in a recorded `extracao_status`, matching `extrair_identidade`'s
    own contract (this document is read by the same detached background
    task / sweep recovery).

    🔴 P1/883 live bug (2026-09-24): `extracao_status` used to land `ok`/
    `sem_dados` in step (a), BEFORE (b)/(c)/(d) ran — so a crash inside any
    of them (a real one: `_upsert_empresa` writing a FK-violating
    `dados_documento_id`, §6 of this same pass) propagated out of a
    BackgroundTask uncaught, and the row was left `ok` forever: the UI
    showed success, the D3 sweep never re-touches an `ok` row, and the
    participações/empresas/certidão-9 side effects had silently never run.
    (b)/(c)/(d) now run inside a try — ANY exception marks `extracao_status
    ='erro'` with a coded `extracao_erro` and is logged, never raised
    into the caller's `await`; `ok`/`sem_dados` is stamped only once every
    side effect below has actually succeeded. A re-run (the D3 sweep, or
    the `.../extrair` re-run route once status is `erro`) is safe: (b) is
    D1 (fill-empty/conflict/equal), (c) upserts `empresas` by `(org_id,
    cnpj)` and `cliente_empresa_participacoes` by `(cliente_id,
    empresa_id)`, and (d) only ever supersedes an older Crednet-derived
    resultado — every step is naturally idempotent, so nothing here needed
    its own "already ran" guard.
    """
    fields = await extractor.extract(
        blob_data, mimetype=doc.get("mime_type"), filename=doc.get("nome_original")
    )

    if fields.error:
        _marcar(
            client, documento_id,
            extracao_status="erro",
            extracao_erro=f"{fields.error}: {fields.error_message or ''}".strip(": "),
            extracao_fonte=getattr(fields.source, "value", fields.source),
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": fields.error}

    try:
        dados = _serializar_crednet(fields)
        achou_algo = bool(
            fields.nome or fields.cpf or fields.nome_mae or fields.data_nascimento
            or fields.participacoes or fields.ocorrencias_constam() is not None
        )

        # (a) — the raw reading, before touching the cliente at all. NOT the
        # final `extracao_status` (2026-09-24 fix — see the docstring
        # above): this document is `ok`/`sem_dados` only once (b)/(c)/(d)
        # below have all actually run without raising.
        _marcar(
            client, documento_id,
            extracao_fonte=getattr(fields.source, "value", fields.source),
            extracao_erro=None,
            extracao_em=_now(),
            extracao_nome=fields.nome,
            extracao_nome_confianca=_confianca_de(fields, "nome_oficial"),
            extracao_nome_rotulo=_rotulo_de(fields, "nome_oficial"),
            extracao_cpf=fields.cpf,
            extracao_cpf_confianca=_confianca_de(fields, "cpf"),
            extracao_cpf_rotulo=_rotulo_de(fields, "cpf"),
            extracao_data_nascimento=(
                fields.data_nascimento.isoformat() if fields.data_nascimento else None
            ),
            extracao_confianca=_confianca_de(fields, "data_nascimento"),
            extracao_rotulo=_rotulo_de(fields, "data_nascimento"),
            extracao_nome_mae=fields.nome_mae,
            extracao_nome_mae_confianca=_confianca_de(fields, "nome_mae"),
            extracao_nome_mae_rotulo=_rotulo_de(fields, "nome_mae"),
            extracao_crednet=dados,
        )

        # (b) — D1 apply onto `clientes`.
        lidos = _lidos(fields)
        aplicados, conflitos = identidade_svc.aplicar_campos_ao_cliente(
            client, org_id, cliente_id, "serasa_crednet", lidos,
            campos=CAMPOS_CREDNET,
            documento_id=documento_id,
            fonte_tabela=DOCUMENTOS_TABLE,
            fonte_id=documento_id,
        )
        if conflitos:
            await identidade_svc.notificar_conflitos(
                client, org_id, conflitos, notification_service
            )

        # (c) — participações -> empresas.
        empresas_vinculadas: list[str] = []
        rejeitadas: list[dict] = []
        for participacao in fields.participacoes:
            if not participacao.cnpj or not participacao.cnpj_valido:
                rejeitadas.append(_participacao_dict(participacao))
                continue
            empresa = _upsert_empresa(client, org_id, participacao)
            _upsert_participacao(
                client, org_id, cliente_id, empresa["id"], participacao, documento_id
            )
            empresas_vinculadas.append(empresa["id"])
        if rejeitadas:
            _marcar(
                client, documento_id,
                extracao_crednet={**dados, "participacoes_rejeitadas": rejeitadas},
            )

        # (d) — certidão 9 (Serasa), the same stored PDF.
        from app.modules.certidoes import service as certidoes_svc

        certidoes_atualizadas = certidoes_svc.registrar_serasa_de_crednet(
            client, org_id, cliente_id, doc, fields
        )
    except Exception as exc:  # noqa: BLE001 - detached task; record, never raise
        # `on any exception` (2026-09-24 fix) means literally any — this
        # wraps the raw-reading write too, not only (b)/(c)/(d): a crash
        # serializing an otherwise-successful read must not leave the
        # document silently stuck with no `extracao_status` at all.
        logger.error(
            "crednet %s: side effects failed: %s", documento_id, exc, exc_info=True,
        )
        _marcar(
            client, documento_id,
            extracao_status="erro",
            extracao_erro=f"side_effects_failed: {exc}",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "side_effects_failed"}

    # Every side effect above succeeded — the status is terminal now.
    _marcar(client, documento_id, extracao_status="ok" if achou_algo else "sem_dados")

    return {
        "status": "ok" if achou_algo else "sem_dados",
        "aplicados": aplicados,
        "conflitos": len(conflitos),
        "empresas": empresas_vinculadas,
        "participacoes_rejeitadas": len(rejeitadas),
        "certidoes_atualizadas": certidoes_atualizadas,
    }


__all__ = ["CAMPOS_CREDNET", "aplicar_leitura"]
