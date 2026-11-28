"""The property-video lifecycle of the YouTube module (owner 2026-11-28, julia-videos-prontos-youtube S2b):

* a Drive-folder fan-out records each video's Drive file id (`upload_jobs.source_file_id`);
* the opt-in `skip_published_for_product` never re-uploads a file already PUBLISHED for the org + product code
  (same Drive id AND same size); a re-edit is uploaded;
* `ProductVideoLifecycle.supersede_previous` sets private the previous published video(s) of the SAME kind, never the
  new ones, tolerates a YouTube refusal (recorded, never raised).

`gdown` is an external library: the fake module installed in `sys.modules` is the external-boundary seam (the same
shape as test_gdrive_service). No guard of ours is patched.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.modules.youtube.schemas.upload import UploadMetadata
from app.modules.youtube.services.upload import UploadService, UploadServiceError
from app.modules.youtube.services.video_lifecycle import (
    RESULT_PRIVATE, RESULT_REFUSED, ProductVideoLifecycle,
)
from app.modules.youtube.services.youtube import YouTubeServiceError
from app.services import gdrive_service

FOLDER = "https://drive.google.com/drive/folders/1abc23DEF456ghi789JKL012mno345PQ"
ORG = uuid4()


def _metadata(code: str = "ONE10898") -> UploadMetadata:
    return UploadMetadata(title=f"{code} video", description="d", tags=[], privacy_status="public", category_id="22",
                          notify_recipients=[], product_code=code)


def _install_gdown(monkeypatch, files: list[tuple[str, str, bytes]], *, listing_fails: bool = False) -> None:
    """files = (drive id, relpath, content). `skip_download=True` lists without writing (gdown's own contract)."""

    def download_folder(*, id, output, quiet, skip_download=False, **_kw):
        root = Path(output) / "drive-folder-root"
        if skip_download:
            if listing_fails:
                raise RuntimeError("listing unavailable")
            return [types.SimpleNamespace(id=fid, path=rel, local_path=str(root / rel)) for fid, rel, _ in files]
        out = []
        for _fid, rel, content in files:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            out.append(str(target))
        return out

    monkeypatch.setitem(sys.modules, "gdown", types.SimpleNamespace(download_folder=download_folder))


class _Query:
    def __init__(self, db: "_FakeDb") -> None:
        self.db, self.filters, self.payload, self.op = db, [], None, "select"

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.filters.append((col, {val}))
        return self

    def in_(self, col, vals):
        self.filters.append((col, set(vals)))
        return self

    def execute(self):
        if self.op == "insert":
            row = {"id": str(uuid4()), **self.payload}
            self.db.rows.append(row)
            return types.SimpleNamespace(data=[row])
        hits = [r for r in self.db.rows if all(r.get(c) in vals for c, vals in self.filters)]
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
        return types.SimpleNamespace(data=[dict(r) for r in hits])


class _FakeDb:
    """`upload_jobs` in memory (the supabase-py chain UploadService uses)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def schema(self, _name):
        return self

    def table(self, _name):
        return _Query(self)


def _service(tmp_path: Path) -> tuple[UploadService, _FakeDb]:
    db = _FakeDb()
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return UploadService(user_supabase=db, admin_supabase=db, upload_dir=upload_dir, youtube_service=object()), db


# ─── Drive file ids ─────────────────────────────────────────────────────────
class TestDriveFileIds:
    def test_iter_folder_ties_each_file_to_its_drive_id(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10), ("ID_S", "Shorts/s.mp4", b"y" * 20)])
        refs = gdrive_service.iter_drive_folder_videos(folder_url=FOLDER, target_dir=tmp_path)
        assert {r.file_name: r.drive_file_id for r in refs} == {"h.mp4": "ID_H", "s.mp4": "ID_S"}

    def test_unreadable_listing_is_loud_and_leaves_ids_unknown(self, monkeypatch, tmp_path, caplog):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x")], listing_fails=True)
        refs = gdrive_service.iter_drive_folder_videos(folder_url=FOLDER, target_dir=tmp_path)
        assert [r.drive_file_id for r in refs] == [None]
        assert any("file ids" in r.getMessage() for r in caplog.records)

    def test_fanout_records_source_file_id(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10)])
        svc, db = _service(tmp_path)
        lote = svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(), drive_folder_url=FOLDER)
        assert len(lote.children) == 1 and lote.skipped == []
        assert db.rows[0]["source_file_id"] == "ID_H" and db.rows[0]["file_size_bytes"] == 10


# ─── skip_published_for_product ─────────────────────────────────────────────
class TestSkipPublished:
    def _publicado(self, db: _FakeDb, file_id: str, size: int, *, status: str = "published", code: str = "ONE10898"):
        db.rows.append({"id": str(uuid4()), "org_id": str(ORG), "product_code": code, "status": status,
                        "source_file_id": file_id, "file_size_bytes": size, "youtube_video_id": f"yt_{file_id}",
                        "target_format": "youtube"})

    def test_same_file_already_published_is_skipped(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10), ("ID_N", "novo.mp4", b"n" * 5)])
        svc, db = _service(tmp_path)
        self._publicado(db, "ID_H", 10)
        lote = svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(), drive_folder_url=FOLDER,
                                             skip_published_for_product=True)
        assert [c.file_name for c in lote.children] == ["novo.mp4"]
        assert [(s.file_name, s.drive_file_id, s.youtube_video_id) for s in lote.skipped] == [("h.mp4", "ID_H", "yt_ID_H")]

    def test_every_file_published_returns_an_empty_batch_and_inserts_nothing(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10)])
        svc, db = _service(tmp_path)
        self._publicado(db, "ID_H", 10, status="notified")
        antes = len(db.rows)
        lote = svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(), drive_folder_url=FOLDER,
                                             skip_published_for_product=True)
        assert lote.children == [] and len(lote.skipped) == 1
        assert len(db.rows) == antes

    @pytest.mark.parametrize("caso", ["outro_tamanho", "falhou", "outro_imovel"])
    def test_not_the_same_published_file_is_uploaded(self, monkeypatch, tmp_path, caso):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10)])
        svc, db = _service(tmp_path)
        if caso == "outro_tamanho":  # the same Drive file replaced by a new version (a re-edit)
            self._publicado(db, "ID_H", 999)
        elif caso == "falhou":
            self._publicado(db, "ID_H", 10, status="failed")
        else:
            self._publicado(db, "ID_H", 10, code="CA2411")
        lote = svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(), drive_folder_url=FOLDER,
                                             skip_published_for_product=True)
        assert len(lote.children) == 1 and lote.skipped == []

    def test_default_never_skips(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x" * 10)])
        svc, db = _service(tmp_path)
        self._publicado(db, "ID_H", 10)
        lote = svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(), drive_folder_url=FOLDER)
        assert len(lote.children) == 1

    def test_skip_requires_a_product_code(self, monkeypatch, tmp_path):
        _install_gdown(monkeypatch, [("ID_H", "h.mp4", b"x")])
        svc, _ = _service(tmp_path)
        with pytest.raises(UploadServiceError, match="product_code"):
            svc.queue_drive_folder_upload(org_id=ORG, created_by=None, metadata=_metadata(""), drive_folder_url=FOLDER,
                                          skip_published_for_product=True)


# ─── supersede_previous ─────────────────────────────────────────────────────
class _Lookup:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def list_jobs(self, code):
        return [r for r in self.rows if r["product_code"] == code]


class _YouTube:
    def __init__(self, recusar: set[str] = frozenset()) -> None:
        self.chamadas: list[tuple[str, str]] = []
        self.recusar = set(recusar)

    def update_video_metadata(self, *, org_id, video_id, privacy_status=None):
        if video_id in self.recusar:
            raise YouTubeServiceError("404 videoNotFound")
        self.chamadas.append((video_id, privacy_status))


class _Catalog:
    def __init__(self, falha: bool = False) -> None:
        self.patches: list[tuple[str, dict]] = []
        self.falha = falha

    def mirror_update(self, video_id, patch):
        if self.falha:
            raise RuntimeError("db down")
        self.patches.append((video_id, patch))


def _job(vid: str, fmt: str, *, status: str = "published", privacy: str = "public", jid: str | None = None) -> dict:
    return {"id": jid or f"job_{vid}", "product_code": "ONE10898", "youtube_video_id": vid, "target_format": fmt,
            "status": status, "privacy_status": privacy}


class TestSupersede:
    def _ciclo(self, rows, yt=None, catalog=None):
        return ProductVideoLifecycle(org_id=ORG, jobs=_Lookup(rows), youtube=yt or _YouTube(), catalog=catalog or _Catalog())

    def test_only_the_same_kind_and_never_the_new_ones(self):
        novo = _job("novo_h", "youtube")
        rows = [novo, _job("velho_h", "youtube"), _job("velho_s", "shorts"), _job("ja_priv", "youtube", privacy="private"),
                _job("falhou", "youtube", status="failed")]
        yt, cat = _YouTube(), _Catalog()
        out = self._ciclo(rows, yt, cat).supersede_previous(product_code="ONE10898", new_jobs=[novo])
        assert yt.chamadas == [("velho_h", "private")]
        assert cat.patches == [("velho_h", {"privacy_status": "private"})]
        assert [(o.youtube_video_id, o.upload_job_id, o.result) for o in out] == [("velho_h", "job_velho_h", RESULT_PRIVATE)]

    def test_shorts_supersede_shorts_only_and_ignore_extras(self):
        novo = _job("novo_s", "shorts")
        yt = _YouTube()
        out = self._ciclo([novo, _job("velho_h", "youtube"), _job("velho_s", "shorts")], yt).supersede_previous(
            product_code="ONE10898", new_jobs=[novo], extra_video_ids=["VISTA123456"])
        assert yt.chamadas == [("velho_s", "private")] and len(out) == 1

    def test_extra_standard_video_and_refusal_recorded(self):
        novo = _job("novo_h", "youtube")
        yt = _YouTube(recusar={"VISTA123456"})
        out = self._ciclo([novo], yt).supersede_previous(product_code="ONE10898", new_jobs=[novo],
                                                          extra_video_ids=["VISTA123456", "novo_h"])
        assert [(o.youtube_video_id, o.result, o.error, o.source) for o in out] == [
            ("VISTA123456", RESULT_REFUSED, "YouTubeServiceError", "extra")]

    def test_extra_already_covered_or_private_is_not_called_twice(self):
        novo = _job("novo_h", "youtube")
        yt = _YouTube()
        self._ciclo([novo, _job("velho_h", "youtube"), _job("priv", "youtube", privacy="private")], yt).supersede_previous(
            product_code="ONE10898", new_jobs=[novo], extra_video_ids=["velho_h", "priv"])
        assert yt.chamadas == [("velho_h", "private")]

    def test_nothing_published_supersedes_nothing(self):
        yt = _YouTube()
        assert self._ciclo([_job("velho_h", "youtube")], yt).supersede_previous(
            product_code="ONE10898", new_jobs=[{"id": "x", "youtube_video_id": None, "target_format": "youtube"}]) == []
        assert yt.chamadas == []

    def test_catalog_mirror_failure_is_flagged_not_raised(self, caplog):
        novo = _job("novo_h", "youtube")
        out = self._ciclo([novo, _job("velho_h", "youtube")], catalog=_Catalog(falha=True)).supersede_previous(
            product_code="ONE10898", new_jobs=[novo])
        assert out[0].ok and out[0].mirror_ok is False
        assert any("catalog mirror failed" in r.getMessage() for r in caplog.records)
