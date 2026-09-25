"""Matrícula Text Extractor Service — the product's half of transcription.

Ported from `erp-imobiliario`'s `app/services/matricula_service.py`
(2026-09-02) as ERP is retired. The behaviour is intentionally identical;
what changed is the schema (`social_wiring`), the org source, and the fact
that this product has no `log_action` audit shim — see `router.py`.

The ladder itself lives in the seed:
`noctusai_lib.integrations.documents.make_document_transcriber` decides,
per page, whether the PDF's own text layer is real content or a scan's
signature stamp, and rasterizes → vision only for the pages it cannot
read. That module carries the history this file used to carry alone.

WHAT STAYS HERE
---------------
The `matricula_extracoes` row and its status lifecycle, and the mapping
from a machine error code to a sentence this product's users can act on.
That mapping is the reason the seed returns codes rather than prose: a
chatbot surfacing the same failure over WhatsApp needs different words
than a settings screen does.

🔴 EVERY WRITE CARRIES AN EXPLICIT `org_id` PREDICATE
------------------------------------------------------
The detached half of this workflow writes through the SERVICE-ROLE client
(a background task outlives the token that spawned it), and service-role
bypasses RLS. So the org scoping RLS performs on the request path has to be
performed by hand here. `_marcar` takes `org_id` and refuses to write
without one — a `None` that silently widened an UPDATE to every org is the
exact shape this file must not have.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.documents import detectar_ruido, has_raw_markup
from noctusai_lib.integrations.documents.formatting import ranges_to_json

from app.modules.imovel_hub.deps import BUCKET as IMOVEL_BUCKET
from app.modules.matriculas import estrutura_service, preenchimento_service
from app.services import documento_retencao, extracao_retentativa

logger = logging.getLogger(__name__)

TABLE = "matricula_extracoes"

#: A row stuck in a non-terminal state longer than this was orphaned by a
#: process that died mid-extraction. Generous enough that a slow vision pass
#: over a long matrícula is never mistaken for a dead one — the same 20
#: minutes `imovel_hub.matricula_extracao_service.STALE_APOS` uses, for the
#: same reason.
STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")

#: What a stranded row says once the sweep finds it. It cannot say "retrying"
#: because there is nothing to retry FROM: this workflow keeps no copy of the
#: uploaded PDF (see `varrer_pendentes`), so re-uploading is genuinely the
#: only way forward and the message says so rather than implying otherwise.
MENSAGEM_ORFA = (
    "A extração foi interrompida (o servidor reiniciou durante o "
    "processamento). Envie o PDF novamente."
)

#: The same situation for an extraction LINKED to an imóvel (migration 109):
#: its PDF is kept as the imóvel's document, so "send the file again" would
#: be false — the operator re-requests the transcription from that document
#: (`POST /api/matriculas/extracoes/de-documento`; an `erro` row never blocks
#: the retry).
MENSAGEM_ORFA_VINCULADA = (
    "A extração foi interrompida (o servidor reiniciou durante o "
    "processamento). O PDF continua guardado nos documentos do imóvel — "
    "solicite a transcrição novamente a partir dele."
)

#: Machine error code → what this product's users should read.
#:
#: Anything not listed here is a bug rather than a condition the user can
#: act on, so it falls through to `_MENSAGEM_PADRAO` WITH the developer
#: message attached — a generic apology that hides the cause is how a
#: silent error survives to production.
_MENSAGENS: dict[str, str] = {
    "no_pages": "PDF sem páginas — verifique se o arquivo não está corrompido.",
    "empty_document": "Arquivo vazio — envie o PDF da matrícula novamente.",
    # Deliberately does NOT name a vendor: with the manual switch in
    # Settings, which key is missing depends on which provider this org
    # selected, and a message hard-coded to "OpenAI" would send the
    # operator to fix a key that was never going to be used. The seed's
    # `error_message` names the provider for the log; the operator is sent
    # to the one screen that shows both the keys and the switch.
    "missing_credentials": (
        "A chave do provedor de IA selecionado não está configurada. "
        "Verifique em Configurações → Chaves de API qual provedor está "
        "escolhido e se a chave dele foi salva."
    ),
    "too_many_vision_pages": (
        "Documento muito longo para transcrição automática. "
        "Envie a matrícula em partes menores."
    ),
    # Names both billing pages rather than guessing: the switch means the
    # empty account could be either one, and sending the operator to the
    # wrong console is the same dead end as saying nothing.
    "insufficient_quota": (
        "Sem créditos na conta do provedor de IA selecionado — a transcrição "
        "de matrículas digitalizadas fica suspensa até que créditos sejam "
        "adicionados (OpenAI: platform.openai.com/settings/organization/"
        "billing · Anthropic: console.anthropic.com/settings/billing). Você "
        "também pode trocar de provedor em Configurações → Chaves de API. "
        "PDFs com camada de texto continuam funcionando normalmente."
    ),
    # These two named OpenAI as well, for the same reason and with the same
    # cost: an org running on Anthropic would be told to check a key it does
    # not use.
    "rate_limited": (
        "Limite de requisições do provedor de IA atingido. Aguarde alguns "
        "minutos e envie novamente — nada foi perdido."
    ),
    "invalid_credentials": (
        "A chave do provedor de IA selecionado foi recusada. Verifique-a em "
        "Configurações → Chaves de API."
    ),
    "rasterize_failed": (
        "Não foi possível ler todas as páginas do PDF. "
        "Verifique se o arquivo não está corrompido."
    ),
}

_MENSAGEM_PADRAO = "Erro inesperado: {detalhe}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mensagem_de_erro(resultado) -> str:
    """Render a transcription failure for this product's users."""
    conhecida = _MENSAGENS.get(resultado.error or "")
    if conhecida:
        return conhecida
    return _MENSAGEM_PADRAO.format(
        detalhe=resultado.error_message or resultado.error or "desconhecido"
    )


def _marcar(db, extracao_id: str, org_id: str, **updates: Any) -> None:
    """Write `updates` onto one row, scoped to its org.

    Raises rather than widening: `db` here is service-role, so an UPDATE
    without the org predicate would reach every tenant's rows.
    """
    if not org_id:
        raise ValueError(
            "matricula_extracoes update requires an org_id — a service-role "
            "write without one is not scoped to any tenant"
        )
    (
        db.table(TABLE)
        .update(updates)
        .eq("id", extracao_id)
        .eq("org_id", org_id)
        .execute()
    )


async def processar_extracao(
    extracao_id: str,
    pdf_bytes: bytes,
    org_id: str,
    db,
    transcriber=None,
    transcriber_factory=None,
    notificador=None,
) -> None:
    """Full extraction pipeline — runs as a background task. NEVER raises.

    Migration 154: once the text and its acts land, a transcription LINKED
    to an imóvel feeds `imovel_dados` (`preenchimento_service`, D1 — fill
    empty, conflict otherwise); `notificador` announces any conflict. A
    failure stores the seed's machine code in `erro_codigo`, which is what
    the sweep's D3 retry decision reads.

    An exception escaping here surfaces NOWHERE: no user sees it, no
    response carries it, and the row sits in `processando` forever. So every
    outcome, including the ugly ones, is written to the row.

    `transcriber` is the direct test seam. `transcriber_factory` is the
    production seam (`app.modules.matriculas.deps.get_transcriber_factory`)
    — a factory rather than an instance so the org's credential is resolved
    at extraction time rather than at import time.
    """
    try:
        _marcar(db, extracao_id, org_id, status="processando")

        if transcriber is None:
            if transcriber_factory is None:
                raise ValueError(
                    "processar_extracao needs a transcriber or a "
                    "transcriber_factory — it must never build its own"
                )
            transcriber = transcriber_factory(org_id)

        resultado = await transcriber.transcribe(
            pdf_bytes, mimetype="application/pdf"
        )

        if not resultado.ok:
            logger.warning(
                "Matrícula %s: transcription failed (%s) %s",
                extracao_id, resultado.error, resultado.error_message or "",
            )
            _marcar(
                db, extracao_id, org_id,
                status="erro",
                erro_mensagem=_mensagem_de_erro(resultado),
                erro_codigo=resultado.error or "transcription_failed",
            )
            return

        logger.info(
            "Matrícula %s: %d pages — %d from text layer, %d via vision",
            extracao_id,
            resultado.num_paginas,
            len(resultado.paginas_por_camada),
            len(resultado.paginas_por_visao),
        )

        # 🔴 Stamped on the SAME write that lands the text (migration 111) —
        # `documento_retencao.dias_para` reads the two-tier policy under
        # `superficie="imovel"`, `tipo_documento="texto_extraido"`. `None`
        # when there is no policy row or the policy says keep indefinitely;
        # both read as "does not expire" to `estrutura_service.
        # purgar_texto_expirado`.
        dias = documento_retencao.dias_para(db, org_id, "imovel", "texto_extraido")
        retencao_ate = (
            (datetime.now(timezone.utc).date() + timedelta(days=dias)).isoformat()
            if dias
            else None
        )
        # CLOSED (was NOC-REMEDIATE[transcricao-formatacao-backfill]): the
        # marker undercounted its own finding — ALL 6 prod rows at the time
        # (not "5 in prod"), which is 100% of the corpus, not a minority. It
        # also named a destination ("until re-transcribed") that did not
        # exist yet: the standalone upload path discarded `pdf_bytes` right
        # after this function returned, so there was nothing left to
        # re-transcribe FROM. Migration 135 (`arquivos_svc`, `estrutura_svc.
        # criar_retranscricao`) closes both gaps — the source is retained
        # going forward, and a concluded extraction can be superseded by a
        # fresh transcription of it without fighting the write-once guard.
        # The 6 pre-135 rows keep no source (135's own header says so) and
        # cannot be repaired by this or any future change; migration 135's
        # backfill flags them `possui_marcacao_bruta = true` so an operator
        # can SEE the defect instead of it hiding in `texto_extraido`, and
        # `contrato_gerador.derivacao` refuses to generate a contract off
        # markered text regardless of this column. — 2026-09-17
        possui_marcacao_bruta = has_raw_markup(resultado.text)
        if possui_marcacao_bruta:
            # A NEW transcription should never reach here — `parse_markup`
            # (the seed's transcriber) strips every well-formed `**`/`<u>`
            # marker before `resultado.text` exists. Landing here means a
            # malformed vision reply left one unbalanced/stray (kept literal
            # ON PURPOSE by `parse_markup` rather than guessed at) — logged
            # so it is investigated, not silently swept into the same bucket
            # as the pre-135 legacy rows.
            logger.warning(
                "Matrícula %s: transcribed text still carries a raw "
                "**/<u> marker — parse_markup kept it literal (unbalanced "
                "or malformed vision reply)",
                extracao_id,
            )
        # 🔴 Migration 136 — computed and written on this SAME call, never a
        # follow-up. The acts below are deliberately written in their own
        # try (they self-heal: `estrutura_service.listar_atos` re-segments a
        # concluded extraction with no acts on its first read) but `ruido`
        # CANNOT self-heal the same way — it needs `resultado.pages`, which
        # cease to exist the moment this function returns, and migration
        # 136's write-once guard freezes `ruido` once `status='concluida'`.
        # If it is not on the text write, it is lost for good.
        ruido = [
            {"start": r.start, "end": r.end, "kind": r.kind}
            for r in detectar_ruido(resultado.pages)
        ]
        _marcar(
            db, extracao_id, org_id,
            status="concluida",
            texto_extraido=resultado.text,
            formatacao=ranges_to_json(resultado.formatting),
            num_paginas=resultado.num_paginas,
            retencao_ate=retencao_ate,
            possui_marcacao_bruta=possui_marcacao_bruta,
            ruido=ruido,
            erro_mensagem=None,
            erro_codigo=None,
        )

        # The acts (migration 109), as offsets into the text that just landed.
        # Deliberately AFTER the text write and in its own try: the text is
        # the product of a paid vision pass and must not be rolled back to
        # `erro` because a second insert failed. The failure is logged at
        # ERROR and self-heals — `estrutura_service.listar_atos` re-segments
        # a concluded extraction that has no acts on its first read.
        try:
            escritos = estrutura_service.persistir_atos(
                db, extracao_id, org_id, resultado.text
            )
            logger.info("Matrícula %s: %d acts persisted", extracao_id, escritos)
        except Exception as falha_atos:  # noqa: BLE001 - text landed; acts heal on read
            logger.error(
                "Matrícula %s: text saved but its acts were not persisted (%s) — "
                "they are re-segmented on the first GET .../atos",
                extracao_id, falha_atos, exc_info=True,
            )

    except Exception as e:  # noqa: BLE001 - detached task; record, never raise
        logger.error(
            "Matrícula %s extraction failed: %s", extracao_id, e, exc_info=True
        )
        _registrar_erro(db, extracao_id, org_id, f"Erro inesperado: {e}", e)
        return

    # Outside the try above on purpose: the transcription is DONE and
    # recorded; nothing the imóvel fill does may flip it to `erro`.
    # `preencher_imovel` never raises and no-ops for an unlinked extraction.
    resumo = await preenchimento_service.preencher_imovel(
        db, org_id, extracao_id, notificador=notificador
    )
    logger.info("Matrícula %s: imovel_dados fill %s", extracao_id, resumo)


def registrar_transcricao_manual(db, extracao_id: str, org_id: str, texto: str) -> None:
    """Land a manually-typed/pasted matrícula text (migration 149) through
    the SAME finalisation `processar_extracao` runs once a transcription's
    text exists: the retention stamp, the raw-markup check, and act
    segmentation — so an `origem='manual'` row is indistinguishable to every
    downstream reader (`estrutura_service`, `titulo_service`,
    `contrato_gerador`) from an AI-transcribed one.

    🔴 `ruido` (migration 136) is deliberately `[]`, not recomputed. Page
    furniture (running headers/footers) is a property of a MULTI-PAGE scan
    (`detectar_ruido` needs `TranscribedPage`s to find a block that repeats
    at more than one page boundary) — a human pasting the whole matrícula's
    text has no page structure at all, so there is nothing here for that
    detector to find. Runs on the request path, not detached, so unlike
    `processar_extracao` an exception here IS allowed to propagate — the
    caller (the router) is still holding an HTTP response to answer.
    """
    dias = documento_retencao.dias_para(db, org_id, "imovel", "texto_extraido")
    retencao_ate = (
        (datetime.now(timezone.utc).date() + timedelta(days=dias)).isoformat()
        if dias
        else None
    )
    possui_marcacao_bruta = has_raw_markup(texto)
    _marcar(
        db, extracao_id, org_id,
        status="concluida",
        texto_extraido=texto,
        formatacao=ranges_to_json(()),
        num_paginas=None,
        retencao_ate=retencao_ate,
        possui_marcacao_bruta=possui_marcacao_bruta,
        ruido=[],
    )
    try:
        escritos = estrutura_service.persistir_atos(db, extracao_id, org_id, texto)
        logger.info("Matrícula %s (manual): %d acts persisted", extracao_id, escritos)
    except Exception as falha_atos:  # noqa: BLE001 - text landed; acts heal on read
        logger.error(
            "Matrícula %s (manual): text saved but its acts were not persisted (%s) — "
            "they are re-segmented on the first GET .../atos",
            extracao_id, falha_atos, exc_info=True,
        )

    # NOC-REMEDIATE[matricula-manual-transcricao-sem-preenchimento]: unlike
    # `processar_extracao`, this never calls `preenchimento_service.
    # preencher_imovel` — a manually-typed/pasted matrícula transcription
    # lands its text/acts but never promotes numero_matricula/titulo/onus/
    # etc. onto `imovel_dados` at all. Found auditing the P1/883 fix for
    # the automatic pipeline's own promotion gap. Named destination:
    # roadmap sw-drive-extraction P1 round 2 — 2026-09-24


def _registrar_erro(
    db, extracao_id: str, org_id: str, mensagem: str, causa, *, codigo: str = "erro_inesperado"
) -> None:
    """Write `erro` onto the row — the last thing a detached task can do.

    If even that fails (bad org_id, DB down) there is nowhere else to report
    to, so the log IS the report — it must not be swallowed, and it must not
    mask the original failure.
    """
    try:
        _marcar(
            db, extracao_id, org_id,
            status="erro", erro_mensagem=mensagem, erro_codigo=codigo,
        )
    except Exception as falha:  # noqa: BLE001 - last resort; say so
        logger.error(
            "Matrícula %s: could not even record the failure: %s "
            "(original error: %s)",
            extracao_id, falha, causa,
        )


async def processar_extracao_de_documento(
    extracao_id: str,
    storage_path: str,
    org_id: str,
    db,
    storage,
    *,
    transcriber=None,
    transcriber_factory=None,
    notificador=None,
) -> None:
    """Read an imóvel's KEPT matrícula PDF back out of storage, then run the
    one transcription pipeline (`processar_extracao`). NEVER raises.
    """
    try:
        blob = await storage.get(bucket=IMOVEL_BUCKET, key=storage_path)
    except Exception as e:  # noqa: BLE001 - detached task; record, never raise
        logger.warning("Matrícula %s: storage read failed: %s", extracao_id, e)
        _registrar_erro(
            db, extracao_id, org_id,
            "Não foi possível ler o PDF guardado no imóvel. Tente novamente.", e,
            codigo="storage",
        )
        return
    if blob is None:
        logger.warning(
            "Matrícula %s: stored object %s is missing", extracao_id, storage_path
        )
        _registrar_erro(
            db, extracao_id, org_id,
            "O PDF da matrícula não foi encontrado no armazenamento do imóvel.",
            "objeto ausente",
            codigo="objeto_ausente",
        )
        return
    await processar_extracao(
        extracao_id,
        blob.data,
        org_id,
        db,
        transcriber=transcriber,
        transcriber_factory=transcriber_factory,
        notificador=notificador,
    )


async def varrer_pendentes(
    client,
    _storage=None,
    *,
    limite: int = 50,
    transcriber_factory=None,
    notificador=None,
) -> dict:
    """Close out extractions that were started and never finished.

    🔴 WHY THIS EXISTS. `status` moves to `processando` before the work and
    to a terminal value after it. If the process dies in between — a deploy,
    an OOM kill, a container restart — nothing ever moves it again. The row
    sits there, the text never fills in, and NOTHING SURFACES. The same is
    true of `pendente` when the background task was never scheduled at all.

    🔴 WHY THIS MARKS `erro` INSTEAD OF RETRYING, unlike `card_hub` /
    `imovel_hub`. Those two read their bytes back out of Storage, so a
    stranded document can genuinely be re-read. A legacy UNLINKED upload
    keeps NO copy of the PDF — the bytes live only in the `BackgroundTask`'s
    closure (ERP's shape, ported unchanged). When the process dies the bytes
    die with it. So the honest recovery is to tell the user the truth and
    ask for the file again; pretending a retry is possible would leave the
    row cycling through `processando` forever, which is the silent error
    this sweep exists to remove, wearing a different hat.

    A LINKED extraction (migration 109) does keep its PDF, as the imóvel's
    document, and the message says so (`MENSAGEM_ORFA_VINCULADA`): the
    operator re-requests it from that document. It is still marked rather
    than retried here because a retry needs the org's transcriber, which is
    a per-request DI seam this scheduler does not hold.

    `_storage` is accepted and ignored: `app.services.extraction_sweep`'s
    `SweepFn` contract is `(admin_client, storage_backend)`, shared with the
    two sweeps that DO need storage.

    🔴 D3 RETRY (migration 154). When the scheduler hands a
    `transcriber_factory`, a second phase retries FAILED rows
    (`status='erro'`) whose source PDF was kept — the credit-exhaustion
    shape, where the fix (credits added) happens outside the document.
    At most `extracao_retentativa.MAX_RETENTATIVAS` times per row, only for a
    retryable `erro_codigo`, in place (same row, same id — an `erro` row has
    no text and no acts, so nothing quotes it), then the row stays `erro`
    for a human. See `_retentar_falhas`.
    """
    cutoff = (_now() - STALE_APOS).isoformat()

    # Both halves below are provably bounded, not assumed to be. The `in_`
    # list is the 2-element module constant `_ESTADOS_NAO_TERMINAIS` — it
    # cannot grow at runtime, so it can never overflow the URL query string.
    # The select carries `.limit(limite)` (default 50), far under PostgREST's
    # 1 000-row cap, and deliberately does NOT page: a sweep that walked every
    # stranded row in one pass would rewrite an unbounded slice of the table
    # in a single scheduled run. It runs hourly and closes out `limite` rows a
    # run, which is the right shape for a recovery job.
    #
    # postgrest-unbounded-ok: fixed 2-element `in_` constant, `.limit(limite)`.
    presos = (
        client.table(TABLE)
        .select("id,org_id,nome_arquivo,status,imovel_documento_id")
        .in_("status", list(_ESTADOS_NAO_TERMINAIS))
        .lt("updated_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []

    marcados = 0
    for row in presos:
        org_id = row.get("org_id")
        if not org_id:
            # An org-less row cannot exist (NOT NULL + DEFAULT
            # current_org_id()), so one here means the schema drifted.
            # Say so; do not widen the UPDATE to reach it.
            logger.error(
                "matricula sweep: row %s has no org_id — skipping (schema drift?)",
                row.get("id"),
            )
            continue
        _marcar(
            client, row["id"], str(org_id),
            status="erro",
            erro_mensagem=(
                MENSAGEM_ORFA_VINCULADA
                if row.get("imovel_documento_id")
                else MENSAGEM_ORFA
            ),
        )
        marcados += 1

    resultado = {"encontrados": len(presos), "marcados": marcados}
    if transcriber_factory is not None:
        resultado.update(
            await _retentar_falhas(
                client, _storage, transcriber_factory, notificador, limite=limite
            )
        )
    return resultado


async def _retentar_falhas(
    client, storage, transcriber_factory, notificador, *, limite: int
) -> dict:
    """The D3 retry phase of `varrer_pendentes` — see its docstring.

    A row a retry cannot help (no retained source, or a permanent failure
    such as an empty PDF) gets `retentativas` set to the cap, with a log
    line: it leaves the retry pool for good, instead of being re-read and
    skipped every hour (and crowding the `limite` window forever).
    """
    cutoff = (_now() - STALE_APOS).isoformat()
    # postgrest-unbounded-ok: `.limit(limite)` — a recovery job, bounded per run.
    falhas = (
        client.table(TABLE)
        .select("*")
        .eq("status", "erro")
        .lt("retentativas", extracao_retentativa.MAX_RETENTATIVAS)
        .lt("updated_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []

    retentadas = 0
    esgotadas = 0
    for row in falhas:
        org_id = str(row.get("org_id") or "")
        if not org_id or row.get("substituida_por"):
            continue
        caminho = None
        if extracao_retentativa.retentavel(row.get("erro_codigo")):
            caminho = estrutura_service.caminho_da_fonte(client, org_id, row)
        if caminho is None:
            logger.info(
                "matricula sweep: %s (erro_codigo=%s) cannot be retried — no kept "
                "source or a permanent failure; leaving it erro for a human",
                row["id"], row.get("erro_codigo"),
            )
            _marcar(
                client, row["id"], org_id,
                retentativas=extracao_retentativa.MAX_RETENTATIVAS,
            )
            esgotadas += 1
            continue
        _marcar(
            client, row["id"], org_id,
            status="pendente",
            retentativas=int(row.get("retentativas") or 0) + 1,
        )
        await processar_extracao_de_documento(
            row["id"], caminho, org_id, client, storage,
            transcriber_factory=transcriber_factory, notificador=notificador,
        )
        retentadas += 1
    return {"retentadas": retentadas, "esgotadas": esgotadas}


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Check which required credentials are missing for matrícula extraction.

    Still reports the key as required: it is needed for any SCANNED matrícula,
    and the caller cannot know in advance which kind will be uploaded. Since
    rung 1 landed, a digitally-issued PDF will extract without it — so this is
    a warning about what may fail, not a hard precondition for every document.
    """
    # Checks the SELECTED provider's key, not OpenAI's unconditionally —
    # otherwise an org running on Anthropic would be warned forever about a
    # key it deliberately does not use, which trains operators to ignore
    # this panel.
    #
    # `resolve_credential` (not `api_keys_store.resolve_api_key`) is correct
    # here: `main.py` registers the product's encrypted store as tier 0 of
    # that same chain, so a key saved in the UI is already visible through
    # it. That closes NOC-REMEDIATE[matriculas-api-key-store] — the marker's
    # concern was that the store was invisible, and it no longer is.
    from app.services.api_keys_store import get_spec, resolve_vision_provider

    missing = []
    provider = resolve_vision_provider(org_id)
    spec = get_spec(f"{provider}_api_key")
    rotulo = spec.label if spec else f"{provider}_api_key"
    # `.strip()`: a blank saved key is as missing as no key — same rule the
    # seed transcriber's own pre-check applies.
    if not (resolve_credential(f"{provider}_api_key", org_id) or "").strip():
        missing.append(
            f"{rotulo} não configurada — é o provedor selecionado para "
            "extração de matrículas digitalizadas (PDFs com camada de texto "
            "não precisam)."
        )
    return missing


def texto_html_da_extracao(texto: Optional[str], formatacao_json) -> Optional[str]:
    """Word-pasteable HTML of a transcript — `GET .../extracoes/{id}`'s
    `texto_html` field. `None` when there is no text yet (an in-progress or
    failed extraction), never an HTML fragment of an empty string.
    `formatacao_json` is the raw `jsonb` column value (possibly `None` for a
    row written before migration 113).
    """
    if not texto:
        return None
    from noctusai_lib.integrations.documents.abnt import (
        paragraphs_from_text,
        render_word_html,
    )
    from noctusai_lib.integrations.documents.formatting import (
        FormattedDocument,
        ranges_from_json,
    )

    doc = FormattedDocument(
        paragraphs=paragraphs_from_text(texto, ranges_from_json(formatacao_json))
    )
    return render_word_html(doc)


def renderizar_extracao_pdf(nome_arquivo: str, texto: str, formatacao_json) -> bytes:
    """ABNT-formatted PDF of one matrícula transcript, titled
    `"Transcrição da matrícula — <nome_arquivo>"` (contract §4).

    Raises `noctusai_lib.integrations.documents.abnt.UnsupportedGlyphError`
    straight through — the router turns it into a 422 naming the character,
    never a silent 500.
    """
    from noctusai_lib.integrations.documents.abnt import (
        paragraphs_from_text,
        render_abnt_pdf,
    )
    from noctusai_lib.integrations.documents.formatting import (
        FormattedDocument,
        Paragraph,
        ParagraphKind,
        Run,
        ranges_from_json,
    )

    titulo = f"Transcrição da matrícula — {nome_arquivo}"
    corpo = paragraphs_from_text(texto, ranges_from_json(formatacao_json))
    titulo_paragrafo = Paragraph(runs=(Run(text=titulo),), kind=ParagraphKind.TITLE)
    doc = FormattedDocument(paragraphs=(titulo_paragrafo, *corpo), title=titulo)
    return render_abnt_pdf(doc)


__all__ = [
    "MENSAGEM_ORFA",
    "MENSAGEM_ORFA_VINCULADA",
    "STALE_APOS",
    "TABLE",
    "check_required_credentials",
    "processar_extracao",
    "processar_extracao_de_documento",
    "renderizar_extracao_pdf",
    "texto_html_da_extracao",
    "varrer_pendentes",
]
