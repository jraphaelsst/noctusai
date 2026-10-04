"""CENPROT (protest registry) manual-upload reader — region crops of the
screenshot, read field by field, written only when self-validated.

🔴 OWNER FINDING (2026-09-30). The office's CENPROT evidence is not an
official certidão: it is a browser screenshot of the CENPROT-SP result page
(the whole desktop, OS taskbar included) pasted into a one-page PDF. The
contract's CENPROT "número" IS the page's "Protocolo da Consulta" (10
digits); the contract's date IS the OS taskbar clock's date.

MEASURED (2026-10-01, 55 real screenshots vs the signed contracts' answer
keys, verdicts only)
----------------------------------------------------------------------
- Generic whole-page transcription (the pre-existing path): número right in
  3/8 prod rows, date right in 0/8 — and the date line is never transcribed.
- Why: the screenshot is ~5000 px wide once rendered; the vision API scales
  any image down to ~1568 px on its long edge, so 10-digit protocol numbers
  and the taskbar clock reach the model as a few pixels per glyph. The model
  fills gaps from its priors — the clock's YEAR came back 1-6 years early in
  10 of 15 date misses, never late.
- Two reads of the SAME image agree on the SAME misread (25/45 wrong numbers
  were "validated" by same-image agreement) — agreement only protects when
  the two reads see DIFFERENT pixels.

THE READER (this module)
------------------------
- Text layer first (2026-10-03). Two of the common layouts carry their
  values as real PDF text, not pixels: the PRINTED page (Chrome's print-to-
  PDF of the result — "Protocolo da Consulta: <10 digits>" + "Documento
  Pesquisado: <CPF/CNPJ>" as text) and InfoSimples' SYNTHESIZED receipt for
  a "nada consta" (no protocol exists; "Horário: dd/mm/aaaa hh:mm:ss" + the
  queried document under "Parâmetros"). Measured on the local corpus
  (verdicts only): 10/10 printed pages give a 10-digit protocol + a
  check-digit-valid Documento from text alone; 6/6 receipts give a
  Documento + a date (3 standalone, 3 inside merged bundles — the receipt's
  own block is parsed, never another API's). Text is the document's own characters, so
  no vision call is made and no agreement rule is needed — only the same
  identity check. A text-layer Documento of SOMEONE ELSE blocks everything
  (no vision fallback: the characters are exact). Runs before the provider
  gate — no model is involved. Measured note: the site's 10-digit protocol
  is NOT date-prefixed (0/13 parse as YYMMDD), so it never yields a date.
- Layout first. A landscape dominant image is the SCREENSHOT layout; a
  portrait strip (or none) is the PRINTED-page layout (print-to-PDF of the
  result page, no taskbar) — page 1 is rendered whole and read at its top.
- Número: two different crops around the result body ("Protocolo da
  Consulta" + "Documento Pesquisado"). Different crops = different
  downscaling = errors that do not coincide. Kept only when the two reads
  of ONE model return the same 10 digits.
- Escalation: only when the cheap model (`OCR_MODELS`, Haiku) did not
  self-validate — its two reads disagree, or neither carries a valid
  Documento — the stronger model (`ESCALATION_OCR_MODELS`, Sonnet) reads the
  SAME two crops and must agree with itself. If both models self-agree on
  DIFFERENT numbers, nothing is written.
- Date: the stronger model reads two different crops of the taskbar clock
  (the corner, and the date line alone) with an instruction to write "?"
  for a digit cut by the screen edge — they must agree exactly. Haiku was
  measured unfit for the date: it read the year 1+ years EARLY on 15/55
  clocks (its date prior, not the pixels — the year's last digit is often
  half-cut by the screenshot's right edge) and 3 wrong dates landed INSIDE
  the plausibility window on the date-line crop; Sonnet read 49/50
  resolvable clocks right with 0 wrong inside the window.

MEASURED (55 real files vs the signed contracts, verdicts only)
- 2026-10-01 (Haiku only, fixed crops): número 41 right / 0 wrong / 14
  empty; date 27 right / 0 wrong / 28 empty. Empties by cause: 3 printed
  layout, 4 Documento check-digit misread, 6 crop disagreement (a dropped
  or changed digit), 1 different consulta; dates: 15 year misreads, rest
  gated by the número.
- 2026-10-03 (this design): número 54 right / 0 misread / 1 differs from
  the contract — a faithful read (both models, three crops, verified by
  eye) of a screenshot of a DIFFERENT consulta than the contract cites; it
  was empty before only because Haiku misread its CPF; date 49 right / 1
  (same file) / 5 empty (3 printed pages have no clock, 2 date reads
  disagreed). Escalation fired on 11/55 files.

SELF-VALIDATION
---------------
1. Identity first: a "Documento Pesquisado" from either crop must pass its
   CPF/CNPJ check digits AND, when the consulta carries one, equal the
   party's own document — a protocol that belongs to someone else is as
   wrong as a misread digit.
2. Número: one model's two crop reads agree, exactly 10 digits; a second
   model agreeing on a different number blocks it.
3. Date: only alongside a validated número (it is THAT consulta's date),
   both clock reads equal, a real calendar date, and inside [referência − 180 d, referência + 45 d].
   The signed contracts put the CENPROT date between 120 days before and 30
   days after the deal opened (114/114 items), so a year misread can never
   land inside the window. `referencia` is the consulta's own creation date.
Anything that fails comes back `None` with an aviso — a wrong
protest-certificate number in a signed contract is worse than a gap (owner
directive, 2026-09-30).

Only the provider this was measured on reads CENPROT: any other configured
document provider gets `None` + an aviso rather than an unmeasured guess.

🔴 PRIVACY. `avisos` NEVER carry an extracted value — only what failed.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Awaitable, Callable, Optional

from noctusai_lib.integrations.documents import dominant_embedded_image
from noctusai_lib.integrations.documents.cnpj import is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.providers import (
    ESCALATION_OCR_MODELS,
    OCR_MODELS,
)

logger = logging.getLogger(__name__)

#: Fractions of the screenshot (left, top, right, bottom). Measured layout,
#: 2026-10-01: browser chrome on top, result body upper-left, taskbar clock in
#: the bottom-right corner.
_RECORTE_CORPO = (0.0, 0.15, 0.65, 0.6)
_RECORTE_ESTREITO = (0.0, 0.2, 0.45, 0.5)
_RECORTE_RELOGIO = (0.86, 0.93, 1.0, 1.0)
#: Just the clock's date line — a second, different-pixel view of the date.
_RECORTE_DATA = (0.935, 0.955, 1.0, 1.0)

#: The PRINTED-page layout (2026-10-03): the browser's "print to PDF" of the
#: result page, not a screenshot — A4 portrait, the result body at the top,
#: no taskbar. 3/55 corpus files; the screenshot crops above land on the
#: wrong part of the page for them (both reads came back without the label).
_RECORTE_PAGINA_TOPO = (0.0, 0.0, 1.0, 0.4)
_RECORTE_PAGINA_TOPO_ESQ = (0.0, 0.05, 0.7, 0.3)
_DPI_PAGINA = 200
#: A screenshot is landscape (~1.73 measured); the dominant image of a
#: printed page is a portrait strip (or absent).
_ASPECTO_MIN_CAPTURA = 1.2

#: The only provider the measurement above covers.
_PROVEDOR_MEDIDO = "anthropic"

_DIGITOS_PROTOCOLO = 10
_JANELA_ANTES = timedelta(days=180)
_JANELA_DEPOIS = timedelta(days=45)
_MAX_TOKENS = 120

PROMPT_PROTOCOLO = """Esta imagem é um recorte de uma captura de tela do site CENPROT-SP.
Leia EXATAMENTE, dígito por dígito, sem adivinhar:
1. "protocolo": o número ao lado do rótulo "Protocolo da Consulta" (somente dígitos).
2. "documento": o CPF/CNPJ ao lado de "Documento Pesquisado" (somente dígitos).
Se o rótulo não aparecer ou algum dígito estiver ilegível, use null.
Responda SOMENTE com JSON: {"protocolo": ..., "documento": ...}"""

PROMPT_DATA = """Esta imagem é um recorte do relógio da barra de tarefas de um computador (hora em cima, data embaixo).
Transcreva a linha da DATA caractere por caractere, exatamente como aparece na imagem.
Se algum dígito estiver cortado na borda da imagem, parcialmente visível ou ilegível, escreva "?" no lugar dele — nunca complete nem deduza.
Responda SOMENTE com JSON: {"data": "dd/mm/aaaa"}"""

#: `(image_bytes, prompt, model) -> raw model text`. The DI seam tests use.
LerImagem = Callable[[bytes, str, str], Awaitable[str]]


@dataclass(frozen=True)
class CenprotEstrutura:
    """`numero`/`emitida_em` are `None` whenever they could not be
    validated, never a best-effort guess. `avisos` are PT-BR,
    diagnostics-only — logged by the caller, never persisted."""

    numero: Optional[str] = None
    emitida_em: Optional[str] = None
    avisos: tuple[str, ...] = ()


def _recortar(imagem: bytes, caixa: tuple[float, float, float, float]) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(imagem))
    w, h = im.size
    recorte = im.crop(
        (int(caixa[0] * w), int(caixa[1] * h), int(caixa[2] * w), int(caixa[3] * h))
    ).convert("RGB")
    saida = io.BytesIO()
    recorte.save(saida, "JPEG", quality=92)
    return saida.getvalue()


def _aspecto(imagem: bytes) -> float:
    from PIL import Image

    w, h = Image.open(io.BytesIO(imagem)).size
    return w / h if h else 0.0


def _renderizar_pagina(pdf_bytes: bytes) -> Optional[bytes]:
    """Page 1 rasterized whole — the printed-page layout's own pixels."""
    import fitz  # type: ignore  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.page_count < 1:
        return None
    return doc[0].get_pixmap(dpi=_DPI_PAGINA).tobytes("jpg", jpg_quality=92)


def _json(texto: Optional[str]) -> dict:
    """The model's JSON object, or `{}` — never raises."""
    if not texto:
        return {}
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return {}
    try:
        dados = json.loads(m.group(0))
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


def _digitos(valor) -> Optional[str]:
    if valor is None:
        return None
    d = only_digits(str(valor))
    return d or None


def _documento_valido(documento: Optional[str], tipo_documento: Optional[str]) -> bool:
    if not documento:
        return False
    if tipo_documento == "cnpj":
        return _cnpj_is_valid(documento)
    if tipo_documento == "cpf":
        return _cpf_is_valid(documento)
    return _cpf_is_valid(documento) or _cnpj_is_valid(documento)


def _data(valor) -> Optional[date]:
    """`"17/06/2026"` → `date`, or `None` for anything not a real date
    (a `?` the model wrote for a cut-off digit included)."""
    if not isinstance(valor, str):
        return None
    m = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", valor)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _leitor_padrao(org_id: Optional[str], provider: str) -> LerImagem:
    async def ler(imagem: bytes, prompt: str, modelo: str) -> str:
        # Usage + cost are recorded by the seed provider itself
        # (`llm.usage.record_usage` → the configured usage sink).
        from noctusai_lib.integrations.llm.vision import analyze_image

        return await analyze_image(
            imagem,
            prompt,
            provider=provider,
            model=modelo,
            org_id=org_id,
            max_tokens=_MAX_TOKENS,
        )

    return ler


async def _ler_varios(
    ler: LerImagem, pedidos: list[tuple[bytes, str, str]], nome_display: str,
) -> list[dict]:
    respostas = await asyncio.gather(
        *(ler(img, prompt, modelo) for img, prompt, modelo in pedidos),
        return_exceptions=True,
    )
    for r in respostas:
        if isinstance(r, BaseException):
            logger.warning("CENPROT %s: leitura falhou: %s", nome_display, r)
    return [_json(r) if isinstance(r, str) else {} for r in respostas]


def _protocolo_concordante(a: dict, b: dict) -> Optional[str]:
    p1, p2 = _digitos(a.get("protocolo")), _digitos(b.get("protocolo"))
    if p1 and p1 == p2 and len(p1) == _DIGITOS_PROTOCOLO:
        return p1
    return None


_RE_PROTOCOLO_TEXTO = re.compile(r"Protocolo\s+da\s+Consulta\s*:\s*([0-9][0-9 .]*[0-9])", re.I)
_RE_DOCUMENTO_TEXTO = re.compile(r"Documento\s+Pesquisado\s*:\s*([^\n]*)", re.I)
_RE_RECIBO_SINTETIZADO = re.compile(r"API\s*:\s*CENPROT", re.I)
_RE_HORARIO_RECIBO = re.compile(r"Hor[áa]rio\s*:\s*(\d{2}/\d{2}/\d{4})")
_RE_PARAMETRO_DOCUMENTO = re.compile(r"Par[âa]metros\s*:\s*(?:cpf|cnpj)\s+([0-9./\-]+)", re.I)


@dataclass(frozen=True)
class LeituraTexto:
    """What a CENPROT PDF's TEXT LAYER says — every field `None` when the
    PDF carries no such text (a screenshot is pixels only).

    `recibo` is InfoSimples' synthesized "nada consta" receipt: no protocol
    exists on it; `horario` is the date it printed for the consulta."""

    protocolo: Optional[str] = None
    documento: Optional[str] = None
    horario: Optional[date] = None
    recibo: bool = False


def _texto_do_pdf(pdf_bytes: bytes) -> str:
    """Every page's text layer, joined — `""` when there is none or the PDF
    does not open (never raises: the vision path still runs after it)."""
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return "\n".join(pagina.get_text() for pagina in doc)
    except Exception as exc:  # noqa: BLE001 - the vision path still runs
        logger.warning("CENPROT: camada de texto ilegível: %s", exc)
        return ""


def ler_camada_texto(texto: str) -> LeituraTexto:
    """Parse the two text-layer layouts (module docstring). Pure."""
    if not texto:
        return LeituraTexto()
    protocolo = None
    m = _RE_PROTOCOLO_TEXTO.search(texto)
    if m:
        digitos = only_digits(m.group(1))
        if len(digitos) == _DIGITOS_PROTOCOLO:
            protocolo = digitos
    documento = None
    m = _RE_DOCUMENTO_TEXTO.search(texto)
    if m:
        documento = _digitos(m.group(1))
    recibo_m = _RE_RECIBO_SINTETIZADO.search(texto)
    horario = None
    if recibo_m:
        # Only the CENPROT receipt's OWN block: a merged bundle carries other
        # APIs' synthesized receipts ("API: …", "Horário: …") too.
        bloco = texto[recibo_m.end():]
        proximo = re.search(r"\bAPI\s*:", bloco)
        if proximo:
            bloco = bloco[:proximo.start()]
        m = _RE_HORARIO_RECIBO.search(bloco)
        horario = _data(m.group(1)) if m else None
        if documento is None:
            m = _RE_PARAMETRO_DOCUMENTO.search(bloco)
            documento = _digitos(m.group(1)) if m else None
    recibo = recibo_m is not None
    return LeituraTexto(protocolo=protocolo, documento=documento, horario=horario, recibo=recibo)


def _na_janela(dia: date, referencia: date) -> bool:
    return referencia - _JANELA_ANTES <= dia <= referencia + _JANELA_DEPOIS


def _estrutura_da_camada_texto(
    leitura: LeituraTexto,
    *,
    tipo_documento_esperado: Optional[str],
    documento_esperado: Optional[str],
    referencia: Optional[date],
) -> Optional[CenprotEstrutura]:
    """The answer when the text layer is decisive, else `None` (→ vision).

    Decisive = a 10-digit protocol, OR the synthesized receipt — both with
    a text-layer Documento. A Documento that fails identity is decisive too
    (blocks everything): exact characters of another party's consulta."""
    if not (leitura.protocolo or leitura.recibo):
        return None
    if not leitura.documento:
        return None
    esperado = _digitos(documento_esperado)
    if not (
        _documento_valido(leitura.documento, tipo_documento_esperado)
        and (esperado is None or leitura.documento == esperado)
    ):
        return CenprotEstrutura(avisos=(
            "Documento Pesquisado (texto do PDF): dígito verificador inválido "
            "ou diferente do CPF/CNPJ da parte na consulta — número e data "
            "não gravados.",
        ))
    avisos: list[str] = []
    emitida_em: Optional[str] = None
    if leitura.recibo:
        if leitura.horario is None:
            avisos.append("Recibo sem horário legível — data não gravada.")
        elif referencia is None:
            avisos.append("Recibo: sem data de referência para conferir — data não gravada.")
        elif not _na_janela(leitura.horario, referencia):
            avisos.append(
                "Recibo: horário fora da janela plausível em relação à consulta "
                "— data não gravada."
            )
        else:
            emitida_em = leitura.horario.isoformat()
        if not leitura.protocolo:
            avisos.append(
                "Recibo de \"nada consta\" sintetizado — a consulta não tem "
                "protocolo; número não gravado."
            )
    else:
        avisos.append(
            "Data: página impressa do CENPROT, sem relógio da barra de "
            "tarefas — data não gravada."
        )
    return CenprotEstrutura(
        numero=leitura.protocolo, emitida_em=emitida_em, avisos=tuple(avisos),
    )


async def estruturar_cenprot(
    pdf_bytes: bytes,
    nome_display: str,
    org_id: Optional[str],
    *,
    provider: Optional[str],
    tipo_documento_esperado: Optional[str],
    documento_esperado: Optional[str],
    referencia: Optional[date],
    ler: Optional[LerImagem] = None,
) -> CenprotEstrutura:
    """Read and self-validate a CENPROT screenshot's número + date.

    Never raises — the caller is a background job; any failure is
    `CenprotEstrutura(avisos=...)`. The text layer is consulted first
    (`ler_camada_texto`) — exact characters, no model, no spend.
    """
    pela_camada = _estrutura_da_camada_texto(
        ler_camada_texto(_texto_do_pdf(pdf_bytes)),
        tipo_documento_esperado=tipo_documento_esperado,
        documento_esperado=documento_esperado,
        referencia=referencia,
    )
    if pela_camada is not None:
        return pela_camada
    if provider != _PROVEDOR_MEDIDO:
        return CenprotEstrutura(avisos=(
            "Leitura do CENPROT só é feita com o provedor de documentos "
            "medido (Anthropic) — número e data não gravados.",
        ))
    modelo = OCR_MODELS[provider]
    modelo_forte = ESCALATION_OCR_MODELS[provider]

    try:
        imagem = dominant_embedded_image(pdf_bytes, 1)
        captura = imagem is not None and _aspecto(imagem) >= _ASPECTO_MIN_CAPTURA
        if not captura:
            imagem = _renderizar_pagina(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.warning("CENPROT %s: imagem da página falhou: %s", nome_display, exc)
        imagem, captura = None, False
    if imagem is None:
        return CenprotEstrutura(avisos=(
            "O PDF não contém a captura de tela esperada do CENPROT — "
            "número e data não gravados.",
        ))

    ler = ler or _leitor_padrao(org_id, provider)
    caixas = (
        (_RECORTE_CORPO, _RECORTE_ESTREITO) if captura
        else (_RECORTE_PAGINA_TOPO, _RECORTE_PAGINA_TOPO_ESQ)
    )
    try:
        recortes = [_recortar(imagem, c) for c in caixas]
    except Exception as exc:  # noqa: BLE001
        logger.warning("CENPROT %s: recorte falhou: %s", nome_display, exc)
        return CenprotEstrutura(avisos=(
            "Não foi possível recortar a captura de tela do CENPROT — "
            "número e data não gravados.",
        ))

    esperado = _digitos(documento_esperado)

    def identidade_ok(leituras: list[dict]) -> bool:
        return any(
            (d := _digitos(r.get("documento")))
            and _documento_valido(d, tipo_documento_esperado)
            and (esperado is None or d == esperado)
            for r in leituras
        )

    # Rung 1 — the cheap model on two different crops.
    leituras = await _ler_varios(
        ler, [(r, PROMPT_PROTOCOLO, modelo) for r in recortes], nome_display,
    )
    concordantes = {p for p in [_protocolo_concordante(*leituras)] if p}

    # Rung 2 — only when rung 1 did not self-validate: the stronger model on
    # the SAME two crops (its own two reads must agree with each other).
    if not concordantes or not identidade_ok(leituras):
        fortes = await _ler_varios(
            ler, [(r, PROMPT_PROTOCOLO, modelo_forte) for r in recortes], nome_display,
        )
        leituras += fortes
        p_forte = _protocolo_concordante(*fortes)
        if p_forte:
            concordantes.add(p_forte)

    if not identidade_ok(leituras):
        return CenprotEstrutura(avisos=(
            "Documento Pesquisado: ilegível, dígito verificador inválido ou "
            "diferente do CPF/CNPJ da parte na consulta — número e data não "
            "gravados.",
        ))
    if len(concordantes) != 1:
        return CenprotEstrutura(avisos=(
            "Protocolo da Consulta: as leituras não concordaram em 10 "
            "dígitos — número e data não gravados.",
        ))
    numero = concordantes.pop()

    if not captura:
        return CenprotEstrutura(numero=numero, avisos=(
            "Data: página impressa do CENPROT, sem relógio da barra de "
            "tarefas — data não gravada.",
        ))

    try:
        recortes_data = [_recortar(imagem, _RECORTE_RELOGIO), _recortar(imagem, _RECORTE_DATA)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("CENPROT %s: recorte do relógio falhou: %s", nome_display, exc)
        recortes_data = []
    datas = await _ler_varios(
        ler, [(r, PROMPT_DATA, modelo_forte) for r in recortes_data], nome_display,
    )
    lidas = [_data(d.get("data")) for d in datas]

    avisos: list[str] = []
    emitida_em: Optional[str] = None
    if len(lidas) != 2 or lidas[0] is None or lidas[1] is None:
        avisos.append(
            "Data (relógio da barra de tarefas): ilegível, cortada ou "
            "inválida — data não gravada."
        )
    elif lidas[0] != lidas[1]:
        avisos.append(
            "Data (relógio da barra de tarefas): as duas leituras não "
            "concordaram — data não gravada."
        )
    elif referencia is None:
        avisos.append(
            "Data (relógio da barra de tarefas): sem data de referência para "
            "conferir — data não gravada."
        )
    elif not _na_janela(lidas[0], referencia):
        avisos.append(
            "Data (relógio da barra de tarefas): fora da janela plausível em "
            "relação à consulta — data não gravada."
        )
    else:
        emitida_em = lidas[0].isoformat()

    return CenprotEstrutura(numero=numero, emitida_em=emitida_em, avisos=tuple(avisos))


__all__ = [
    "CenprotEstrutura",
    "LeituraTexto",
    "PROMPT_DATA",
    "PROMPT_PROTOCOLO",
    "estruturar_cenprot",
    "ler_camada_texto",
]
