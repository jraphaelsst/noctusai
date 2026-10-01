"""The roteiro cronograma, as a PDF — one imóvel per page, in visiting order.

Rendering goes through `noctusai_lib.integrations.documents.html_pdf.render_html_pdf`
(owner-mandated path for every platform PDF; reportlab-direct was removed from
this module). The HTML lives in `roteiro_pdf_template`; this module gathers
what the template needs and owns the one piece of I/O the renderer forbids.

PHOTOS
------
`render_html_pdf` blocks remote fetches (SSRF + determinism), so a photo is
fetched HERE, server-side, and embedded as a `data:` URI (`carregar_fotos`).
That fetch is bounded (timeout, size cap, image content-type only) and a
failure is NEVER silent and NEVER fatal: it is logged at WARNING and the page
renders a visible "foto indisponível" placeholder — a cronograma without one
photo is still useful at the door, a 500 is not.

Server-side rather than a browser print dialog so these bytes can later be
attached to a WhatsApp message or e-mail without a browser in the loop.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import httpx

from noctusai_lib.integrations.documents.html_pdf import render_html_pdf
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import roteiro_pdf_template as tpl

logger = logging.getLogger(__name__)

VAZIO = tpl.VAZIO

FOTO_TIMEOUT_S = 5.0
FOTO_MAX_BYTES = 3 * 1024 * 1024
#: Formats xhtml2pdf (PIL) embeds reliably; anything else is a placeholder, not
#: a render failure.
_TIPOS_FOTO = {"image/jpeg", "image/jpg", "image/png", "image/gif"}


def gerar(
    roteiro: dict,
    *,
    cliente_nome: Optional[str] = None,
    proprietarios_por_codigo: Optional[dict[str, list[dict]]] = None,
    fotos_por_codigo: Optional[dict[str, str]] = None,
) -> bytes:
    """`RoteiroOut` -> PDF bytes. Takes the already-enriched dict (no DB reads)."""
    visitas = sorted(
        roteiro.get("visitas") or [], key=lambda v: (v.get("ordem") or 0)
    )
    if not visitas:
        # A zero-page PDF is a corrupt file, not an empty state.
        raise ValidationError_("roteiro sem imóveis não gera cronograma", field="visitas")

    proprietarios = {k.strip().upper(): v for k, v in (proprietarios_por_codigo or {}).items()}
    fotos = {k.strip().upper(): v for k, v in (fotos_por_codigo or {}).items()}
    titulo = _titulo_documento(roteiro)
    data_visita = tpl.formatar_data(roteiro.get("data_visita"))
    total = len(visitas)

    paginas = []
    for i, visita in enumerate(visitas, start=1):
        chave = str(visita.get("codigo") or "").strip().upper()
        paginas.append(
            tpl.pagina(
                visita,
                indice=i,
                total=total,
                titulo=titulo,
                data_visita=data_visita,
                cliente_nome=cliente_nome,
                proprietarios=proprietarios.get(chave) or [],
                foto_data_uri=fotos.get(chave),
                foto_dim=_dimensoes(fotos.get(chave)),
            )
        )
    return render_html_pdf(tpl.documento(paginas, titulo=titulo))


#: The photo box (pt). Aspect ratio is preserved inside it so a tall photo can
#: never push the page over and break "one imóvel per page".
_CAIXA_FOTO = (330, 230)


def _dimensoes(data_uri: Optional[str]) -> tuple[int, int]:
    if not data_uri:
        return _CAIXA_FOTO
    try:
        from PIL import Image

        with Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1]))) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001 — undecodable bytes: fall back to the box, logged
        logger.warning("roteiro pdf: foto com dimensões ilegíveis; usando caixa padrão")
        return _CAIXA_FOTO
    escala = min(_CAIXA_FOTO[0] / w, _CAIXA_FOTO[1] / h)
    return max(1, int(w * escala)), max(1, int(h * escala))


def nome_arquivo(roteiro: dict) -> str:
    """`roteiro-<id8>[-<YYYY-MM-DD>].pdf` — date part only when the roteiro has one."""
    base = f"roteiro-{str(roteiro.get('id') or '')[:8]}"
    data = str(roteiro.get("data_visita") or "")[:10]
    return f"{base}-{data}.pdf" if data else f"{base}.pdf"


def _titulo_documento(roteiro: dict) -> str:
    return roteiro.get("titulo") or f"Roteiro de {tpl.formatar_data(roteiro.get('created_at'))}"


def carregar_fotos(
    imoveis: list[dict],
    *,
    client: Optional[httpx.Client] = None,
) -> dict[str, str]:
    """`codigo -> data: URI` of each imóvel's first photo; failures => missing key.

    `imoveis` are `ImovelResumo` dicts (`foto_destaque`, else `fotos[0]`).
    `client` is the DI seam (tests pass an `httpx.Client(transport=MockTransport)`).
    """
    out: dict[str, str] = {}
    proprio = client is None
    http = client or httpx.Client(timeout=FOTO_TIMEOUT_S, follow_redirects=True)
    try:
        for imovel in imoveis:
            codigo = str(imovel.get("codigo") or "").strip().upper()
            url = _primeira_foto(imovel)
            if not codigo or not url:
                continue
            uri = _baixar(http, codigo, url)
            if uri:
                out[codigo] = uri
    finally:
        if proprio:
            http.close()
    return out


def _primeira_foto(imovel: dict) -> Optional[str]:
    url = imovel.get("foto_destaque")
    if not url:
        fotos = imovel.get("fotos") or []
        first = fotos[0] if fotos else None
        url = first.get("url") if isinstance(first, dict) else first
    return str(url) if url else None


def _baixar(http: httpx.Client, codigo: str, url: str) -> Optional[str]:
    if not url.lower().startswith(("http://", "https://")):
        logger.warning("roteiro pdf: foto de %s ignorada (esquema não http/https)", codigo)
        return None
    try:
        with http.stream("GET", url, timeout=FOTO_TIMEOUT_S) as resp:
            resp.raise_for_status()
            tipo = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if tipo not in _TIPOS_FOTO:
                logger.warning(
                    "roteiro pdf: foto de %s com content-type não suportado %r", codigo, tipo
                )
                return None
            corpo = bytearray()
            for pedaco in resp.iter_bytes():
                corpo.extend(pedaco)
                if len(corpo) > FOTO_MAX_BYTES:
                    logger.warning(
                        "roteiro pdf: foto de %s excede %d bytes", codigo, FOTO_MAX_BYTES
                    )
                    return None
    except httpx.HTTPError as exc:
        logger.warning("roteiro pdf: falha ao buscar foto de %s (%s)", codigo, exc)
        return None
    if not corpo:
        logger.warning("roteiro pdf: foto de %s vazia", codigo)
        return None
    return f"data:{tipo};base64,{base64.b64encode(bytes(corpo)).decode('ascii')}"
