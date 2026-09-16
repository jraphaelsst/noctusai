"""``noctus.photo_editing.list_rejections`` — per-rejected-photo detail for an org.

Reads ``social_wiring.fotos_dataset`` — the engine's append-only
training-ready export (``noctusai_lib.domain.photo_editing.types.
DatasetRecord`` / ``PhotoEditingRepository.list_rejections`` is the async
engine-side equivalent; this tool queries the same underlying rows
directly via PostgREST, matching the ``noctus.youtube.*`` direct-query
shape rather than driving the async Protocol from a sync MCP handler) —
filtered to ``decisao_final = 'rejeitar'``, then enriches each row with:

  - the effective style-guide **version** in force at submit time
    (``fotos_dataset.guia_efetivo_sha256`` → ``fotos_guias_efetivos`` →
    ``fotos_guias_estilo.versao``);
  - the editor **model** that produced the ``depois`` (after) image
    (latest ``fotos_edicoes`` row for that photo — ``modelo_id`` +
    ``modelo_versao``);
  - short-lived **signed before/after URLs** (``edicao-fotos`` bucket,
    TTL ``_db.SIGNED_URL_TTL_SECONDS`` ≤ 1h).

Bounded by ``limit`` (default 50, capped at 100) — never dumps the whole
dataset. Plan §1: "Claude Code must be able to inspect rejected photos
through an MCP tool."

Parameters
----------
org : str
    Organization specifier — UUID, slug, or name substring. Required (no
    auto-select default — see ``_resolve.resolve_org``).
batch : str
    Optional ``fotos_lotes.id`` (UUID) to scope to one batch.
edit_types : list[str]
    Optional subset of the fixed edit-type vocabulary
    (``cor_luz`` / ``ceu`` / ``declutter`` / ``staging_virtual``) — a
    rejection row is included when its ``tipos_edicao`` overlaps this set.
limit : int
    Maximum rows to return (default 50, capped at 100).

Returns
-------
dict — one of:

    Success::

        {
          "org_id": "<uuid>",
          "org_label": "Imobiliária Exemplo",
          "total_returned": 2,
          "rejections": [
            {
              "foto_id": "<uuid>",
              "lote_id": "<uuid>",
              "comentario": "Céu ficou artificial demais",
              "tipos_edicao": ["ceu"],
              "guia_versao": 7,
              "modelo_id": "gpt-image-2.5-sunburst",
              "modelo_versao": "2026-09-08",
              "avaliacao_score": "8.10",
              "avaliacao_recomendacao": "aprovar",
              "antes_url": "https://.../object/sign/edicao-fotos/...",
              "depois_url": "https://.../object/sign/edicao-fotos/...",
              "created_at": "2026-09-15T18:04:00+00:00",
            },
            ...
          ],
        }

    No data / org / validation error: structured ``error`` or
    ``status: no_data`` dict.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.domain.photo_editing.types import Decision, EditType

from ._db import BUCKET, SIGNED_URL_TTL_SECONDS, get_pe_client, _not_configured_error
from ._resolve import resolve_org

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100

_VALID_EDIT_TYPES = frozenset(e.value for e in EditType)
_REJEITAR = Decision.REJEITAR.value


def _is_uuid(s: str) -> bool:
    import uuid as _uuid_mod

    try:
        _uuid_mod.UUID(s)
        return True
    except ValueError:
        return False


def _signed_url(client, path: str | None) -> str | None:
    """Best-effort signed URL for ``path`` in the ``edicao-fotos`` bucket.

    Returns ``None`` for an absent path (e.g. a photo still ``em_lote_
    openai`` with no ``storage_path_editada`` yet) or on a storage-API
    failure — logged, never raised, so one bad object never blanks the
    whole list.
    """
    if not path:
        return None
    try:
        response = client.storage.from_(BUCKET).create_signed_url(
            path, SIGNED_URL_TTL_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - degrade, don't crash the list
        logger.warning(
            "photo_editing.list_rejections: signed_url failed bucket=%s path=%s err=%s",
            BUCKET,
            path,
            exc,
        )
        return None
    if isinstance(response, dict):
        url = response.get("signedURL") or response.get("signed_url")
        if isinstance(url, str) and url:
            return url
    logger.warning(
        "photo_editing.list_rejections: unexpected create_signed_url response shape: %r",
        response,
    )
    return None


def _latest_edits_by_foto(client, foto_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Latest ``fotos_edicoes`` row (highest ``tentativa``) per ``foto_id``."""
    if not foto_ids:
        return {}
    resp = (
        client.table("fotos_edicoes")
        .select("foto_id, modelo_id, modelo_versao, tentativa")
        .in_("foto_id", foto_ids)
        .execute()
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in resp.data or []:
        fid = row.get("foto_id")
        current = latest.get(fid)
        if current is None or (row.get("tentativa") or 0) >= (current.get("tentativa") or 0):
            latest[fid] = row
    return latest


def _guide_versions_by_sha(client, org_id: str, shas: list[str]) -> dict[str, int]:
    """``guia_efetivo_sha256`` -> ``fotos_guias_estilo.versao``, via ``fotos_guias_efetivos``."""
    if not shas:
        return {}
    efetivos = (
        client.table("fotos_guias_efetivos")
        .select("sha256, guia_estilo_id")
        .eq("org_id", org_id)
        .in_("sha256", shas)
        .execute()
    )
    sha_to_guia_id: dict[str, str] = {
        row["sha256"]: row["guia_estilo_id"]
        for row in (efetivos.data or [])
        if row.get("sha256") and row.get("guia_estilo_id")
    }
    guia_ids = list(set(sha_to_guia_id.values()))
    if not guia_ids:
        return {}
    guias = (
        client.table("fotos_guias_estilo").select("id, versao").in_("id", guia_ids).execute()
    )
    guia_id_to_versao: dict[str, int] = {
        row["id"]: row["versao"] for row in (guias.data or []) if row.get("id") is not None
    }
    return {
        sha: guia_id_to_versao[guia_id]
        for sha, guia_id in sha_to_guia_id.items()
        if guia_id in guia_id_to_versao
    }


def list_rejections(
    org: str = "",
    batch: str = "",
    edit_types: list[str] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    """Return per-rejected-photo detail for an org.

    See module docstring for the full parameter + return shape.
    """
    try:
        client = get_pe_client()
    except RuntimeError:
        return _not_configured_error("noctus.photo_editing.list_rejections")

    org_row = resolve_org(client, org or None)
    if org_row is None:
        return {
            "error": "org_not_found",
            "org": org,
            "message": "No organization matched the specifier.",
        }
    if "error" in org_row:
        return org_row

    if batch and not _is_uuid(batch):
        return {
            "error": "invalid_batch",
            "batch": batch,
            "message": "batch must be a UUID (fotos_lotes.id).",
        }

    edit_types = edit_types or []
    invalid_types = [t for t in edit_types if t not in _VALID_EDIT_TYPES]
    if invalid_types:
        return {
            "error": "invalid_edit_type",
            "invalid": invalid_types,
            "valid_values": sorted(_VALID_EDIT_TYPES),
        }

    org_id = org_row["id"]
    limit = min(max(1, limit), _MAX_LIMIT)

    query = (
        client.table("fotos_dataset")
        .select(
            "foto_id, lote_id, comentario, tipos_edicao, guia_efetivo_sha256, "
            "avaliacao_score, avaliacao_recomendacao, storage_path_original, "
            "storage_path_editada, created_at"
        )
        .eq("org_id", org_id)
        .eq("decisao_final", _REJEITAR)
    )
    if batch:
        query = query.eq("lote_id", batch)
    if edit_types:
        query = query.overlaps("tipos_edicao", edit_types)

    resp = query.order("created_at", desc=True).limit(limit).execute()
    rows: list[dict[str, Any]] = resp.data or []

    if not rows:
        return {
            "status": "no_data",
            "org_id": org_id,
            "org_label": org_row.get("nome", ""),
            "message": "No rejected photos matched the filters.",
        }

    foto_ids = [r["foto_id"] for r in rows if r.get("foto_id")]
    shas = [r["guia_efetivo_sha256"] for r in rows if r.get("guia_efetivo_sha256")]
    edits_by_foto = _latest_edits_by_foto(client, foto_ids)
    versao_by_sha = _guide_versions_by_sha(client, org_id, shas)

    rejections: list[dict[str, Any]] = []
    for row in rows:
        foto_id = row.get("foto_id")
        edit = edits_by_foto.get(foto_id, {})
        rejections.append(
            {
                "foto_id": foto_id,
                "lote_id": row.get("lote_id"),
                "comentario": row.get("comentario"),
                "tipos_edicao": row.get("tipos_edicao") or [],
                "guia_versao": versao_by_sha.get(row.get("guia_efetivo_sha256")),
                "modelo_id": edit.get("modelo_id"),
                "modelo_versao": edit.get("modelo_versao"),
                "avaliacao_score": row.get("avaliacao_score"),
                "avaliacao_recomendacao": row.get("avaliacao_recomendacao"),
                "antes_url": _signed_url(client, row.get("storage_path_original")),
                "depois_url": _signed_url(client, row.get("storage_path_editada")),
                "created_at": row.get("created_at"),
            }
        )

    return {
        "org_id": org_id,
        "org_label": org_row.get("nome", ""),
        "total_returned": len(rejections),
        "rejections": rejections,
    }


def register(server) -> None:
    """Register ``noctus.photo_editing.list_rejections`` on the MCP server."""

    @server.tool(
        name="noctus.photo_editing.list_rejections",
        description=(
            "Return per-rejected-photo detail for an org's Edição de Fotos "
            "batches: the reviewer's comment, the effective style-guide "
            "version in force at submit time, the editor model that "
            "produced the after image, and short-lived signed before/after "
            "URLs (edicao-fotos bucket, TTL <= 1h). Pass org as a UUID, "
            "slug, or name (required); optionally scope to one batch (UUID) "
            "or a subset of edit types (cor_luz/ceu/declutter/"
            "staging_virtual). limit caps rows returned (default 50, max "
            "100)."
        ),
    )
    def _handler(
        org: str = "",
        batch: str = "",
        edit_types: list[str] | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        return list_rejections(org=org, batch=batch, edit_types=edit_types, limit=limit)
