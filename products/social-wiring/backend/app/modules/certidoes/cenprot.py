"""CENPROT (protest registry) manual-upload structuring — label-anchored,
self-validating against the party's own CPF/CNPJ on file.

🔴 OWNER FINDING (2026-09-30). The office's CENPROT evidence is not an
official certidão — it is a browser screenshot of the CENPROT-SP site's
result page (the whole desktop, OS taskbar included), pasted into a
single-page PDF by a converter tool. Measured against 8 real prod rows
(`social_wiring.certidao_resultados`, `tipo='cenprot'`):

- The transcript contained the "PROTOCOLO" label in 8/8, but the transcribed
  protocol differed from the contract's own número in 8/8 — 1-3 wrong digits
  in 5, 4-6 in 2, one read 8 digits short. The contract's "número" IS the
  page's own "Protocolo da Consulta" (10 digits, confirmed exactly on one
  deal).
- The page also prints "Documento Pesquisado: <CPF/CNPJ>" — the party's own
  document, confirmed against the contract's CPF in 3/8 (invalid check
  digits in the other 5 — an OCR misread, never a real CPF).
- `emitida_em` was wrong or empty in 8/8. The contract's date is nowhere
  printed on the page AS a document date — measured 2026-09-30 against 6 real
  screenshots (deals 855/863/867/875/876/897): the OS taskbar clock's own
  date, printed directly under its HH:MM time at the bottom of the desktop
  screenshot, matched the contract's `emitida_em` exactly in 6/6.

THE FIX, IN TWO LAYERS
-----------------------
1. Legibility (seed layer, `documents.transcription.cenprot_render_dpi_policy`
   + `force_vision=True`): the screenshot is this page's one embedded image,
   so `_dominant_embedded_image` re-renders JUST that region — browser
   chrome, CENPROT content, and taskbar clock together — at 600 DPI, instead
   of a whole-page raster diluted by the blank margins the converter tool
   leaves above and below it.
2. Structuring (this module): deterministic label matches on the resulting
   transcript — "Protocolo da Consulta" for `numero`, "Documento Pesquisado"
   for the searched CPF/CNPJ, and the taskbar-clock date pattern for
   `emitida_em` — the same "the label IS the source of truth" posture
   `service._aplicar_overrides_numero` (G14/G15) already takes for other
   certidão types, never a generic "guess the document's number" prompt.

SELF-VALIDATION, NOT A LEAP OF FAITH
--------------------------------------
`Documento Pesquisado` carries its own check digits (CPF/CNPJ) and must ALSO
equal the party's document on file (`certidao_consultas.documento`) — a
single independent read that passes both is trusted. `Protocolo da Consulta`
and the taskbar date carry NO check digit, so trust instead comes from
AGREEMENT between two independent reads of the same document (owner
requirement, 2026-09-30): each is kept only when both reads produce the
identical value. `estruturar_cenprot` runs the identity check FIRST — a
protocolo two reads agree on, attached to the wrong person's screenshot, is
exactly as wrong as a misread digit — so `numero`/`emitida_em` are only ever
written once `Documento Pesquisado` itself validates. Whenever a field
cannot be validated, it comes back `None` with an `aviso` explaining why —
never a guessed value: a wrong protest-certificate number in a signed
contract is worse than a gap.

🔴 PRIVACY. `avisos` NEVER carry the extracted value itself — only what
failed and how (digit counts, "diverged between reads", "check digit
invalid") — this module's own diagnostics-only-verdicts contract, and the
one this whole feature was built under (real people's CPF/protest data).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Awaitable, Callable, Optional

from noctusai_lib.integrations.documents.cnpj import is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.transcription import (
    cenprot_render_dpi_policy,
    make_document_transcriber,
)

logger = logging.getLogger(__name__)

#: "Protocolo da Consulta: 0123456789" — CENPROT-SP's own sequential
#: consulta counter, printed once, near the top of the page. No check digit
#: (see module docstring for why two independent reads stand in for one).
#: Tolerant of stray punctuation/whitespace an OCR pass sometimes inserts
#: between digits, never of a shorter/longer run — `re.sub(r"\D", ...)`
#: below collapses whatever separators survive.
_PROTOCOLO_RE = re.compile(
    r"Protocolo\s+da\s+Consulta\s*[:\-]?\s*([0-9][0-9.\- ]{7,}[0-9])",
    re.IGNORECASE,
)

#: "Documento Pesquisado: 123.456.789-09" (CPF) or a CNPJ-shaped run.
_DOCUMENTO_RE = re.compile(
    r"Documento\s+Pesquisado\s*[:\-]?\s*([0-9][0-9.\-/ ]{9,}[0-9])",
    re.IGNORECASE,
)

#: The OS taskbar clock prints its time directly ABOVE its own date
#: (Windows' standard system-tray clock layout) — anchoring the date match
#: to a preceding `HH:MM` is what tells it apart from any OTHER dd/mm/yyyy
#: string a future CENPROT template might add to the page body itself.
#: Confirmed 2026-09-30 against 6 real screenshots: `HH:MM` immediately
#: (modulo OCR-inserted whitespace/newline) precedes the date, in every one.
_TASKBAR_DATA_RE = re.compile(r"\d{1,2}:\d{2}\s*\n?\s*(\d{2}/\d{2}/\d{4})")

#: Fallback for a read that dropped the HH:MM but kept the date — used ONLY
#: when the anchored pattern above found nothing AND there is EXACTLY one
#: dd/mm/yyyy-shaped date anywhere in the transcript (today's CENPROT
#: template prints no other date), so an unrelated date can never be picked
#: up silently.
_DATA_SOLTA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


@dataclass(frozen=True)
class CenprotLeitura:
    """One independent read's own findings — a fact about THIS read, never
    a verdict; `estruturar_cenprot` is what reconciles two of these."""

    protocolo: Optional[str] = None  # digits only
    documento_pesquisado: Optional[str] = None  # digits only
    data: Optional[str] = None  # dd/mm/yyyy


def _extrair(texto: Optional[str]) -> CenprotLeitura:
    """Pure label-anchored parse of one transcript. Never raises — an
    unmatched label is `None`, exactly like the rest of this document
    family's overrides (`service._numero_via_codigo_controle` et al.)."""
    if not texto:
        return CenprotLeitura()

    protocolo = None
    m = _PROTOCOLO_RE.search(texto)
    if m:
        digitos = re.sub(r"\D", "", m.group(1))
        protocolo = digitos or None

    documento = None
    m = _DOCUMENTO_RE.search(texto)
    if m:
        digitos = re.sub(r"\D", "", m.group(1))
        documento = digitos or None

    data = None
    m = _TASKBAR_DATA_RE.search(texto)
    if m:
        data = m.group(1)
    else:
        achados = _DATA_SOLTA_RE.findall(texto)
        if len(achados) == 1:
            data = achados[0]

    return CenprotLeitura(
        protocolo=protocolo, documento_pesquisado=documento, data=data
    )


def _documento_com_check_digit_valido(
    documento: Optional[str], tipo_documento: Optional[str]
) -> bool:
    """Check-digit validity ALONE — party-match is `estruturar_cenprot`'s own
    job, since only it knows the expected document. Defaults to CPF when
    `tipo_documento` is missing/unrecognised: `cpf.is_valid` already refuses
    anything not exactly 11 digits, so a 14-digit CNPJ is never
    misclassified as a valid CPF by this fallback."""
    if not documento:
        return False
    if tipo_documento == "cnpj":
        return _cnpj_is_valid(documento)
    return _cpf_is_valid(documento)


def _data_iso(data_br: Optional[str]) -> Optional[str]:
    """`"17/06/2026"` → `"2026-06-17"`, or `None` for anything not a
    well-formed calendar date (guards against a digit-swap OCR artifact
    reaching a DATE column, same posture `service._is_iso_date` takes for
    the generic structured read)."""
    if not data_br:
        return None
    partes = data_br.split("/")
    if len(partes) != 3:
        return None
    dd, mm, yyyy = partes
    try:
        return date(int(yyyy), int(mm), int(dd)).isoformat()
    except ValueError:
        return None


@dataclass(frozen=True)
class CenprotEstrutura:
    """`estruturar_cenprot`'s verdict — `numero`/`emitida_em` are `None`
    whenever they could not be validated (see module docstring §
    "self-validation"), never a best-effort guess. `avisos` are PT-BR,
    diagnostics-only (never the extracted value itself) — the caller logs
    them; they are not a database column (mirrors `_mesclar_resultados_
    estruturados`'s own "aviso, never estrutura_erro" rule: this document
    WAS read successfully, it just could not all be trusted)."""

    numero: Optional[str] = None
    emitida_em: Optional[str] = None
    avisos: tuple[str, ...] = ()


def _fabricar_transcriber(org_id: Optional[str], provider: Optional[str]):
    from app.modules.certidoes.service import CERTIDAO_MANUAL_MAX_VISION_PAGES

    return make_document_transcriber(
        real=True,
        org_id=org_id,
        max_vision_pages=CERTIDAO_MANUAL_MAX_VISION_PAGES,
        provider=provider,
        render_dpi_policy=cenprot_render_dpi_policy(),
    )


async def _ler_segunda_vez_padrao(
    pdf_bytes: bytes, org_id: Optional[str], provider: Optional[str]
) -> Optional[str]:
    """The default second independent read: a FRESH high-DPI crop
    transcription (never reusing the first call's own answer) — see
    `estruturar_cenprot` for why a second read exists at all."""
    resultado = await _fabricar_transcriber(org_id, provider).transcribe(
        pdf_bytes, mimetype="application/pdf", force_vision=True
    )
    return resultado.text or None


async def estruturar_cenprot(
    texto_leitura1: Optional[str],
    pdf_bytes: bytes,
    nome_display: str,
    org_id: Optional[str],
    *,
    tipo_documento_esperado: Optional[str],
    documento_esperado: Optional[str],
    provider: Optional[str] = None,
    ler_segunda_vez: Optional[Callable[[], Awaitable[Optional[str]]]] = None,
) -> CenprotEstrutura:
    """CENPROT's own structuring step — label-anchored, two-read-validated.

    `texto_leitura1` is the transcript `process_manual_extraction` already
    produced for this resultado (via `_extract_pdf_text`, which for
    `tipo='cenprot'` already renders through `cenprot_render_dpi_policy` +
    `force_vision=True` — see that function). Reusing it here means the
    "first read" costs no extra vision call; only the SECOND independent
    read (`ler_segunda_vez`, defaulting to `_ler_segunda_vez_padrao`) does.

    Order of operations, and why: `Documento Pesquisado` is checked FIRST.
    A `numero`/`emitida_em` two reads agree on is still worthless if this
    screenshot belongs to a DIFFERENT person than the one it was filed
    under — identity comes before either agreement check.

    Never raises: `ler_segunda_vez` failing (network, quota, a malformed
    provider response) is treated as "second read produced nothing", the
    same as a genuinely blank read — `numero`/`emitida_em` come back `None`
    with an aviso, never an exception a background job would otherwise die
    on (this module's callers are background jobs; see `service.
    process_manual_extraction`'s own "never raises" contract).
    """
    leitura1 = _extrair(texto_leitura1)
    try:
        texto2 = await (ler_segunda_vez or (
            lambda: _ler_segunda_vez_padrao(pdf_bytes, org_id, provider)
        ))()
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.warning(
            "CENPROT %s: segunda leitura independente falhou: %s",
            nome_display, exc,
        )
        texto2 = None
    leitura2 = _extrair(texto2)

    avisos: list[str] = []

    documento_validado: Optional[str] = None
    esperado_digitos = only_digits(documento_esperado) if documento_esperado else None
    for leitura in (leitura1, leitura2):
        candidato = leitura.documento_pesquisado
        if not candidato:
            continue
        if not _documento_com_check_digit_valido(candidato, tipo_documento_esperado):
            continue
        if esperado_digitos and candidato != esperado_digitos:
            continue
        documento_validado = candidato
        break

    if documento_validado is None:
        avisos.append(
            "Documento Pesquisado: dígito verificador inválido ou não "
            "corresponde ao CPF/CNPJ da parte na consulta — número e data "
            "não gravados."
        )
        return CenprotEstrutura(avisos=tuple(avisos))

    numero: Optional[str] = None
    if leitura1.protocolo and leitura1.protocolo == leitura2.protocolo:
        numero = leitura1.protocolo
    elif leitura1.protocolo or leitura2.protocolo:
        avisos.append(
            "Protocolo da Consulta: duas leituras independentes "
            "divergiram — número não gravado."
        )

    emitida_em: Optional[str] = None
    if leitura1.data and leitura1.data == leitura2.data:
        emitida_em = _data_iso(leitura1.data)
        if leitura1.data and emitida_em is None:
            avisos.append(
                "data da consulta: as duas leituras concordaram num valor "
                "que não é uma data válida — data não gravada."
            )
    elif leitura1.data or leitura2.data:
        avisos.append(
            "Data da consulta (relógio da barra de tarefas): duas leituras "
            "independentes divergiram — data não gravada."
        )

    return CenprotEstrutura(numero=numero, emitida_em=emitida_em, avisos=tuple(avisos))


__all__ = [
    "CenprotEstrutura",
    "CenprotLeitura",
    "estruturar_cenprot",
]
