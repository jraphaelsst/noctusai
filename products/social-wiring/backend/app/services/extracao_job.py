"""The ONE shape for "read a document, persist the reading, apply it" —
the recurrence-rule formalization an audit against origin/dev found
missing (lesson G6).

🔴 WHY THIS EXISTS
------------------
`card_hub.crednet_service.aplicar_leitura` and `card_hub.
negociacao_extracao_service.extrair` already got this right BEFORE this
runner existed: the reading is persisted, the D1 apply runs INSIDE a
`try`, and the TERMINAL `extracao_status` is written LAST — only once the
apply step (which can touch several tables, open conflicts, fire
notifications) has actually succeeded. An exception there ends the job in
`erro`, never a false `ok`. Both are now BUILT on this runner too
(`NOC-REMEDIATE[extracao-job-runner-adopt]`, 2026-09-28 — a
behavior-preserving swap onto the shared shape, not a fix) — see each
module's own docstring for the one documented, test-uncovered behavioral
note the swap carries (a failed-extraction sentinel now also (re)writes
`extracao_fonte`, where the pre-swap code left it untouched).

Three siblings did NOT follow that shape — each stamped a terminal `ok`
BEFORE running its own apply step, with no exception handling (or a
`try` that only logs) around it:

- `card_hub.identidade_extracao_service.extrair_identidade` — `ok` written,
  then `aplicar_campos_ao_cliente` called with no try at all.
- `empresas.extracao_service.extrair_cartao` — `ok` written, then
  `dados_service.aplicar_cartao` called with no try at all.
- `imovel_hub.matricula_extracao_service.extrair` — `ok` written, then
  `campos_svc.aplicar` called in a try that only LOGS the exception,
  leaving the already-written `ok` standing.

A transient PostgREST/DB error during any of those apply steps used to
mean: the document shows `ok`, the target field is never filled, no
conflict is opened, and the sweep never revisits an `ok` row — an
older/wrong stored value silently flows into whatever gets generated
downstream. That is N=3 broken instances plus the 2 already-correct
references above — five total, past the recurrence rule's N=3 MUST-
formalize threshold (`KB § PATTERNS/architect/project-execution.md`).

WHAT THIS OWNS
--------------
- `ExtractionJobConfig` — the handful of things that differ per surface
  (table, bucket, `deve_extrair`, how to call the extractor, how to read
  its error, and the `processar` callback that persists the FULL reading
  and runs every D1 apply / conflict / notification side effect).
- `preparar` — fetch+validate the document, stamp `processando`, fetch the
  blob, log the access. Split out (rather than folded into `executar`) so
  a caller whose document type delegates to an ALREADY G6-compliant
  sibling pipeline (identity's Crednet branch, which owns its own
  extract+persist+apply+terminal-status end to end once handed a blob —
  see `crednet_service.aplicar_leitura`'s own `executar_com_blob` call)
  can reuse this preamble without going through `executar`'s own
  `ler`/`processar` split.
- `executar_com_blob` — extract, check the reading's own error, then run
  `processar` inside ONE try/except: an exception ANYWHERE in it (persist
  OR apply OR notify) ends the job in `erro` with a named code, logged
  with context, never swallowed. The terminal status is written ONLY
  after `processar` returns successfully.
- `executar` — `preparar` + `executar_com_blob` composed, for the common
  case of one extraction pipeline per document
  (`empresas.extracao_service.extrair_cartao`,
  `imovel_hub.matricula_extracao_service.extrair`).

WHAT THIS DOES **NOT** OWN
---------------------------
The RECOVERY sweep (finding never-finished/never-started/retryable rows)
is `app.services.extracao_varredura`'s job, not this module's — this
module runs ONE job; that one finds candidates and calls back into
whichever `extrair`/`extrair_cartao` a surface exposes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from app.services import table_reads

logger = logging.getLogger(__name__)

#: Outcomes a `processar` callback's `resultado["status"]` may carry.
OK = "ok"
SEM_DADOS = "sem_dados"
ERRO = "erro"

#: The named error codes `executar`/`executar_com_blob`/`preparar` may
#: return on `documento["erro"]` themselves (a `processar` callback names
#: its OWN code via `ExtractionJobConfig.erro_aplicar_codigo`).
ERRO_DOCUMENTO_NAO_ENCONTRADO = "documento_nao_encontrado"
ERRO_DOCUMENTO_REMOVIDO = "documento_removido"
ERRO_TIPO_NAO_EXTRAIVEL = "tipo_nao_extraivel"
ERRO_STORAGE = "storage"
ERRO_OBJETO_AUSENTE = "objeto_ausente"
ERRO_APLICAR_PADRAO = "aplicar_leitura"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def marcar(client: Any, table: str, documento_id: UUID, **campos: Any) -> None:
    """The one `UPDATE ... WHERE id=` every step in this family makes —
    exposed so a surface's `processar` callback can persist its OWN
    reading columns (and any table-specific extras) without re-deriving
    `table_reads.table(...)` itself."""
    _t(client, table).update(campos).eq("id", str(documento_id)).execute()


@dataclass(frozen=True)
class ExtractionJobConfig:
    """One surface's wiring — everything the shared skeleton needs to stay
    generic over table shape, extractor construction, and apply logic."""

    #: The documents table (`cliente_documentos`, `empresa_documentos`, ...).
    table: str
    bucket: str
    #: `tipo_documento -> bool` — is this a type we extract at all?
    deve_extrair: Callable[[str], bool]
    #: `(blob_bytes, doc_row) -> leitura` — the extractor call, ALREADY
    #: bound to a concrete extractor instance by the caller (mirrors every
    #: existing `extrair` accepting `extractor=` from ITS OWN caller).
    ler: Optional[Callable[[bytes, dict], Awaitable[Any]]] = None
    #: `leitura -> error_code|None` — `None` means no error, proceed.
    leitura_erro: Callable[[Any], Optional[str]] = lambda leitura: None
    leitura_erro_mensagem: Callable[[Any], Optional[str]] = lambda leitura: None
    #: `leitura -> extracao_fonte value|None` — recorded on the erro path
    #: (the happy path records it as part of `processar`'s own persist,
    #: since the FULL reading is that callback's job).
    leitura_fonte: Callable[[Any], Optional[str]] = lambda leitura: None
    #: `(org_id, documento_id) -> None` — the audit-log write, called AFTER
    #: the blob is confirmed present, BEFORE extraction (every sibling's
    #: own rule: "logged before the read, so a crash still records it").
    log_acesso: Optional[Callable[[UUID, UUID], None]] = None
    #: `(leitura, doc_row) -> {"status": OK|SEM_DADOS, "aviso": str|None, **info}`
    #: — persists the FULL reading and runs every D1 apply / conflict /
    #: notification side effect. Everything it does is ONE failure domain:
    #: an exception ANYWHERE inside it — persisting the reading, applying
    #: a field, opening a conflict, firing a notification — ends the job
    #: in `erro`, never a false terminal `ok`. `info` keys are returned to
    #: the CALLER only; they are never written back onto the document row
    #: (only `extracao_status`/`extracao_erro`/`extracao_em`, plus
    #: `extracao_aviso` when `suporta_aviso=True`, are).
    processar: Optional[Callable[[Any, dict], Awaitable[dict]]] = None
    #: The named `erro` code recorded when `processar` raises.
    erro_aplicar_codigo: str = ERRO_APLICAR_PADRAO
    #: Does `table` have an `extracao_aviso` column? Only
    #: `atendimento_documentos` does (migration 171) — writing it
    #: elsewhere would 400 on a column that doesn't exist.
    suporta_aviso: bool = False


async def preparar(
    client: Any, storage: Any, org_id: UUID, documento_id: UUID, config: ExtractionJobConfig,
) -> tuple[Optional[dict], Optional[Any], Optional[dict]]:
    """(a) fetch+validate, stamp `processando`, fetch the blob, log the
    access. Returns `(doc, blob, None)` on success — `doc["extracao_
    tentativas"]` is updated in place to the just-stamped value — or
    `(None, None, error_dict)` when the job cannot proceed, with the
    failure already recorded on the document row."""
    rows = (
        _t(client, config.table).select("*").eq("org_id", str(org_id))
        .eq("id", str(documento_id)).limit(1).execute()
    ).data or []
    if not rows:
        logger.warning(
            "extracao_job %s: documento %s not found for org %s", config.table, documento_id, org_id,
        )
        return None, None, {"status": ERRO, "erro": ERRO_DOCUMENTO_NAO_ENCONTRADO}

    doc = rows[0]
    if doc.get("deleted_at"):
        # Deleted between upload and this job. Reading its bytes now would
        # be work on something the client already asked us to forget.
        return None, None, {"status": ERRO, "erro": ERRO_DOCUMENTO_REMOVIDO}
    if not config.deve_extrair(str(doc.get("tipo_documento") or "")):
        return None, None, {"status": ERRO, "erro": ERRO_TIPO_NAO_EXTRAIVEL}

    tentativas = int(doc.get("extracao_tentativas") or 0) + 1
    marcar(
        client, config.table, documento_id,
        extracao_status="processando", extracao_em=_now(), extracao_tentativas=tentativas,
    )
    doc["extracao_tentativas"] = tentativas

    try:
        blob = await storage.get(bucket=config.bucket, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("extracao_job %s %s: storage read failed: %s", config.table, documento_id, exc)
        marcar(
            client, config.table, documento_id,
            extracao_status=ERRO, extracao_erro=f"storage: {exc}", extracao_em=_now(),
        )
        return None, None, {"status": ERRO, "erro": ERRO_STORAGE}

    if blob is None:
        marcar(
            client, config.table, documento_id,
            extracao_status=ERRO, extracao_erro="objeto ausente no storage", extracao_em=_now(),
        )
        return None, None, {"status": ERRO, "erro": ERRO_OBJETO_AUSENTE}

    # Logged BEFORE the extraction — same rule every sibling in this
    # product follows: an access log that only records successful reads is
    # not an access log.
    if config.log_acesso is not None:
        config.log_acesso(org_id, documento_id)

    return doc, blob, None


async def executar_com_blob(
    client: Any, config: ExtractionJobConfig, documento_id: UUID, doc: dict, blob: Any, tipo_documento: str,
) -> dict:
    """(b)-(e), given an already-fetched `doc`/`blob` (from `preparar`, or
    from a caller with its own preamble — see `identidade_extracao_
    service.extrair_identidade`'s Crednet branch): extract, check the
    reading's own error, then ONE failure domain (`config.processar`)
    ending in the terminal status — never before it (lesson G6)."""
    leitura = await config.ler(blob.data, doc)

    erro_codigo = config.leitura_erro(leitura)
    if erro_codigo:
        # The DPS-tripwire rule every sibling follows: a failed reading is
        # NEVER persisted — `extracao_dados` stays whatever it already was.
        mensagem = config.leitura_erro_mensagem(leitura) or ""
        marcar(
            client, config.table, documento_id,
            extracao_status=ERRO,
            extracao_erro=f"{erro_codigo}: {mensagem}".strip(": "),
            extracao_fonte=config.leitura_fonte(leitura),
            extracao_em=_now(),
        )
        return {"status": ERRO, "erro": erro_codigo}

    # 🔴 EVERYTHING FROM HERE ON IS ONE FAILURE DOMAIN (lesson G6).
    # Persisting the reading and applying it are different operations, but
    # a failure in EITHER must land the same way — `erro`, never an
    # uncaught exception left to crash the detached background task (which
    # would strand the document in `processando` until the sweep's stale
    # timeout) and never a false `ok`.
    try:
        resultado = await config.processar(leitura, doc)
    except Exception as exc:  # noqa: BLE001 - lesson G6: never a false 'ok'
        logger.exception(
            "extracao_job %s %s: apply failed (tipo=%s)", config.table, documento_id, tipo_documento,
        )
        marcar(
            client, config.table, documento_id,
            extracao_status=ERRO, extracao_erro=f"{config.erro_aplicar_codigo}: {exc}", extracao_em=_now(),
        )
        return {"status": ERRO, "erro": config.erro_aplicar_codigo}

    # (e) — only NOW the terminal status lands, and ONLY the fields this
    # runner owns: `processar`'s other `resultado` keys are informational,
    # returned to the caller, never written back onto the document row.
    status = resultado.get("status", OK)
    terminal: dict[str, Any] = {"extracao_status": status, "extracao_erro": None, "extracao_em": _now()}
    if config.suporta_aviso:
        terminal["extracao_aviso"] = resultado.get("aviso")
    marcar(client, config.table, documento_id, **terminal)
    return {**resultado, "status": status}


async def executar(
    client: Any, storage: Any, org_id: UUID, documento_id: UUID, config: ExtractionJobConfig,
) -> dict:
    """The common case: ONE extraction pipeline per document —
    `preparar` + `executar_com_blob` composed. Never raises; every path
    ends in a recorded `extracao_status`."""
    doc, blob, erro = await preparar(client, storage, org_id, documento_id, config)
    if erro is not None:
        return erro
    tentativas = doc.get("extracao_tentativas")
    resultado = await executar_com_blob(
        client, config, documento_id, doc, blob, str(doc.get("tipo_documento") or ""),
    )
    return {**resultado, "tentativas": tentativas}


__all__ = [
    "ERRO",
    "ERRO_APLICAR_PADRAO",
    "ERRO_DOCUMENTO_NAO_ENCONTRADO",
    "ERRO_DOCUMENTO_REMOVIDO",
    "ERRO_OBJETO_AUSENTE",
    "ERRO_STORAGE",
    "ERRO_TIPO_NAO_EXTRAIVEL",
    "OK",
    "SEM_DADOS",
    "ExtractionJobConfig",
    "executar",
    "executar_com_blob",
    "marcar",
    "preparar",
]
