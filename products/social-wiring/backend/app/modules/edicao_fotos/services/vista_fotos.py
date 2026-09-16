"""Pull an imóvel's Vista gallery into a batch (`POST /lotes/{id}/vista`).

Reads through the EXISTING seed Vista adapter (`VistaRESTAdapter.
list_imovel_fotos`, proven live 2026-09-16 — `Foto` on `/imoveis/detalhes`,
dict-keyed payload normalized by the seed) with the product's existing
`VISTA_API_KEY` (`settings.crm_api_key`). No new credential: reads do not
need the portal key (PROJECT.md §C5).

Order: the `Destaque` photo first, then by Vista photo code (contract §10).
Each downloaded photo goes through the engine's `add_photo_bytes`, so the
same limits, formats and GPS-stripping ingest apply as for an upload.
Re-pulling the same imóvel skips photos already in the batch
(`vista_codigo`), so a retried request does not duplicate.

A photo that fails to download is REPORTED in the response (`falhas`) and
logged — never dropped silently — and the rest of the gallery still lands.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx

from noctusai_lib.domain.photo_editing import (
    PhotoEditingPorts,
    SubmissionError,
    add_photo_bytes,
)
from noctusai_lib.domain.real_estate.imovel import ImovelFoto

logger = logging.getLogger(__name__)

#: Download ceiling. The business limit (25 MB) is enforced by the engine;
#: this only bounds how much a misbehaving CDN can make us buffer.
MAX_DOWNLOAD_BYTES = 26 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30.0

_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "heif"}
_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


class VistaFotoDownloadError(RuntimeError):
    """One gallery photo could not be fetched (reported, not fatal)."""


@runtime_checkable
class VistaPhotoSource(Protocol):
    async def list_photos(self, codigo: str) -> list[ImovelFoto]: ...
    async def fetch(self, url: str) -> tuple[bytes, str]:
        """Return ``(bytes, extension)`` or raise `VistaFotoDownloadError`."""
        ...


def extension_for(url: str, content_type: str | None) -> str:
    suffix = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
    if suffix in _EXTENSIONS:
        return suffix
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in _CONTENT_TYPES:
        return _CONTENT_TYPES[mime]
    raise VistaFotoDownloadError(f"formato não identificado ({mime or 'sem content-type'})")


class RealVistaPhotoSource:
    """Seed Vista adapter for the listing + httpx for the image bytes."""

    def __init__(self, adapter: Any, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._adapter = adapter
        self._http = http_client

    async def list_photos(self, codigo: str) -> list[ImovelFoto]:
        return await self._adapter.list_imovel_fotos(codigo)

    async def fetch(self, url: str) -> tuple[bytes, str]:
        if urlparse(url).scheme not in ("http", "https"):
            raise VistaFotoDownloadError("URL de foto inválida")
        client = self._http or httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        )
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise VistaFotoDownloadError(f"HTTP {resp.status_code}")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_DOWNLOAD_BYTES:
                        raise VistaFotoDownloadError("arquivo grande demais")
                return bytes(buf), extension_for(url, resp.headers.get("content-type"))
        except httpx.HTTPError as exc:
            raise VistaFotoDownloadError(f"falha de rede: {type(exc).__name__}") from exc
        finally:
            if self._http is None:
                await client.aclose()


def ordered_gallery(fotos: list[ImovelFoto]) -> list[ImovelFoto]:
    """`Destaque` first, then by photo code (stable, numeric-aware)."""

    def code_key(f: ImovelFoto) -> tuple[int, int, str]:
        code = f.codigo or ""
        return (0, int(code), code) if code.isdigit() else (1, 0, code)

    return sorted((f for f in fotos if f.url), key=lambda f: (not f.destaque, code_key(f)))


@dataclass
class VistaIngestResult:
    codigo: str
    encontradas: int = 0
    adicionadas: list[str] = field(default_factory=list)
    ja_no_lote: list[str] = field(default_factory=list)
    falhas: list[dict[str, str]] = field(default_factory=list)
    interrompido: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "encontradas": self.encontradas,
            "adicionadas": len(self.adicionadas),
            "foto_ids": self.adicionadas,
            "ja_no_lote": len(self.ja_no_lote),
            "falhas": self.falhas,
            "interrompido": self.interrompido,
        }


async def ingest_vista_gallery(
    ports: PhotoEditingPorts,
    source: VistaPhotoSource,
    *,
    lote_id: str,
    codigo: str,
) -> VistaIngestResult:
    result = VistaIngestResult(codigo=codigo)
    fotos = ordered_gallery(await source.list_photos(codigo))
    result.encontradas = len(fotos)
    present = {p.vista_codigo for p in await ports.repo.list_photos(lote_id) if p.vista_codigo}
    for foto in fotos:
        ref = foto.codigo or foto.url or ""
        if foto.codigo and foto.codigo in present:
            result.ja_no_lote.append(foto.codigo)
            continue
        try:
            data, ext = await source.fetch(foto.url or "")
        except VistaFotoDownloadError as exc:
            logger.warning(
                "edicao_fotos: foto Vista %s do imóvel %s não baixada: %s", ref, codigo, exc
            )
            result.falhas.append({"codigo": ref, "motivo": str(exc)})
            continue
        try:
            photo = await add_photo_bytes(
                ports, lote_id=lote_id, data=data, extension=ext, vista_codigo=foto.codigo
            )
        except SubmissionError as exc:
            if exc.code in ("lote_cheio", "lote_ja_submetido"):
                result.interrompido = exc.code
                break
            logger.warning(
                "edicao_fotos: foto Vista %s do imóvel %s recusada: %s", ref, codigo, exc.code
            )
            result.falhas.append({"codigo": ref, "motivo": exc.code})
            continue
        result.adicionadas.append(photo.id)
    return result


__all__ = [
    "MAX_DOWNLOAD_BYTES",
    "RealVistaPhotoSource",
    "VistaFotoDownloadError",
    "VistaIngestResult",
    "VistaPhotoSource",
    "extension_for",
    "ingest_vista_gallery",
    "ordered_gallery",
]
