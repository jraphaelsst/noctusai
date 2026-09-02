"""Certidões Negativas — the issuance pipeline.

Orchestrates certificate emission via the InfoSimples API, AI-powered document
analysis, and result persistence. Each certificate type is declared in
`registry.CERTIDOES_CONFIG`; the pipeline (fetch → download → convert → store →
analyze) is shared across all of them.

Ported from `products/erp-imobiliario/backend/app/services/certidoes_service.py`
as the ERP product is retired. Four things changed, and only these four:

1. **Storage goes through the seed seam.** ERP uploaded through its
   product-local `StorageService` into an `erp-certidoes` bucket and got a
   PUBLIC url back. This product owns no such service: it consumes
   `noctusai_lib.integrations.storage.StorageBackend` and writes into the
   existing `social-wiring-documentos` bucket under a `certidoes/` prefix.
   See `_persist_pdf` for what `arquivo_url` now holds and why.

2. **The delete workaround is gone, not ported.** ERP's `_delete_storage_files`
   reached past its own StorageService into `db.storage.from_(bucket).remove()`
   because that service silently fell back to a dry-run under a non-admin
   client — i.e. it worked around a defect in its own abstraction. The seed
   seam has no such fallback, so the delete is expressed through it.

3. **Credentials resolve through `credentials.resolve_key`.** One indirection,
   for the reason its module docstring gives.

4. **`log_action` is dropped.** This product has no audit-log helper, and
   inventing a shim for one feature would be a fork of an audit surface rather
   than an audit surface. Surfaced as `drift-found:`.

Everything else — the retry ladder, the 612/"nada consta" branch, the
content-type detection, the TJSP cooldown queue, the two recovery sweeps, the
cancel path, the manual-upload pipeline — is the ERP behaviour, because it is
the behaviour a live user depends on.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.tasks import schedule_coro
from xhtml2pdf import pisa

from app.modules.certidoes.credentials import (
    INFOSIMPLES_TOKEN,
    OPENAI_API_KEY,
    resolve_key,
)
from app.modules.certidoes.deps import BUCKET, PREFIXO
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    INFOSIMPLES_BASE_URL,
    PARAM_BUILDERS,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    config_for,
)

logger = logging.getLogger(__name__)

CONSULTAS = "certidao_consultas"
RESULTADOS = "certidao_resultados"

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 240.0

#: Maximum time a resultado can stay "processando" before being considered
#: stuck. InfoSimples API calls time out at 240s with 3 retries = ~12 min worst
#: case, so this threshold is deliberately LONGER than the slowest legitimate
#: run — that is what makes the sweep safe to fire at any moment rather than
#: only at boot.
STALE_PROCESSANDO_SECONDS = 15 * 60


# --------------- Paging (PostgREST's 1 000-row cap) ---------------


def _all_rows(fetch_page, label: str) -> list[dict]:
    """Every row of an UNBOUNDED read, paged past PostgREST's row cap.

    `app.services.table_reads.paged_rows` is the canonical helper and is what
    the org-scoped reads here use indirectly — but it requires an `org_id`, and
    the two recovery sweeps below are deliberately cross-org (they run from a
    scheduler that has no caller and no org). This is that same pager with the
    org filter left to the caller's `fetch_page`.
    """
    return list(iter_paged_rows(fetch_page, id_key="id", label=label))


def in_batches(items: list[str], size: int = 200):
    """Yield `items` in chunks — PostgREST rides `.in_()` values in the URL
    query string, so an unbatched ~1 000-item list comes back as a bare 400
    with no hint that length was the problem.
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------- Core Processing ---------------


async def _fetch_certidao(
    config: dict,
    consulta: dict,
    token: str,
    client: httpx.AsyncClient,
) -> dict:
    """Call InfoSimples API for a single certificate type, with retry logic.

    Retries up to MAX_RETRIES times on transient failures (timeouts, network
    errors, server errors). Returns dict with keys: success, file_url,
    raw_response, error.
    """
    builder = PARAM_BUILDERS[config["params_fn"]]
    params = builder(consulta, token)
    url = f"{INFOSIMPLES_BASE_URL}/{config['endpoint']}"
    timeout = config.get("timeout", DEFAULT_TIMEOUT)

    last_error = "Erro desconhecido"
    last_raw = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params, timeout=timeout)
            data = resp.json()

            api_code = data.get("code")

            if api_code == 200 and data.get("data"):
                # Most endpoints: file URL is in data[0].site_receipt
                # CENPROT: file URL is in root-level site_receipts[0]
                site_receipt = data["data"][0].get("site_receipt", "")
                if not site_receipt:
                    site_receipts = data.get("site_receipts") or []
                    site_receipt = site_receipts[0] if site_receipts else ""
                return {
                    "success": True,
                    "file_url": site_receipt,
                    "raw_response": data,
                    "error": None,
                }

            # Code 612 = "no data at source" — for certidões this means
            # nada consta (no debts/protests/issues found), which is a valid result.
            if api_code == 612:
                detail = (data.get("errors", []) or ["Nada consta"])[0]
                return {
                    "success": True,
                    "file_url": None,
                    "raw_response": data,
                    "error": None,
                    "nada_consta": detail,
                }

            # Extract error — prefer specific fields (errors[], code_message)
            # over the generic message field which is often uninformative.
            last_raw = data
            errors_list = data.get("errors") or []
            specific_error = (
                (errors_list[0] if errors_list else None)
                or data.get("code_message")
            )
            generic_error = data.get("message")
            # Combine: show specific error first, append generic if different
            if specific_error and generic_error and specific_error != generic_error:
                last_error = f"{specific_error} ({generic_error})"
            else:
                last_error = (
                    specific_error
                    or generic_error
                    or f"Erro na consulta (code: {data.get('code', 'unknown')})"
                )

            # Don't retry on definitive API errors (bad params, auth, etc.)
            if isinstance(api_code, int) and 400 <= api_code < 500:
                break

            logger.warning(
                "InfoSimples %s attempt %d/%d failed: %s",
                config["tipo"], attempt, MAX_RETRIES, last_error,
            )

        except Exception as e:
            last_error = str(e)
            last_raw = None
            logger.warning(
                "InfoSimples %s attempt %d/%d exception: %s",
                config["tipo"], attempt, MAX_RETRIES, e,
            )

        # Wait before retrying (exponential: 2s, 4s)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(2 ** attempt)

    logger.error(
        "InfoSimples %s failed after %d attempts: %s",
        config["tipo"], MAX_RETRIES, last_error,
    )
    return {
        "success": False,
        "file_url": None,
        "raw_response": last_raw,
        "error": last_error,
    }


async def _download_file(
    url: str, client: httpx.AsyncClient
) -> Optional[tuple[bytes, str]]:
    """Download a file from a URL. Returns (content_bytes, content_type) or None."""
    try:
        resp = await client.get(url, timeout=60.0, follow_redirects=True)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "application/octet-stream")
            logger.info(
                "Downloaded %s: content-type=%s, size=%d, first_bytes=%r",
                url[:80], ct, len(resp.content), resp.content[:20],
            )
            return resp.content, ct
        logger.warning("File download failed with status %d for %s", resp.status_code, url)
        return None
    except Exception as e:
        logger.error("File download error: %s", e)
        return None


def _convert_html_to_pdf(html_bytes: bytes) -> Optional[bytes]:
    """Convert HTML content to PDF using xhtml2pdf."""
    try:
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.BytesIO(html_bytes), dest=pdf_buffer)
        if pisa_status.err:
            logger.error("xhtml2pdf conversion error count: %d", pisa_status.err)
            return None
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.error("HTML→PDF conversion failed: %s", e)
        return None


# --------------- Storage ---------------


def storage_key(org_id: str, consulta_id: str, tipo: str) -> str:
    """The bucket key for one stored certidão PDF.

    🔴 The `org_id` MUST be the FIRST path segment — this bucket's object-RLS
    policies (migration 057) match on it, so a key shaped any other way is
    readable across orgs.

    Keyed on `consulta_id` rather than on the person's NAME (which is what the
    ERP used as its subfolder). A name is not unique, contains spaces and
    accents, and can be edited after the fact — none of which a storage key
    survives well. The consulta id is stable and is what every read already
    has in hand.

    The random suffix keeps a re-issue (reprocess, manual upload) from
    overwriting the previous file: `put` overwrites, and a certidão that was
    superseded still has to be produceable, because it is what an earlier step
    of the deal was decided against.
    """
    return f"{org_id}/{PREFIXO}/{consulta_id}/{tipo}_{uuid.uuid4().hex[:8]}.pdf"


def is_storage_key(value: Optional[str]) -> bool:
    """Is `value` one of our bucket keys rather than an external URL?

    `arquivo_url` holds EITHER — see `_persist_pdf`. Everything we write is a
    key; anything with a scheme came from the source system.
    """
    return bool(value) and "://" not in value


async def _persist_pdf(
    pdf_bytes: bytes,
    storage: StorageBackend,
    org_id: Optional[str],
    consulta_id: str,
    tipo: str,
) -> Optional[str]:
    """Put the PDF in the bucket. Returns the KEY, or None when it could not.

    🔴 THE KEY, NOT A URL — and that is the one deliberate contract change from
    the ERP.

    ERP stored a permanent PUBLIC url. This product's bucket is private and its
    reads are minted as short-TTL signed URLs (`documento_store.
    SIGNED_URL_TTL_SECONDS` is 300 seconds). Storing a signed URL in a column
    that outlives it by months would mean every certidão silently becomes an
    un-downloadable dead link a few minutes after it is issued — and re-minting
    one per resultado on every read is 10 storage round-trips on a detail
    endpoint the frontend polls every 3 seconds.

    So the column holds the key, and the two routes that actually need bytes
    (`/download`, `/download-zip`) read them straight through this seam. No URL
    to expire, no per-poll minting, and the delete path gets the key for free
    instead of parsing it back out of a URL the way ERP had to.

    `None` on failure is a REPORTED outcome, not a swallowed one: the caller
    keeps the upstream `file_url` in `arquivo_url` so the certidão is still
    reachable while InfoSimples keeps it alive, and the failure is logged at
    error.
    """
    if not org_id:
        logger.warning(
            "certidoes: no org_id for consulta %s — skipping storage upload; "
            "arquivo_url will keep the upstream URL",
            consulta_id,
        )
        return None
    key = storage_key(org_id, consulta_id, tipo)
    try:
        await storage.put(
            bucket=BUCKET,
            key=key,
            data=pdf_bytes,
            content_type="application/pdf",
            metadata={"tipo": tipo, "consulta_id": consulta_id},
        )
        return key
    except Exception as e:
        logger.error("certidoes: storage upload failed for %s: %s", key, e)
        return None


async def read_certidao_bytes(
    arquivo_url: str,
    storage: StorageBackend,
    http_client: httpx.AsyncClient,
) -> Optional[bytes]:
    """The bytes behind one `arquivo_url`, whichever kind it is.

    A bucket key is read through the storage seam; an `https://` URL is fetched
    over HTTP (the source system still hosts it — this is the fallback path for
    a certidão whose upload failed). `None` when neither produced bytes; every
    caller treats that as "skip this file" and says so.
    """
    if is_storage_key(arquivo_url):
        try:
            blob = await storage.get(bucket=BUCKET, key=arquivo_url)
        except Exception as e:
            logger.warning("certidoes: storage read failed for %s: %s", arquivo_url, e)
            return None
        if blob is None:
            logger.warning("certidoes: no blob at key %s", arquivo_url)
            return None
        return blob.data
    downloaded = await _download_file(arquivo_url, http_client)
    return downloaded[0] if downloaded else None


async def delete_storage_files(
    resultados: list[dict], storage: StorageBackend
) -> int:
    """Delete every stored file behind a list of resultados. Returns the count.

    Replaces ERP's `_delete_storage_files`, which parsed the bucket path back
    out of a public URL and then bypassed its own StorageService to dodge a
    dry-run fallback. Neither half is needed here: the column already holds the
    key, and the seam deletes for real.
    """
    keys = [
        r["arquivo_url"]
        for r in resultados
        if is_storage_key(r.get("arquivo_url"))
    ]
    if not keys:
        logger.info("certidoes: no stored files to delete for this consulta")
        return 0

    deleted = 0
    for key in keys:
        try:
            # `delete` returns False for an already-absent key and never raises
            # 404 — an already-gone file is not an error, it is the goal.
            await storage.delete(bucket=BUCKET, key=key)
            deleted += 1
        except Exception as e:
            # Logged, not raised: the DB rows must still go. A blob we failed
            # to remove is an orphan in the bucket; a row we failed to remove
            # is a certidão the user asked us to forget and still sees.
            logger.error("certidoes: failed to delete storage key %s: %s", key, e)
    logger.info("certidoes: deleted %d/%d storage files", deleted, len(keys))
    return deleted


# --------------- AI analysis ---------------


async def _analyze_with_ai(text: str, org_id: Optional[str] = None) -> Optional[str]:
    """Send document text/summary to the seed `chat_completion` wrapper.

    Returns a user-facing marker string if the OpenAI key is not configured —
    AI analysis is optional, the certificate itself is still valid without it,
    and a Portuguese sentence in the column is what tells the operator WHY the
    analysis box is empty. The pre-flight credential check exists for exactly
    that: without it the call raises `LLMNotConfigured` and the operator sees a
    stack-trace-shaped error on a certidão that actually succeeded.
    """
    api_key = resolve_key(OPENAI_API_KEY, org_id)
    if not api_key:
        logger.warning("AI analysis skipped — openai_api_key not configured")
        return (
            "[Análise IA não disponível — OpenAI API Key não configurada. "
            "Configure em Configurações → Chaves de API]"
        )

    try:
        return await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista jurídico. Analise o conteúdo desta certidão "
                        "e forneça um resumo claro da situação da pessoa/empresa mencionada. "
                        "Foque em: existência de débitos, pendências, restrições ou se está tudo regular. "
                        "Responda em português."
                    ),
                },
                {"role": "user", "content": text},
            ],
            model="gpt-4.1-mini",
            org_id=org_id,
            max_tokens=1000,
        )
    except Exception as e:
        logger.error("AI analysis failed: %s", e)
        return f"[Erro na análise IA: {e}]"


async def _extract_pdf_text(
    pdf_bytes: bytes, nome_display: str, org_id: Optional[str] = None
) -> Optional[str]:
    """Extract text content from a certidão PDF for AI analysis.

    Goes through the seed transcriber (`documents.make_document_transcriber`)
    rather than a bare `get_text()` sweep, so a scanned certidão — whose text
    layer is a digital-signature stamp, not content — is not handed to
    `_analyze_with_ai` as if it were the document.

    `max_vision_pages=0` keeps this path on the free, exact half of the ladder.
    Certidões arrive here from a background scheduler that runs per org on a
    timer, so switching rung 2 on would start billing vision calls on a loop
    nobody is watching. Raise it (or drop the argument for the seed default of
    40) to transcribe scanned certidões too — that is a cost decision, not a
    technical blocker.

    Returns None when nothing trustworthy is there, which the caller already
    treats as "no analysis". The `vision_disabled` case is logged rather than
    silently dropped: a scanned certidão getting no AI analysis is a real gap
    and should be visible in the logs, not inferred from an empty column.
    """
    try:
        from noctusai_lib.integrations.documents import make_document_transcriber

        transcriber = make_document_transcriber(
            real=True, org_id=org_id, max_vision_pages=0
        )
        resultado = await transcriber.transcribe(
            pdf_bytes, mimetype="application/pdf"
        )
        if resultado.error == "vision_disabled":
            logger.info(
                "Certidão %s: %s — analysing the %d page(s) with a real text layer",
                nome_display, resultado.error_message, len(resultado.pages),
            )
        elif not resultado.ok:
            logger.warning(
                "Certidão %s: transcription failed (%s) %s",
                nome_display, resultado.error, resultado.error_message or "",
            )

        extracted = resultado.text
        if not extracted:
            return None
        # Prefix with certificate type for context (mirrors how the automated
        # flow sends structured API response data). Truncate to avoid exceeding
        # token limits.
        return f"Certidão: {nome_display}\n\n{extracted[:4000]}"
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return None


# --------------- One certificate ---------------


async def _process_single_certidao(
    config: dict,
    consulta: dict,
    infosimples_token: str,
    db,
    resultado_id: str,
    http_client: httpx.AsyncClient,
    storage: StorageBackend,
) -> None:
    """Process a single certificate: fetch → download → store → analyze → update.

    Updates the parent consulta's progress (concluidas count) after each
    certificate finishes so the frontend progress bar updates in real-time.
    """
    consulta_id = consulta["id"]
    org_id = consulta.get("org_id")

    # Update status to processando and record when the API call is about to
    # happen. api_requested_at survives status resets (reprocessing) so the
    # TJSP cooldown is always enforced — even after a resultado is reset from
    # "erro" to "na_fila".
    db.table(RESULTADOS).update({
        "status": "processando",
        "api_requested_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", resultado_id).execute()

    # Fetch from InfoSimples
    result = await _fetch_certidao(config, consulta, infosimples_token, http_client)

    if not result["success"]:
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": result["error"],
            "api_response": result["raw_response"],
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    # "Nada consta" result (e.g., no protests found) — success without PDF
    if result.get("nada_consta"):
        db.table(RESULTADOS).update({
            "status": "sucesso",
            "analise_ia": result["nada_consta"],
            "api_response": result["raw_response"],
            "erro_mensagem": None,
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    file_url = result["file_url"]
    arquivo_url = file_url
    is_html = config["response_format"] == "html"

    # Download the document and persist it to our own bucket so we don't depend
    # on InfoSimples keeping the site_receipt URL alive.
    if file_url:
        download_result = await _download_file(file_url, http_client)
        if download_result:
            raw_bytes, content_type = download_result
            already_pdf = raw_bytes[:5] == b"%PDF-"

            if already_pdf:
                # Content is already a valid PDF — use as-is
                pdf_bytes = raw_bytes
            elif is_html or "text/html" in content_type:
                # HTML content (either from config or detected via content-type)
                # → convert to PDF
                pdf_bytes = _convert_html_to_pdf(raw_bytes)
                if not pdf_bytes:
                    logger.warning(
                        "HTML→PDF conversion failed for %s, keeping original URL",
                        config["tipo"],
                    )
            elif "application/pdf" in content_type:
                # Server says it's a PDF but missing magic bytes — trust the server
                pdf_bytes = raw_bytes
            else:
                # Unknown content type — not a PDF, not HTML. Skip storage.
                logger.warning(
                    "Unexpected content-type %s for %s (first bytes: %r), keeping original URL",
                    content_type, config["tipo"], raw_bytes[:20],
                )
                pdf_bytes = None

            if pdf_bytes:
                stored_key = await _persist_pdf(
                    pdf_bytes, storage, org_id, consulta_id, config["tipo"]
                )
                if stored_key:
                    arquivo_url = stored_key
        else:
            logger.warning(
                "Failed to download file for %s from %s, keeping original URL",
                config["tipo"], file_url,
            )

    # AI analysis (use raw response summary as text input)
    analise = None
    raw = result["raw_response"]
    if raw and raw.get("data"):
        summary_parts = []
        for item in raw["data"]:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k != "site_receipt" and v:
                        summary_parts.append(f"{k}: {v}")
        if summary_parts:
            text_for_analysis = "\n".join(summary_parts)
            analise = await _analyze_with_ai(text_for_analysis, org_id)

    # Update resultado — always store as .pdf
    update_data = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{config['tipo']}.pdf",
        "analise_ia": analise,
        "api_response": result["raw_response"],
        "erro_mensagem": None,
    }
    db.table(RESULTADOS).update(update_data).eq("id", resultado_id).execute()
    _atualizar_status_consulta(consulta_id, org_id, db)


def _atualizar_status_consulta(consulta_id: str, org_id: Optional[str], db) -> None:
    """Recalculate and update the consulta's progress and status.

    Called after each certificate finishes (success or error) so the frontend
    progress bar updates in real-time. Also called by the TJSP queue worker
    after processing queued items.

    Status logic:
    - Any resultado still pending/processing/queued → "processando"
    - All done, at least one success → "concluida"
    - All done, zero successes → "erro"
    """
    query = db.table(RESULTADOS).select("status").eq("consulta_id", consulta_id)
    if org_id:
        query = query.eq("org_id", str(org_id))
    rows = query.execute().data or []

    sucessos = sum(1 for r in rows if r["status"] == "sucesso")
    erros = sum(1 for r in rows if r["status"] == "erro")
    still_pending = sum(
        1 for r in rows if r["status"] in ("pendente", "processando", "na_fila")
    )

    if still_pending > 0:
        final_status = "processando"
    elif sucessos == 0 and erros > 0:
        final_status = "erro"
    else:
        final_status = "concluida"

    db.table(CONSULTAS).update({
        "status": final_status,
        "concluidas": sucessos,
    }).eq("id", consulta_id).execute()


# --------------- One consulta ---------------


async def processar_consulta(consulta_id: str, db, storage: StorageBackend) -> None:
    """Process all certificates for a consulta (runs in background).

    All certificates are processed in parallel. TJSP is included if the
    cooldown has passed; otherwise it's queued ("na_fila") for the on-demand
    scheduler. A premature TJSP request RESETS the API counter, so we never
    fire before the cooldown expires.
    """
    consulta_result = db.table(CONSULTAS).select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data
    if not consulta:
        logger.error("certidoes: consulta %s not found — nothing to process", consulta_id)
        return
    org_id = consulta.get("org_id")

    db.table(CONSULTAS).update({
        "status": "processando",
    }).eq("id", consulta_id).execute()

    # postgrest-unbounded-ok: one resultado per registry type per consulta
    # (exactly `len(CERTIDOES_CONFIG)`, 10 today) — 10 rows, not 1 000.
    resultados_result = db.table(RESULTADOS).select("*").eq(
        "consulta_id", consulta_id
    ).order("ordem").execute()
    resultados = resultados_result.data or []

    # Validate InfoSimples token — required for certificate issuance
    infosimples_token = _get_infosimples_token(org_id)
    if not infosimples_token:
        error_msg = (
            "Token InfoSimples não configurado. "
            "Configure em Configurações → Chaves de API."
        )
        logger.error("InfoSimples token missing for consulta %s", consulta_id)
        resultado_ids = [r["id"] for r in resultados]
        for batch in in_batches(resultado_ids):
            db.table(RESULTADOS).update({
                "status": "erro",
                "erro_mensagem": error_msg,
            }).in_("id", batch).execute()
        db.table(CONSULTAS).update({
            "status": "erro",
            "concluidas": 0,
        }).eq("id", consulta_id).execute()
        return

    # Only process resultados that are pending (skip already succeeded ones)
    pending = [r for r in resultados if r["status"] == "pendente"]

    tjsp_pending = [r for r in pending if r["tipo"] == TJSP_TIPO]
    non_tjsp_pending = [r for r in pending if r["tipo"] != TJSP_TIPO]

    # Check TJSP cooldown — if clear, process in parallel; otherwise queue
    tjsp_can_run = False
    if tjsp_pending:
        last_at = _get_tjsp_last_request_at(org_id, db) if org_id else None
        if last_at:
            elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
            tjsp_can_run = elapsed >= TJSP_COOLDOWN_SECONDS
            if not tjsp_can_run:
                remaining = TJSP_COOLDOWN_SECONDS - elapsed
                logger.info(
                    "TJSP cooldown active for org %s, %.0fs remaining — queuing",
                    org_id, remaining,
                )
        else:
            # No previous TJSP request — safe to run immediately
            tjsp_can_run = True

    async with httpx.AsyncClient() as http_client:
        tasks = []
        for r in non_tjsp_pending:
            config = config_for(r["tipo"])
            if not config:
                logger.warning(
                    "certidoes: resultado %s has tipo %r which is not in the "
                    "registry — skipping (the row stays 'pendente')",
                    r["id"], r["tipo"],
                )
                continue
            tasks.append(
                _process_single_certidao(
                    config, consulta, infosimples_token, db, r["id"],
                    http_client, storage,
                )
            )
        if tjsp_can_run:
            for r in tjsp_pending:
                config = config_for(r["tipo"])
                if config:
                    tasks.append(
                        _process_single_certidao(
                            config, consulta, infosimples_token, db, r["id"],
                            http_client, storage,
                        )
                    )
                    logger.info(
                        "TJSP resultado %s processing immediately (cooldown clear)",
                        r["id"],
                    )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Certificate processing failed: %s", result)

    # Queue TJSP items that couldn't run due to cooldown, and schedule the
    # deferred processing
    if not tjsp_can_run and tjsp_pending:
        tjsp_ids = [r["id"] for r in tjsp_pending]
        for batch in in_batches(tjsp_ids):
            db.table(RESULTADOS).update({
                "status": "na_fila",
            }).in_("id", batch).execute()
        for r in tjsp_pending:
            logger.info("TJSP resultado %s queued (na_fila) — cooldown active", r["id"])
        if org_id:
            schedule_tjsp_for_org(org_id, db, storage)

    _atualizar_status_consulta(consulta_id, org_id, db)


# --------------- Recovery ---------------


def recover_stale_processando(db) -> int:
    """Detect and recover resultados stuck in 'processando' for too long.

    Called on every list fetch (throttled) so the frontend never loops forever
    on stuck items. Uses `api_requested_at` (set right before the API call in
    `_process_single_certidao`) to determine staleness — NOT `updated_at`,
    which may reflect the original creation time.

    Only recovers items whose `api_requested_at` is older than the threshold.
    Items in 'processando' WITHOUT an `api_requested_at` are waiting to start
    and are handled by `recover_stuck_processando`.

    Returns the number of recovered items.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSANDO_SECONDS)
    ).isoformat()

    # Fetch all "processando" items, then filter in Python for stale ones. We
    # can't use `.lt("api_requested_at", cutoff)` directly because items
    # without api_requested_at (NULL) would be silently included or excluded
    # depending on the PostgREST version.
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, tipo, consulta_id, org_id, api_requested_at")
            .eq("status", "processando")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    stuck = _all_rows(_page, "certidao_resultados processando")

    stale = [
        item for item in stuck
        if item.get("api_requested_at") and item["api_requested_at"] < cutoff
    ]

    if not stale:
        return 0

    logger.warning(
        "Auto-recovering %d stale 'processando' items (>%ds old)",
        len(stale), STALE_PROCESSANDO_SECONDS,
    )

    stale_ids = [item["id"] for item in stale]
    for batch in in_batches(stale_ids):
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": (
                "Processamento expirou — a automação foi interrompida. "
                "Tente reprocessar ou faça upload manual."
            ),
        }).in_("id", batch).execute()

    consultas: dict[str, Optional[str]] = {}
    for item in stale:
        consultas[item["consulta_id"]] = item.get("org_id")
        logger.info(
            "Auto-recovered stale resultado %s (api_requested_at=%s) → erro",
            item["id"], item["api_requested_at"],
        )

    for cid, oid in consultas.items():
        _atualizar_status_consulta(cid, oid, db)

    return len(stale)


def recover_stuck_processando(db) -> None:
    """Reset orphaned "processando" items left by killed background tasks.

    Non-TJSP items go back to "pendente", TJSP items go back to "na_fila" so
    they are picked up by `schedule_all_pending_tjsp`.

    🔴 UNCONDITIONAL — it resets EVERY 'processando' row, including one a live
    task in this very process is working on. That is correct exactly once, at
    process START, when by definition no task of ours is running yet, and it is
    why the periodic sweep in `scheduler.py` calls `recover_stale_processando`
    (which has a 15-minute floor) instead of this one. See that module for the
    boot-time wiring.
    """
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, tipo, consulta_id, org_id")
            .eq("status", "processando")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    items = _all_rows(_page, "certidao_resultados processando (startup)")
    if not items:
        return

    logger.warning("Recovering %d stuck 'processando' items on startup", len(items))

    tjsp_ids = [item["id"] for item in items if item["tipo"] == TJSP_TIPO]
    non_tjsp_ids = [item["id"] for item in items if item["tipo"] != TJSP_TIPO]

    for batch in in_batches(non_tjsp_ids):
        db.table(RESULTADOS).update({
            "status": "pendente",
            "erro_mensagem": None,
        }).in_("id", batch).execute()

    for batch in in_batches(tjsp_ids):
        db.table(RESULTADOS).update({
            "status": "na_fila",
            "erro_mensagem": None,
        }).in_("id", batch).execute()

    consultas: dict[str, Optional[str]] = {
        item["consulta_id"]: item.get("org_id") for item in items
    }
    for cid, oid in consultas.items():
        _atualizar_status_consulta(cid, oid, db)


def cancelar_processamento(consulta_id: str, org_id: Optional[str], db) -> dict:
    """Cancel in-progress certificate processing for one consulta.

    Resets every resultado of the consulta that is pendente/processando/na_fila
    to 'erro' with a cancellation message, and cancels any scheduled TJSP task
    for the affected orgs.

    Returns counts of cancelled items.
    """
    query = db.table(RESULTADOS).select("id, tipo, org_id").eq(
        "consulta_id", consulta_id
    ).in_("status", ["pendente", "processando", "na_fila"])
    if org_id:
        query = query.eq("org_id", str(org_id))
    items = query.execute().data or []
    if not items:
        return {"cancelados": 0}

    item_ids = [item["id"] for item in items]
    for batch in in_batches(item_ids):
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": "Cancelado manualmente pelo usuário.",
        }).in_("id", batch).execute()

    org_ids = set(item.get("org_id") for item in items if item.get("org_id"))
    for oid in org_ids:
        task = _tjsp_scheduled_tasks.pop(oid, None)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled scheduled TJSP task for org %s", oid)

    _atualizar_status_consulta(consulta_id, org_id, db)

    logger.info(
        "Cancelled %d in-progress resultados for consulta %s", len(items), consulta_id
    )
    return {"cancelados": len(items)}


# --------------- Credentials ---------------


def _get_infosimples_token(org_id: Optional[str] = None) -> Optional[str]:
    """Resolve the InfoSimples token via this module's credential seam."""
    return resolve_key(INFOSIMPLES_TOKEN, org_id)


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Which required credentials are missing for certificate issuance.

    Returns a list of human-readable messages, one per missing credential; an
    empty list means everything is configured.
    """
    missing = []
    if not resolve_key(INFOSIMPLES_TOKEN, org_id):
        missing.append(
            "Token InfoSimples não configurado — necessário para emissão de certidões."
        )
    return missing


# --------------- Manual upload ---------------


async def process_manual_upload(
    pdf_bytes: bytes,
    resultado_id: str,
    consulta: dict,
    tipo: str,
    nome_display: str,
    org_id: Optional[str],
    db,
    storage: StorageBackend,
) -> dict:
    """Run a manually uploaded certificate PDF through the SAME pipeline as the
    automated flow (the post-download steps of `_process_single_certidao`).

    1. Put it in the bucket (same key shape)
    2. Extract text for AI analysis
    3. Run AI analysis on the extracted text
    4. Update resultado → sucesso
    5. Recalculate consulta status

    Returns the update_data dict applied to the resultado.
    """
    consulta_id = consulta["id"]

    # Mark as processando (same as automated flow)
    db.table(RESULTADOS).update({
        "status": "processando",
    }).eq("id", resultado_id).execute()

    # 1. Storage — same key shape as `_process_single_certidao`
    arquivo_url = await _persist_pdf(pdf_bytes, storage, org_id, consulta_id, tipo)

    # 2. Extract text for AI analysis (replaces the API response data the
    #    automated flow uses as input for `_analyze_with_ai`)
    text_for_analysis = await _extract_pdf_text(pdf_bytes, nome_display, org_id)

    # 3. AI analysis — same function as automated flow
    analise = None
    if text_for_analysis:
        analise = await _analyze_with_ai(text_for_analysis, org_id)

    # 4. Update resultado → sucesso (same fields as automated flow)
    update_data: dict = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{tipo}.pdf",
        "analise_ia": analise,
        "api_response": None,
        "erro_mensagem": None,
    }
    db.table(RESULTADOS).update(update_data).eq("id", resultado_id).execute()

    # 5. Recalculate consulta status — same function as automated flow
    _atualizar_status_consulta(consulta_id, org_id, db)

    return update_data


# --------------- TJSP On-Demand Scheduler ---------------
#
# Instead of polling every N seconds, TJSP items are scheduled to fire at the
# exact moment the cooldown expires. Each org has at most one scheduled task.
# After processing, the task chains the next queued item (if any) with a fresh
# cooldown delay.

#: One scheduled asyncio.Task per org — prevents double-scheduling and holds a
#: strong reference so the task isn't garbage-collected.
_tjsp_scheduled_tasks: dict[str, "asyncio.Task"] = {}


def _get_tjsp_last_request_at(org_id: str, db) -> Optional[datetime]:
    """When the last TJSP API request was made for an org.

    Uses the dedicated `api_requested_at` column, which is set right before
    calling the InfoSimples API and is NEVER cleared on reprocessing. That is
    what keeps the cooldown enforced even after a resultado is reset from
    "erro" to "na_fila" for retry.

    Fetches recent TJSP resultados and filters NULLs in Python rather than
    relying on supabase-py's `.not_.is_()` filter, which can silently return
    NULL rows depending on the client version.
    """
    result = db.table(RESULTADOS).select(
        "id, api_requested_at"
    ).eq("tipo", TJSP_TIPO).eq("org_id", str(org_id)).order(
        "created_at", desc=True
    ).limit(10).execute()

    for row in (result.data or []):
        ts_str = row.get("api_requested_at")
        if not ts_str:
            continue
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            logger.warning(
                "certidoes: resultado id=%s has unparseable api_requested_at=%r (%s); "
                "skipping when computing TJSP cooldown",
                row.get("id"), ts_str, exc,
            )
            continue
    return None


def _get_tjsp_remaining_cooldown(org_id: str, db) -> float:
    """Seconds remaining on the TJSP cooldown for an org. 0.0 when clear."""
    last_at = _get_tjsp_last_request_at(org_id, db)
    if not last_at:
        logger.info(
            "TJSP cooldown: no previous api_requested_at found for org %s", org_id
        )
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    remaining = max(0.0, TJSP_COOLDOWN_SECONDS - elapsed)
    logger.info(
        "TJSP cooldown for org %s: last_at=%s, elapsed=%.0fs, remaining=%.0fs",
        org_id, last_at.isoformat(), elapsed, remaining,
    )
    return remaining


async def _process_single_tjsp_item(
    resultado: dict, db, storage: StorageBackend
) -> None:
    """Process one queued TJSP resultado: fetch its consulta, call InfoSimples."""
    consulta_id = resultado["consulta_id"]
    org_id = resultado.get("org_id")

    consulta_result = db.table(CONSULTAS).select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data
    if not consulta:
        logger.error(
            "TJSP queue: consulta %s not found for resultado %s",
            consulta_id, resultado["id"],
        )
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": "Consulta não encontrada",
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    infosimples_token = _get_infosimples_token(org_id)
    if not infosimples_token:
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": (
                "Token InfoSimples não configurado. "
                "Configure em Configurações → Chaves de API."
            ),
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    config = config_for(TJSP_TIPO)
    if not config:
        logger.error(
            "TJSP queue: %r is not in CERTIDOES_CONFIG — resultado %s left queued",
            TJSP_TIPO, resultado["id"],
        )
        return

    async with httpx.AsyncClient() as http_client:
        await _process_single_certidao(
            config, consulta, infosimples_token, db, resultado["id"],
            http_client, storage,
        )

    _atualizar_status_consulta(consulta_id, org_id, db)


async def _delayed_tjsp_process(
    delay: float, resultado: dict, org_id: str, db, storage: StorageBackend
) -> None:
    """Sleep out the remaining cooldown, process one TJSP item, chain the next.

    Runs as a one-shot asyncio.Task in the main event loop. After completion
    (success or failure), checks for more queued items for the same org and
    schedules the next one with a fresh cooldown delay.

    On CancelledError (server shutdown / --reload) it does NOT reschedule — the
    new process's startup recovery handles that.
    """
    resultado_id = resultado["id"]
    cancelled = False
    sleep_start = datetime.now(timezone.utc)
    try:
        if delay > 0:
            logger.info(
                "TJSP sleep START: resultado %s, delay=%.0fs (org %s)",
                resultado_id, delay, org_id,
            )
            await asyncio.sleep(delay)
            actual = (datetime.now(timezone.utc) - sleep_start).total_seconds()
            logger.info(
                "TJSP sleep END: resultado %s, slept=%.0fs of %.0fs (org %s)",
                resultado_id, actual, delay, org_id,
            )

        # Verify the item is still queued (it may have been deleted, cancelled
        # or reprocessed while we slept)
        check = db.table(RESULTADOS).select("status").eq(
            "id", resultado_id
        ).execute()
        if not check.data or check.data[0]["status"] != "na_fila":
            logger.info("TJSP resultado %s no longer na_fila, skipping", resultado_id)
            return

        logger.info("TJSP processing: resultado %s (org %s)", resultado_id, org_id)
        await _process_single_tjsp_item(resultado, db, storage)

    except asyncio.CancelledError:
        cancelled = True
        actual = (datetime.now(timezone.utc) - sleep_start).total_seconds()
        logger.info(
            "TJSP task CANCELLED for resultado %s after %.0fs of %.0fs sleep (org %s)",
            resultado_id, actual, delay, org_id,
        )
        raise
    except Exception as e:
        logger.error("TJSP processing failed for %s: %s", resultado_id, e)
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": f"Erro no processamento: {e}",
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(
            resultado["consulta_id"], resultado.get("org_id"), db
        )
    finally:
        _tjsp_scheduled_tasks.pop(org_id, None)
        # Only reschedule on normal completion or handled errors — NOT on
        # CancelledError (server shutdown). The new process's startup recovery
        # calls schedule_all_pending_tjsp, which handles rescheduling.
        if not cancelled:
            schedule_tjsp_for_org(org_id, db, storage)


def schedule_tjsp_for_org(org_id: str, db, storage: StorageBackend) -> None:
    """Schedule the next queued TJSP item for an org.

    Idempotent: if a task is already in flight for this org, does nothing.
    Calculates the exact delay from `api_requested_at` so the item fires
    precisely when the cooldown expires — no polling.
    """
    existing = _tjsp_scheduled_tasks.get(org_id)
    if existing and not existing.done():
        return  # Already scheduled

    queued = db.table(RESULTADOS).select(
        "id, consulta_id, org_id"
    ).eq("tipo", TJSP_TIPO).eq("status", "na_fila").eq(
        "org_id", str(org_id)
    ).order("created_at").limit(1).execute()

    items = queued.data or []
    if not items:
        return

    remaining = _get_tjsp_remaining_cooldown(org_id, db)
    task = schedule_coro(
        _delayed_tjsp_process(remaining, items[0], org_id, db, storage),
        logger=logger,
        name=f"tjsp_{org_id}",
    )
    _tjsp_scheduled_tasks[org_id] = task
    logger.info(
        "TJSP task scheduled for org %s: resultado %s in %.0fs",
        org_id, items[0]["id"], remaining,
    )


def schedule_all_pending_tjsp(db, storage: StorageBackend) -> None:
    """Scan for every queued TJSP item and schedule one task per org.

    Called after `recover_stuck_processando` to resume items that were waiting
    before the process restarted.
    """
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, org_id")
            .eq("tipo", TJSP_TIPO)
            .eq("status", "na_fila")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    queued = _all_rows(_page, "certidao_resultados na_fila (tjsp)")

    org_ids = set(item["org_id"] for item in queued if item.get("org_id"))
    if org_ids:
        logger.info("Scheduling pending TJSP items for %d org(s)", len(org_ids))
    for oid in org_ids:
        schedule_tjsp_for_org(oid, db, storage)


def status_counts_por_consulta(
    consulta_ids: list[str], org_id: Any, db
) -> tuple[dict[str, int], dict[str, int]]:
    """`(sucessos, erros)` counts keyed by consulta_id, for a page of consultas.

    🔴 BATCHED **AND** PAGED — both hazards are live on this one read, and
    fixing only the famous one leaves the other silently wrong.

    - Batched, because PostgREST rides `.in_()` values in the URL query string,
      so a long id list comes back as a bare 400.
    - Paged, because a full page is 200 consultas and each fans out to one
      resultado per registry type (10 today) — 2 000 rows against PostgREST's
      1 000-row cap, which it applies SILENTLY and reports as success. An
      un-paged read here does not fail; it just returns counts that are wrong
      for the back half of the page, and "concluídas: 0" on a consulta that
      finished is indistinguishable from one that genuinely has not started.

    The batch size is deliberately smaller than `in_batches`' default: the id
    count is not the row count here, it is the row count divided by the
    fan-out. The pager underneath makes the read correct regardless; the
    smaller batch just keeps it to one round-trip per batch in the common case.
    """
    sucessos: dict[str, int] = {}
    erros: dict[str, int] = {}
    if not consulta_ids:
        return sucessos, erros

    for batch in in_batches(consulta_ids, size=50):

        def _page(start: int, end: int, _batch=batch):
            return (
                db.table(RESULTADOS)
                .select("id, consulta_id, status")
                .eq("org_id", str(org_id))
                .in_("consulta_id", _batch)
                .in_("status", ["sucesso", "erro"])
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        for row in _all_rows(_page, f"certidao_resultados counts for org_id={org_id}"):
            target = sucessos if row["status"] == "sucesso" else erros
            target[row["consulta_id"]] = target.get(row["consulta_id"], 0) + 1

    return sucessos, erros


def tjsp_cooldown_status(org_id: Any, db) -> dict:
    """The org's TJSP cooldown, shaped for the frontend's countdown.

    `{"ativo": False}` when this org has never made a TJSP request — which is
    a real state ("you can go now"), not a missing one, and is why it does not
    carry the other two keys.
    """
    last_at = _get_tjsp_last_request_at(str(org_id), db)
    if not last_at:
        return {"ativo": False}
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    remaining = max(0.0, TJSP_COOLDOWN_SECONDS - elapsed)
    return {
        "ativo": remaining > 0,
        "ultimo_request_at": last_at.isoformat(),
        "segundos_restantes": int(remaining),
    }


def queued_tjsp_for_org(org_id: Any, db) -> list[dict]:
    """Every `na_fila` TJSP resultado for an org, oldest first (queue order)."""
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, consulta_id, created_at")
            .eq("tipo", TJSP_TIPO)
            .eq("status", "na_fila")
            .eq("org_id", str(org_id))
            .order("created_at")
            .range(start, end)
            .execute()
            .data
        )

    return _all_rows(_page, f"certidao_resultados na_fila for org_id={org_id}")


__all__ = [
    "CERTIDOES_CONFIG",
    "CONSULTAS",
    "RESULTADOS",
    "STALE_PROCESSANDO_SECONDS",
    "TJSP_COOLDOWN_SECONDS",
    "TJSP_TIPO",
    "cancelar_processamento",
    "check_required_credentials",
    "delete_storage_files",
    "is_storage_key",
    "process_manual_upload",
    "processar_consulta",
    "in_batches",
    "queued_tjsp_for_org",
    "read_certidao_bytes",
    "recover_stale_processando",
    "recover_stuck_processando",
    "schedule_all_pending_tjsp",
    "schedule_tjsp_for_org",
    "status_counts_por_consulta",
    "storage_key",
    "tjsp_cooldown_status",
]
