"""CoreStudio post media: the storage key convention, signed download URLs, upload adoption and ``apagar_insumos``.

Key convention (one private bucket, ``MIDIA_BUCKET``)::

    org/<org_id>/posts/<post_id>/insumos/<file>   raw inputs (owner rule Q5: deleted when the post is fully published)
    org/<org_id>/posts/<post_id>/saidas/<file>    produced / approved outputs (NEVER deleted by this module)
    org/<org_id>/posts/<post_id>/preview/<file>   previews

``apagar_insumos`` is the seam slice S4 (scheduled publish) calls after a FULL publish::

    await apagar_insumos(db, storage, org_id=..., post_id=..., ator_id=None) -> InsumosApagados

It deletes only blobs under the post's ``insumos/`` prefix, marks the matching ``cs_post_assets`` rows
``apagado_em`` (migration 353's trigger writes the ``insumos_apagados`` event in the same transaction as each UPDATE),
is idempotent (a second call deletes/marks nothing) and re-runnable after a partial failure (blobs first, rows second).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from noctusai_lib.integrations.storage import StorageBackend

logger = logging.getLogger(__name__)

MIDIA_BUCKET = "sw-posts-midia"
ZONAS = ("insumos", "saidas", "preview")
ASSETS = "cs_post_assets"
POSTS = "cs_posts"
#: Signed download TTL for the browser/sandbox: the seam default (600 s), never longer without a reason.
TTL_DOWNLOAD_S = 600

_ID_OK = re.compile(r"^[0-9a-fA-F-]{8,64}$")
_NOME_OK = re.compile(r"[^A-Za-z0-9._-]+")
_PAGINA = 1000
_MAX_PAGINAS = 200


class MidiaStorageError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _id(v: str, campo: str) -> str:
    if not isinstance(v, str) or not _ID_OK.match(v):
        raise MidiaStorageError("id_invalido", f"{campo} inválido")
    return v


def prefixo_post(org_id: str, post_id: str) -> str:
    return f"org/{_id(org_id, 'org_id')}/posts/{_id(post_id, 'post_id')}/"


def prefixo_zona(org_id: str, post_id: str, zona: str) -> str:
    if zona not in ZONAS:
        raise MidiaStorageError("zona_invalida", f"Zona inválida: {zona}")
    return f"{prefixo_post(org_id, post_id)}{zona}/"


def zona_de(storage_path: str) -> Optional[str]:
    """The zone segment of a key (``insumos``/``saidas``/``preview``), or None when the key has no zone."""
    partes = storage_path.split("/")
    if len(partes) >= 6 and partes[0] == "org" and partes[2] == "posts" and partes[4] in ZONAS:
        return partes[4]
    return None


def chave_upload(org_id: str, post_id: str, zona: str, filename: str) -> str:
    """Server-derived key for a new file (the client never chooses the prefix); the name is sanitised."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    nome = _NOME_OK.sub("_", base).strip("._") or "arquivo"
    return f"{prefixo_zona(org_id, post_id, zona)}{nome}"


def validar_chave(org_id: str, post_id: str, storage_path: str) -> str:
    """The key must sit in a ZONE under THIS org's and post's prefix; returns the zone. A foreign/zoneless key is refused."""
    pref = prefixo_post(org_id, post_id)
    if ".." in storage_path or "//" in storage_path or not storage_path.startswith(pref):
        raise MidiaStorageError("caminho_invalido", "O arquivo não pertence a este post")
    zona = zona_de(storage_path)
    if zona is None or len(storage_path.split("/")) < 6 or storage_path.endswith("/"):
        raise MidiaStorageError("caminho_invalido", "O arquivo precisa estar em insumos/, saidas/ ou preview/")
    return zona


async def url_download(storage: StorageBackend, *, org_id: str, post_id: str, storage_path: str) -> str:
    """Short-lived signed download URL (default TTL), only for a key that validates under the org/post prefix."""
    validar_chave(org_id, post_id, storage_path)
    return await storage.signed_url(bucket=MIDIA_BUCKET, key=storage_path, expires_in_seconds=TTL_DOWNLOAD_S)


async def adotar_upload(
    upload_service: Any, storage: StorageBackend, *, org_id: str, post_id: str, upload_id: str, zona: str = "insumos",
) -> str:
    """Move a COMPLETED seed resumable upload into the post's zone and return the new key.

    ``upload_service`` is the seed ``ResumableUploadService``; ``consume`` hands the assembled bytes to us and removes
    the staging object, so no orphan copy is left outside the post prefix.
    """
    sessao, dados = await upload_service.consume(org_id=org_id, session_id=upload_id)
    chave = chave_upload(org_id, post_id, zona, sessao.filename)
    await storage.put(bucket=MIDIA_BUCKET, key=chave, data=dados, content_type=sessao.content_type)
    return chave


@dataclass(frozen=True)
class InsumosApagados:
    blobs_apagados: int
    assets_marcados: int


async def _listar(storage: StorageBackend, prefixo: str) -> list[str]:
    return await storage.list_keys(bucket=MIDIA_BUCKET, prefix=prefixo, limit=_PAGINA)


async def apagar_insumos(
    db: Any, storage: StorageBackend, *, org_id: str, post_id: str, ator_id: Optional[str] = None,
    agora: Optional[datetime] = None,
) -> InsumosApagados:
    """Delete the post's raw inputs (``insumos/``) and record it. Never touches ``saidas/`` or ``preview/``."""
    prefixo = prefixo_zona(org_id, post_id, "insumos")
    post = await run_in_threadpool(
        lambda: db.table(POSTS).select("id").eq("id", post_id).eq("org_id", org_id).execute().data
    )
    if not post:
        raise MidiaStorageError("post_nao_encontrado", "Post não encontrado")

    apagados = 0
    vistos: set[str] = set()
    for _ in range(_MAX_PAGINAS):
        chaves = [k for k in await _listar(storage, prefixo) if k.startswith(prefixo)]
        novas = [k for k in chaves if k not in vistos]
        if not novas:
            break
        for k in novas:
            vistos.add(k)
            if await storage.delete(bucket=MIDIA_BUCKET, key=k):
                apagados += 1
    else:
        logger.error("apagar_insumos: page cap hit for post %s (more than %d pages)", post_id, _MAX_PAGINAS)
        raise MidiaStorageError("insumos_demais", "Quantidade de insumos acima do limite de uma execução; tente novamente")

    stamp = (agora or datetime.now(timezone.utc)).isoformat()

    def _marcar() -> int:
        rows = (
            db.table(ASSETS).select("id,storage_path,apagado_em").eq("post_id", post_id).eq("org_id", org_id).execute().data
            or []
        )
        n = 0
        for r in rows:
            if r.get("apagado_em") is not None or not str(r["storage_path"]).startswith(prefixo):
                continue
            upd = (
                db.table(ASSETS).update({"apagado_em": stamp, "atualizado_por": ator_id, "updated_at": stamp})
                .eq("id", r["id"]).eq("org_id", org_id).is_("apagado_em", "null").execute().data
            )
            n += 1 if upd else 0
        return n

    marcados = await run_in_threadpool(_marcar)
    logger.info("apagar_insumos post=%s blobs=%d assets=%d", post_id, apagados, marcados)
    return InsumosApagados(apagados, marcados)
