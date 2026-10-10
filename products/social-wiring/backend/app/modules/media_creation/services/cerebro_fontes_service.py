"""Segundo Cérebro — sources: file import (endpoint 14) and Minhas extrações
(endpoints 19-24). Composes :class:`CerebroService` (brain guards, the atomic
``cs_brain_append`` write path, import serialisation) — nothing is duplicated.

v1 scope (cerebro-contract.md §10): file import + pasted-text extractions. URL
sources (YouTube import, extraction by link) are phase 2 — see the
``NOC-REMEDIATE`` markers. Voice answers (13) are a separate slice.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from noctusai_lib.integrations.documents.plain_text import extract_plain_text
from noctusai_lib.integrations.documents.transcription import DocumentTranscriber
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.media_creation.deps import CEREBRO_BUCKET
from app.modules.media_creation.services.cerebro_service import (
    BRAINS,
    IMPORTS,
    CerebroError,
    CerebroService,
    _iso,
    block_header,
    import_dict,
)

logger = logging.getLogger(__name__)

EXTRACTIONS = "cs_extractions"
TARGETS = "cs_extraction_targets"
EXTRACTION_COLS = (
    "id,marca_id,name,source_kind,source_url,transcript,status,error_message,created_at"
)

MAX_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({"pdf", "docx", "txt", "md", "csv"})

MSG_YOUTUBE_UNAVAILABLE = "Transcrição do YouTube ainda não disponível"
MSG_URL_UNAVAILABLE = "Extração por link ainda não disponível"
MSG_UNREADABLE = "Não foi possível ler texto deste arquivo."
MSG_IMPORT_FAILED = "Ocorreu um erro ao importar o arquivo. Tente novamente."
MSG_BAD_FORMAT = "Formato de arquivo não suportado. Envie PDF, DOCX, TXT, MD ou CSV."
MSG_BAD_ENCODING = "Não foi possível ler a codificação do arquivo. Salve-o como UTF-8."
MSG_DOCX_UNREADABLE = "Não foi possível ler este arquivo DOCX."

#: ``PlainText.error`` code -> user-facing pt-BR message (anything else, and the
#: ``vazio`` code, falls back to :data:`MSG_UNREADABLE`).
_EXTRACT_ERRORS = {
    "formato_invalido": MSG_BAD_FORMAT,
    "encoding": MSG_BAD_ENCODING,
    "docx_ilegivel": MSG_DOCX_UNREADABLE,
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def _safe_name(filename: str) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return (_UNSAFE.sub("_", base).strip("._") or "arquivo")[:120]


def _display_name(filename: str) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (base or "arquivo")[:200]


def sniff_matches_extension(content: bytes, ext: str) -> bool:
    """Cheap synchronous check that the bytes are what the extension claims
    (the deep parse happens in the background job)."""
    if ext == "pdf":
        return content.startswith(b"%PDF")
    if ext == "docx":
        return content.startswith(b"PK\x03\x04")
    return not content.startswith((b"%PDF", b"PK\x03\x04")) and b"\x00" not in content


class CerebroFontesService:
    def __init__(
        self, db, org_id: str, user_id: Optional[str] = None,
        storage: Optional[StorageBackend] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.storage = storage
        self.brains = CerebroService(db, org_id, user_id, storage)

    # ── file import (endpoint 14) ───────────────────────────────────────

    async def start_file_import(
        self, brain_id: str, filename: str, content: bytes
    ) -> dict[str, Any]:
        """Validate, retain the original, and create the ``processing`` row.
        Raises ``CerebroError`` (404/413/415/422/502)."""
        brain = self.brains.get_brain_row(brain_id)
        name = _display_name(filename)
        if _ext(name) not in ALLOWED_EXTENSIONS:
            raise CerebroError(415, MSG_BAD_FORMAT)
        if not content:
            raise CerebroError(422, "O arquivo está vazio.")
        if len(content) > MAX_FILE_BYTES:
            raise CerebroError(413, "O arquivo excede o limite de 20 MB.")
        if not sniff_matches_extension(content, _ext(name)):
            raise CerebroError(415, MSG_BAD_FORMAT)
        if self.storage is None:
            raise RuntimeError("storage backend not configured")
        key = (
            f"{self.org_id}/{brain['marca_id']}/{brain_id}/files/"
            f"{uuid.uuid4().hex}-{_safe_name(name)}"
        )
        try:
            await self.storage.put(
                bucket=CEREBRO_BUCKET, key=key, data=content,
                content_type="application/octet-stream",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a typed 502, nothing recorded
            logger.error("cerebro: storing import for brain %s failed: %s", brain_id, exc)
            raise CerebroError(502, "Não foi possível salvar o arquivo. Tente novamente.") from exc
        rows = self.db.table(IMPORTS).insert({
            "id": str(uuid.uuid4()), "org_id": self.org_id, "brain_id": brain_id, "kind": "file",
            "filename": name, "storage_path": key, "size_bytes": len(content),
            "status": "processing", "created_by": self.user_id,
        }).execute().data
        return import_dict(rows[0])

    def _finish_import(self, import_id: str, patch: dict[str, Any]) -> None:
        self.db.table(IMPORTS).update({**patch, "updated_at": _iso()}).eq("id", import_id).eq(
            "org_id", self.org_id
        ).eq("status", "processing").execute()

    async def run_file_import(
        self, import_id: str, brain_id: str, filename: str, content: bytes,
        transcriber: Optional[DocumentTranscriber] = None,
    ) -> None:
        """Background job: text -> header block -> ``cs_brain_append``. Never
        raises; every outcome lands on the import row (a stranded
        ``processing`` is swept to ``error`` by ``sweep_stale``)."""
        try:
            plain = await extract_plain_text(content, filename, transcriber=transcriber)
            if not plain.ok or not plain.text.strip():
                msg = _EXTRACT_ERRORS.get(plain.error or "", MSG_UNREADABLE)
                self._finish_import(import_id, {"status": "error", "error_message": msg})
                return
            block = f"{block_header('Arquivo', filename)}\n\n{plain.text.strip()}"
            try:
                self.brains.append_block(brain_id, block)
            except CerebroError as exc:
                self._finish_import(import_id, {"status": "error", "error_message": exc.detail})
                return
            self._finish_import(
                import_id, {"status": "appended", "chars_appended": len(block), "error_message": None}
            )
        except Exception as exc:  # noqa: BLE001 - background job: record, never raise
            logger.exception("cerebro: file import %s failed: %s", import_id, exc)
            try:
                self._finish_import(import_id, {"status": "error", "error_message": MSG_IMPORT_FAILED})
            except Exception as inner:  # noqa: BLE001
                logger.error("cerebro: could not record import failure %s: %s", import_id, inner)

    # ── extractions (endpoints 19-24) ───────────────────────────────────

    def _extraction_row(self, extraction_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(EXTRACTIONS).select(EXTRACTION_COLS)
            .eq("id", extraction_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise CerebroError(404, "Extração não encontrada")
        return rows[0]

    def _targets_of(self, extraction_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {e: [] for e in extraction_ids}
        for chunk in batched(sorted(extraction_ids)):
            def page(start: int, end: int, _chunk=chunk):
                return (
                    self.db.table(TARGETS).select("extraction_id,brain_id,applied_at")
                    .eq("org_id", self.org_id).in_("extraction_id", _chunk)
                    .order("brain_id").range(start, end).execute().data
                )
            for row in iter_paged_rows(page, page_size=PAGE_SIZE, label=TARGETS):
                out.setdefault(row["extraction_id"], []).append(row)
        names: dict[str, str] = {}
        brain_ids = sorted({t["brain_id"] for ts in out.values() for t in ts})
        for chunk in batched(brain_ids):
            for b in (
                self.db.table(BRAINS).select("id,name")
                .eq("org_id", self.org_id).in_("id", chunk).execute().data
            ) or []:
                names[b["id"]] = b["name"]
        return {
            eid: [
                {"brain_id": t["brain_id"], "brain_name": names.get(t["brain_id"], ""),
                 "applied_at": t.get("applied_at")}
                for t in ts
            ]
            for eid, ts in out.items()
        }

    @staticmethod
    def _summary_of(row: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": row["id"], "marca_id": row["marca_id"], "name": row["name"],
            "source_kind": row["source_kind"], "source_url": row.get("source_url"),
            "status": row["status"], "error_message": row.get("error_message"),
            "targets": targets, "created_at": row.get("created_at"),
        }

    def _detail(self, row: dict[str, Any]) -> dict[str, Any]:
        targets = self._targets_of([row["id"]])[row["id"]]
        return {**self._summary_of(row, targets), "transcript": row.get("transcript")}

    def _validate_brains(self, marca_id: str, brain_ids: list[str]) -> list[str]:
        """Every target must be a brain of THIS marca (and org); otherwise 422."""
        wanted = list(dict.fromkeys(brain_ids))
        found: set[str] = set()
        for chunk in batched(sorted(wanted)):
            for r in (
                self.db.table(BRAINS).select("id")
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .in_("id", chunk).execute().data
            ) or []:
                found.add(r["id"])
        if found != set(wanted):
            raise CerebroError(422, "Escolha apenas cérebros desta marca.")
        return wanted

    def create_extraction(
        self, marca_id: str, name: str, brain_ids: list[str],
        text: Optional[str], url: Optional[str],
    ) -> dict[str, Any]:
        self.brains.assert_marca(marca_id)
        if url is not None:
            # NOC-REMEDIATE[extraction-by-url]: phase 2 (cerebro-contract.md §10.3) — needs
            # a downloader with SSRF guards + a security review. -- 2026-10-09
            raise CerebroError(422, MSG_URL_UNAVAILABLE)
        if not (text or "").strip():
            raise CerebroError(422, "Cole o texto da extração.")
        targets = self._validate_brains(marca_id, brain_ids)
        row = self.db.table(EXTRACTIONS).insert({
            "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
            "name": name, "source_kind": "text", "transcript": text, "status": "ready",
            "created_by": self.user_id,
        }).execute().data[0]
        self.db.table(TARGETS).insert([
            {"extraction_id": row["id"], "brain_id": b, "org_id": self.org_id} for b in targets
        ]).execute()
        return self._detail(row)

    def list_extractions(
        self, marca_id: str, *, q: Optional[str], limit: int, offset: int
    ) -> dict[str, Any]:
        self.brains.assert_marca(marca_id)

        def page(start: int, end: int):
            return (
                self.db.table(EXTRACTIONS).select(EXTRACTION_COLS.replace(",transcript", ""))
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .order("id").range(start, end).execute().data
            )
        rows = list(iter_paged_rows(page, page_size=PAGE_SIZE, label=EXTRACTIONS))
        needle = (q or "").strip().lower()
        if needle:
            rows = [r for r in rows if needle in (r.get("name") or "").lower()]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        total = len(rows)
        window = rows[offset: offset + limit]
        targets = self._targets_of([r["id"] for r in window]) if window else {}
        return {
            "items": [self._summary_of(r, targets.get(r["id"], [])) for r in window],
            "total": total,
        }

    def get_extraction(self, extraction_id: str) -> dict[str, Any]:
        return self._detail(self._extraction_row(extraction_id))

    def update_extraction(
        self, extraction_id: str, *, name: Optional[str], transcript: Optional[str],
        brain_ids: Optional[list[str]],
    ) -> dict[str, Any]:
        row = self._extraction_row(extraction_id)
        patch: dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if transcript is not None:
            if row["status"] not in ("ready", "applied"):
                raise CerebroError(409, "A transcrição ainda não está pronta para edição.")
            if not transcript.strip():
                raise CerebroError(422, "A transcrição não pode ficar vazia.")
            patch["transcript"] = transcript
        if brain_ids is not None:
            wanted = self._validate_brains(row["marca_id"], [str(b) for b in brain_ids])
            current = {
                t["brain_id"]: t for t in self._targets_of([extraction_id])[extraction_id]
            }
            for b, t in current.items():
                # an applied target stays (its text is already in the brain)
                if b not in wanted and not t["applied_at"]:
                    self.db.table(TARGETS).delete().eq("extraction_id", extraction_id).eq(
                        "brain_id", b
                    ).eq("org_id", self.org_id).execute()
            fresh = [b for b in wanted if b not in current]
            if fresh:
                self.db.table(TARGETS).insert([
                    {"extraction_id": extraction_id, "brain_id": b, "org_id": self.org_id}
                    for b in fresh
                ]).execute()
            if row["status"] == "applied" and fresh:
                patch["status"] = "ready"
        if patch:
            patch["updated_at"] = _iso()
            res = (
                self.db.table(EXTRACTIONS).update(patch)
                .eq("id", extraction_id).eq("org_id", self.org_id).execute().data
            )
            row = res[0] if res else {**row, **patch}
        return self._detail(row)

    def apply_extraction(
        self, extraction_id: str, brain_ids: Optional[list[str]]
    ) -> dict[str, int]:
        """Append the transcript to each requested (default: unapplied) target.
        Idempotent per target: ``applied_at`` is claimed BEFORE the append, so a
        repeat or concurrent apply skips it; a failed append releases the claim."""
        row = self._extraction_row(extraction_id)
        if row["status"] not in ("ready", "applied"):
            raise CerebroError(409, "A extração ainda não está pronta para aplicar.")
        transcript = (row.get("transcript") or "").strip()
        if not transcript:
            raise CerebroError(422, "A extração não tem texto para aplicar.")
        targets = {t["brain_id"]: t for t in self._targets_of([extraction_id])[extraction_id]}
        if brain_ids is None:
            chosen = [b for b, t in targets.items() if not t["applied_at"]]
        else:
            chosen = list(dict.fromkeys(str(b) for b in brain_ids))
            if any(b not in targets for b in chosen):
                raise CerebroError(422, "Escolha apenas cérebros que são destinos desta extração.")
        block = f"{block_header('Extração', row['name'])}\n\n{transcript}"
        applied = skipped = 0
        for b in chosen:
            claimed = (
                self.db.table(TARGETS).update({"applied_at": _iso()})
                .eq("extraction_id", extraction_id).eq("brain_id", b)
                .eq("org_id", self.org_id).is_("applied_at", "null").execute().data
            )
            if not claimed:
                skipped += 1
                continue
            try:
                self.brains.append_block(b, block)
            except Exception:
                self.db.table(TARGETS).update({"applied_at": None}).eq(
                    "extraction_id", extraction_id
                ).eq("brain_id", b).eq("org_id", self.org_id).execute()
                raise
            applied += 1
        remaining = (
            self.db.table(TARGETS).select("brain_id")
            .eq("extraction_id", extraction_id).eq("org_id", self.org_id)
            .is_("applied_at", "null").execute().data
        ) or []
        if not remaining and row["status"] != "applied":
            self.db.table(EXTRACTIONS).update({"status": "applied", "updated_at": _iso()}).eq(
                "id", extraction_id
            ).eq("org_id", self.org_id).execute()
        return {"applied": applied, "skipped": skipped}

    def delete_extraction(self, extraction_id: str) -> None:
        self._extraction_row(extraction_id)
        self.db.table(EXTRACTIONS).delete().eq("id", extraction_id).eq("org_id", self.org_id).execute()
