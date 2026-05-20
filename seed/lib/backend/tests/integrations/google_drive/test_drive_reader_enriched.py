"""Projection-enrichment tests for `DriveReader` (Phase 6a-drive
2026-05-19). Pin: enriched fields default to back-compat values + new
constructors / properties / sync facade behave correctly + Fake
mirrors Real."""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.google_drive import (
    FOLDER_MIME,
    RENDERED_AS_BINARY,
    RENDERED_AS_CSV,
    RENDERED_AS_PASSTHROUGH,
    RENDERED_AS_PDF_TEXT,
    RENDERED_AS_TEXT,
    DriveFileContent,
    DriveSearchHit,
    DriveSearchResult,
    FakeDriveReader,
    SyncDriveReader,
    make_sync_drive_reader,
    translate_rendered_as,
)


class TestEnrichedHitDefaults:
    def test_minimal_construction_still_works(self) -> None:
        """The original constructor surface (id/name/mime_type) still
        works; enriched fields default to empty collections / None."""
        hit = DriveSearchHit(id="x", name="n", mime_type="text/plain")
        assert hit.parents == []
        assert hit.owners == []
        assert hit.icon_link is None
        assert hit.raw == {}

    def test_file_id_alias(self) -> None:
        hit = DriveSearchHit(id="abc", name="n", mime_type="text/plain")
        assert hit.file_id == "abc"

    def test_modified_at_derived_property(self) -> None:
        hit = DriveSearchHit(
            id="x",
            name="n",
            mime_type="text/plain",
            modified_time="2026-05-19T12:34:56Z",
        )
        dt = hit.modified_at
        assert dt is not None
        assert dt.year == 2026 and dt.month == 5 and dt.day == 19

    def test_modified_at_returns_none_on_garbage(self) -> None:
        hit = DriveSearchHit(
            id="x", name="n", mime_type="text/plain", modified_time="not-a-date"
        )
        assert hit.modified_at is None

    def test_modified_at_none_when_missing(self) -> None:
        hit = DriveSearchHit(id="x", name="n", mime_type="text/plain")
        assert hit.modified_at is None

    def test_is_folder_derived(self) -> None:
        folder = DriveSearchHit(id="f", name="My Folder", mime_type=FOLDER_MIME)
        file_ = DriveSearchHit(id="d", name="doc", mime_type="text/plain")
        assert folder.is_folder is True
        assert file_.is_folder is False

    def test_enriched_fields_populate(self) -> None:
        hit = DriveSearchHit(
            id="x",
            name="n",
            mime_type="text/plain",
            parents=["p1", "p2"],
            owners=["a@b.com"],
            icon_link="https://drive.google.com/icon.png",
            raw={"size": "1024", "trashed": False},
        )
        assert hit.parents == ["p1", "p2"]
        assert hit.owners == ["a@b.com"]
        assert hit.icon_link == "https://drive.google.com/icon.png"
        assert hit.raw["trashed"] is False


class TestSearchResultFilesAlias:
    def test_files_alias_returns_hits(self) -> None:
        h = DriveSearchHit(id="x", name="n", mime_type="text/plain")
        res = DriveSearchResult(hits=[h])
        assert res.files is res.hits
        assert res.files[0].file_id == "x"


class TestEnrichedContentDefaults:
    def test_minimal_construction_still_works(self) -> None:
        c = DriveFileContent(
            file_id="x",
            name="n",
            mime_type="text/plain",
            rendered_as=RENDERED_AS_PASSTHROUGH,
            data=b"hi",
        )
        assert c.raw_mime is None
        assert c.is_truncated is False  # alias for truncated
        assert c.bytes_read == 2  # derived from len(data)

    def test_text_decodes_utf8_for_text_rendered_as(self) -> None:
        c = DriveFileContent(
            file_id="x",
            name="n",
            mime_type="text/csv",
            rendered_as=RENDERED_AS_CSV,
            data="Data,Ref\n1,ONE5597\n".encode("utf-8"),
        )
        assert "ONE5597" in c.text

    def test_text_returns_empty_for_unknown_binary(self) -> None:
        c = DriveFileContent(
            file_id="x",
            name="n",
            mime_type="video/mp4",
            rendered_as=RENDERED_AS_BINARY,
            data=b"\x00\x01\x02",
        )
        assert c.text == ""

    def test_text_returns_empty_for_binary_pdf_without_extractor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When PyMuPDF / pdfminer aren't importable, PDF .text degrades
        to empty string (documented contract) — never crashes."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[override]
            if name in ("fitz", "pdfminer", "pdfminer.high_level"):
                raise ImportError("simulated slim env")
            return real_import(name, *args, **kwargs)

        # External-boundary patch (the imports inside the lazy helper —
        # NOT our own code) is the legitimate use of monkeypatch.
        monkeypatch.setattr(builtins, "__import__", fake_import)
        c = DriveFileContent(
            file_id="x",
            name="n",
            mime_type="application/pdf",
            rendered_as=RENDERED_AS_BINARY,
            data=b"%PDF-fake",
        )
        # Should NOT crash; returns "".
        assert c.text == ""


class TestRenderedAsTranslation:
    @pytest.mark.parametrize(
        "legacy,canonical",
        [
            ("csv", RENDERED_AS_CSV),
            ("text", RENDERED_AS_TEXT),
            ("pdf-text", RENDERED_AS_PDF_TEXT),
            ("binary", RENDERED_AS_BINARY),
        ],
    )
    def test_legacy_to_canonical(self, legacy: str, canonical: str) -> None:
        assert translate_rendered_as(legacy, to="canonical") == canonical

    def test_unknown_passes_through(self) -> None:
        assert translate_rendered_as("mystery", to="canonical") == "mystery"

    def test_canonical_passthrough_to_legacy_text(self) -> None:
        assert translate_rendered_as(RENDERED_AS_PASSTHROUGH, to="legacy") == "text"

    def test_invalid_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown to="):
            translate_rendered_as(RENDERED_AS_CSV, to="garbage")


class TestFakeMirrorsEnrichedRealShape:
    """Pin: the Fake exposes the same enriched-field surface as the
    Real adapter (the `seed-Fake-mirrors-Real` rule)."""

    @pytest.mark.asyncio
    async def test_add_file_accepts_enriched_fields(self) -> None:
        fake = FakeDriveReader()
        hit = fake.add_file(
            "f1",
            "doc",
            b"hello",
            mime_type="text/plain",
            parents=["root"],
            owners=["a@b.com"],
            icon_link="https://icon",
        )
        assert hit.parents == ["root"]
        assert hit.owners == ["a@b.com"]
        assert hit.icon_link == "https://icon"

    @pytest.mark.asyncio
    async def test_read_file_populates_raw_mime(self) -> None:
        fake = FakeDriveReader()
        fake.add_file(
            "sheet",
            "S",
            b"a,b\n1,2\n",
            mime_type="application/vnd.google-apps.spreadsheet",
            rendered_as=RENDERED_AS_CSV,
            raw_mime="text/csv",
        )
        content = await fake.read_file("sheet")
        assert content is not None
        assert content.raw_mime == "text/csv"
        assert content.text == "a,b\n1,2\n"
        assert content.bytes_read == len(content.data)
        assert content.is_truncated is False

    @pytest.mark.asyncio
    async def test_folder_filter_uses_parents(self) -> None:
        fake = FakeDriveReader()
        fake.add_file("a", "doc-a", b"x", parents=["fold"])
        fake.add_file("b", "doc-b", b"y", parents=["other"])
        res = await fake.search("", folder_id="fold")
        assert [h.id for h in res.hits] == ["a"]


class TestSyncFacade:
    def test_make_sync_drive_reader_returns_wrapper(self) -> None:
        sync = make_sync_drive_reader(use_fake=True)
        assert isinstance(sync, SyncDriveReader)

    def test_sync_search_no_running_loop(self) -> None:
        fake = FakeDriveReader()
        fake.add_file("x", "Cronograma", b"data", mime_type="text/csv")
        sync = SyncDriveReader(fake)
        res = sync.search("cronograma")
        assert len(res.hits) == 1
        assert res.hits[0].file_id == "x"

    def test_sync_read_file_no_running_loop(self) -> None:
        fake = FakeDriveReader()
        fake.add_file("x", "n", b"payload", rendered_as=RENDERED_AS_PASSTHROUGH)
        sync = SyncDriveReader(fake)
        content = sync.read_file("x")
        assert content is not None
        assert content.text == "payload"

    def test_sync_get_file_missing_returns_none(self) -> None:
        sync = SyncDriveReader(FakeDriveReader())
        assert sync.get_file("nope") is None

    def test_sync_list_recent(self) -> None:
        fake = FakeDriveReader()
        fake.add_file(
            "old", "older", b"x", modified_time="2026-01-01T00:00:00Z"
        )
        fake.add_file(
            "new", "newer", b"y", modified_time="2026-05-19T00:00:00Z"
        )
        sync = SyncDriveReader(fake)
        res = sync.list_recent()
        assert [h.id for h in res.hits] == ["new", "old"]

    def test_sync_works_inside_running_loop(self) -> None:
        """When called from inside an async context, the facade must
        still complete (uses worker-thread fallback)."""
        fake = FakeDriveReader()
        fake.add_file("x", "n", b"payload")
        sync = SyncDriveReader(fake)

        async def _call_sync_from_async() -> int:
            res = sync.search("")
            return len(res.hits)

        count = asyncio.run(_call_sync_from_async())
        assert count == 1

    def test_reader_property_exposes_wrapped(self) -> None:
        fake = FakeDriveReader()
        sync = SyncDriveReader(fake)
        assert sync.reader is fake


class TestBackCompatExistingTests:
    """Pin: the original `test_drive_reader.py` invariants still
    hold (back-compat). Re-asserted here in addition to the original
    file to make the no-regression contract explicit."""

    @pytest.mark.asyncio
    async def test_existing_search_by_name_unchanged(self) -> None:
        r = FakeDriveReader()
        r.add_file(
            "sheet1",
            "Cronograma One",
            b"Data,Ref,Corretor\n2026-01-01,ONE5597,Joao\n",
            mime_type="application/vnd.google-apps.spreadsheet",
            rendered_as="text/csv",
        )
        res = await r.search("cronograma")
        assert len(res.hits) == 1
        assert res.hits[0].id == "sheet1"

    @pytest.mark.asyncio
    async def test_existing_truncation_still_works(self) -> None:
        r = FakeDriveReader()
        r.add_file("x", "n", b"0" * 1000)
        content = await r.read_file("x", max_bytes=10)
        assert content is not None
        assert content.truncated is True
        assert len(content.data) == 10
