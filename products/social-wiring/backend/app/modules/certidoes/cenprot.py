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

THE READER (this module) — three small reads, one per crop:
- `_RECORTE_CORPO` and `_RECORTE_ESTREITO`: two different crops around the
  result body, each read for "Protocolo da Consulta" + "Documento
  Pesquisado". Different crops = different downscaling = errors that do not
  coincide. The número is kept only when BOTH crops return the same 10
  digits.
- `_RECORTE_RELOGIO`: the bottom-right taskbar corner, read for the date
  alone, at a resolution where the year is legible.

Measured with this design (Haiku 4.5): número 41 right / 0 wrong / 14 left
empty; date 27 right / 0 wrong / 28 left empty (55 files).

SELF-VALIDATION
---------------
1. Identity first: a "Documento Pesquisado" from either crop must pass its
   CPF/CNPJ check digits AND, when the consulta carries one, equal the
   party's own document — a protocol that belongs to someone else is as
   wrong as a misread digit.
2. Número: both crops agree, exactly 10 digits.
3. Date: only alongside a validated número (it is THAT consulta's date), a
   real calendar date, and inside [referência − 180 d, referência + 45 d].
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
from noctusai_lib.integrations.documents.providers import OCR_MODELS

logger = logging.getLogger(__name__)

#: Fractions of the screenshot (left, top, right, bottom). Measured layout,
#: 2026-10-01: browser chrome on top, result body upper-left, taskbar clock in
#: the bottom-right corner.
_RECORTE_CORPO = (0.0, 0.15, 0.65, 0.6)
_RECORTE_ESTREITO = (0.0, 0.2, 0.45, 0.5)
_RECORTE_RELOGIO = (0.86, 0.93, 1.0, 1.0)

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

PROMPT_DATA = """Esta imagem é o canto inferior direito de uma tela de computador (relógio da barra de tarefas): a hora em cima e a data embaixo.
Leia a DATA exatamente, dígito por dígito, inclusive o ano completo de 4 dígitos. Não deduza o ano; leia o que está escrito. Se ilegível, use null.
Responda SOMENTE com JSON: {"data": "dd/mm/aaaa"}"""

#: `(image_bytes, prompt) -> raw model text`. The DI seam tests use.
LerImagem = Callable[[bytes, str], Awaitable[str]]


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
    """`"17/06/2026"` → `date`, or `None` for anything not a real date."""
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
    async def ler(imagem: bytes, prompt: str) -> str:
        from noctusai_lib.integrations.llm.vision import analyze_image

        return await analyze_image(
            imagem,
            prompt,
            provider=provider,
            model=OCR_MODELS[provider],
            org_id=org_id,
            max_tokens=_MAX_TOKENS,
        )

    return ler


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
    `CenprotEstrutura(avisos=...)`.
    """
    if provider != _PROVEDOR_MEDIDO:
        return CenprotEstrutura(avisos=(
            "Leitura do CENPROT só é feita com o provedor de documentos "
            "medido (Anthropic) — número e data não gravados.",
        ))

    try:
        imagem = dominant_embedded_image(pdf_bytes, 1)
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.warning("CENPROT %s: recorte da imagem falhou: %s", nome_display, exc)
        imagem = None
    if imagem is None:
        return CenprotEstrutura(avisos=(
            "O PDF não contém a captura de tela esperada do CENPROT — "
            "número e data não gravados.",
        ))

    ler = ler or _leitor_padrao(org_id, provider)
    try:
        recortes = [
            _recortar(imagem, _RECORTE_CORPO),
            _recortar(imagem, _RECORTE_ESTREITO),
            _recortar(imagem, _RECORTE_RELOGIO),
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("CENPROT %s: recorte falhou: %s", nome_display, exc)
        return CenprotEstrutura(avisos=(
            "Não foi possível recortar a captura de tela do CENPROT — "
            "número e data não gravados.",
        ))

    respostas = await asyncio.gather(
        ler(recortes[0], PROMPT_PROTOCOLO),
        ler(recortes[1], PROMPT_PROTOCOLO),
        ler(recortes[2], PROMPT_DATA),
        return_exceptions=True,
    )
    for r in respostas:
        if isinstance(r, BaseException):
            logger.warning("CENPROT %s: leitura falhou: %s", nome_display, r)
    corpo, estreito, relogio = (
        _json(r) if isinstance(r, str) else {} for r in respostas
    )

    esperado = _digitos(documento_esperado)
    documentos = [_digitos(corpo.get("documento")), _digitos(estreito.get("documento"))]
    identidade_ok = any(
        d and _documento_valido(d, tipo_documento_esperado)
        and (esperado is None or d == esperado)
        for d in documentos
    )
    if not identidade_ok:
        return CenprotEstrutura(avisos=(
            "Documento Pesquisado: ilegível, dígito verificador inválido ou "
            "diferente do CPF/CNPJ da parte na consulta — número e data não "
            "gravados.",
        ))

    avisos: list[str] = []
    p1, p2 = _digitos(corpo.get("protocolo")), _digitos(estreito.get("protocolo"))
    numero: Optional[str] = None
    if p1 and p1 == p2 and len(p1) == _DIGITOS_PROTOCOLO:
        numero = p1
    else:
        avisos.append(
            "Protocolo da Consulta: as duas leituras não concordaram em 10 "
            "dígitos — número e data não gravados."
        )
        return CenprotEstrutura(avisos=tuple(avisos))

    emitida_em: Optional[str] = None
    lida = _data(relogio.get("data"))
    if lida is None:
        avisos.append(
            "Data (relógio da barra de tarefas): ilegível ou inválida — data "
            "não gravada."
        )
    elif referencia is None:
        avisos.append(
            "Data (relógio da barra de tarefas): sem data de referência para "
            "conferir — data não gravada."
        )
    elif not (referencia - _JANELA_ANTES <= lida <= referencia + _JANELA_DEPOIS):
        avisos.append(
            "Data (relógio da barra de tarefas): fora da janela plausível em "
            "relação à consulta — data não gravada."
        )
    else:
        emitida_em = lida.isoformat()

    return CenprotEstrutura(numero=numero, emitida_em=emitida_em, avisos=tuple(avisos))


__all__ = [
    "CenprotEstrutura",
    "PROMPT_DATA",
    "PROMPT_PROTOCOLO",
    "estruturar_cenprot",
]
