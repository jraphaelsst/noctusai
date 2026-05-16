"""Google Drive read/inspection surface tests — Fake + content stats.

The Real adapter wraps googleapiclient and is exercised by the same
mocked-transport approach as the existing download tests; here we
cover the Fake (the dev/test default consumers actually inject) +
`compute_content_stats` (the LLM-counting-trap fix) deterministically,
network-free.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.google_drive import (
    DriveFileContent,
    DriveSearchHit,
    FakeDriveReader,
    compute_content_stats,
    make_drive_reader,
)


@pytest.fixture
def reader() -> FakeDriveReader:
    r = FakeDriveReader()
    r.add_file(
        "sheet1",
        "Cronograma One",
        b"Data,Ref,Corretor\n2026-01-01,ONE5597,Joao\n2026-01-02,ONE5876,Ana\n",
        mime_type="application/vnd.google-apps.spreadsheet",
        rendered_as="text/csv",
        modified_time="2026-05-13T10:00:00Z",
    )
    r.add_file(
        "doc1",
        "Notas",
        b"linha um\nlinha dois\n",
        mime_type="text/plain",
        modified_time="2026-05-12T10:00:00Z",
    )
    return r


class TestFakeDriveReaderSearch:
    @pytest.mark.asyncio
    async def test_search_by_name(self, reader: FakeDriveReader) -> None:
        res = await reader.search("cronograma")
        assert len(res.hits) == 1
        assert res.hits[0].id == "sheet1"

    @pytest.mark.asyncio
    async def test_search_empty_returns_all(self, reader: FakeDriveReader) -> None:
        res = await reader.search("")
        assert len(res.hits) == 2

    @pytest.mark.asyncio
    async def test_search_mime_filter(self, reader: FakeDriveReader) -> None:
        res = await reader.search("", mime_type="text/plain")
        assert [h.id for h in res.hits] == ["doc1"]


class TestFakeDriveReaderListAndGet:
    @pytest.mark.asyncio
    async def test_list_recent_orders_by_modified_desc(
        self, reader: FakeDriveReader
    ) -> None:
        res = await reader.list_recent()
        assert [h.id for h in res.hits] == ["sheet1", "doc1"]

    @pytest.mark.asyncio
    async def test_get_file_found(self, reader: FakeDriveReader) -> None:
        hit = await reader.get_file("sheet1")
        assert isinstance(hit, DriveSearchHit)
        assert hit.capabilities.get("canDownload") is True

    @pytest.mark.asyncio
    async def test_get_file_missing_returns_none(
        self, reader: FakeDriveReader
    ) -> None:
        assert await reader.get_file("nope") is None


class TestFakeDriveReaderReadFile:
    @pytest.mark.asyncio
    async def test_read_file_returns_content(
        self, reader: FakeDriveReader
    ) -> None:
        content = await reader.read_file("sheet1")
        assert isinstance(content, DriveFileContent)
        assert content.rendered_as == "text/csv"
        assert content.truncated is False
        assert b"ONE5597" in content.data

    @pytest.mark.asyncio
    async def test_read_file_truncates(self, reader: FakeDriveReader) -> None:
        content = await reader.read_file("sheet1", max_bytes=10)
        assert content is not None
        assert content.truncated is True
        assert len(content.data) == 10

    @pytest.mark.asyncio
    async def test_read_missing_returns_none(
        self, reader: FakeDriveReader
    ) -> None:
        assert await reader.read_file("nope") is None


class TestMakeDriveReaderFactory:
    def test_use_fake(self) -> None:
        assert isinstance(make_drive_reader(use_fake=True), FakeDriveReader)

    def test_real_requires_creds(self) -> None:
        with pytest.raises(ValueError, match="api_key or oauth_credentials"):
            make_drive_reader()


class TestComputeContentStats:
    def test_csv_shape(self) -> None:
        text = "Data,Ref,Corretor\n2026-01-01,ONE5597,Joao\n2026-01-02,ONE5876,Ana\n"
        stats = compute_content_stats(text, rendered_as="text/csv")
        assert stats["total_lines"] == 3
        assert stats["non_empty_lines"] == 3
        assert stats["csv_column_count"] == 3
        assert stats["csv_data_rows"] == 2
        assert stats["csv_header"] == "Data,Ref,Corretor"

    def test_plain_text_no_csv_keys(self) -> None:
        stats = compute_content_stats("a\nb\n\nc\n", rendered_as="text/plain")
        assert stats["total_lines"] == 4
        assert stats["non_empty_lines"] == 3
        assert "csv_data_rows" not in stats

    def test_counts_match_python_ground_truth(self) -> None:
        # The exact failure mode from the session note: an LLM said 35
        # for a payload whose true line count differs. Deterministic
        # Python is the oracle.
        body = "h\n" + "\n".join(f"row{i},ONE{i}" for i in range(183)) + "\n"
        stats = compute_content_stats(body, rendered_as="text/csv")
        assert stats["total_lines"] == 184
        assert stats["csv_data_rows"] == 183
