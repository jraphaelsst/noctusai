"""In-memory deterministic FakeDriveDownloader for dev + tests.

Seed-data shape: a dict of `file_id → (DriveFile, bytes)`. Tests use
`add_fake_file(...)` to populate fixtures inline:

```python
fake = FakeDriveDownloader()
fake.add_fake_file("xyz", "clip.mp4", b"<video bytes>", "video/mp4")
await fake.download("xyz", tmp_path / "clip.mp4")
```

`download(...)` writes the seeded bytes to disk verbatim — exercising
the file-write side effect that consumers depend on, while skipping the
googleapiclient transport.
"""

from __future__ import annotations

from pathlib import Path

from noctusai_lib.integrations.google_drive.types import DriveFile


class FakeDriveDownloader:
    """Deterministic in-memory `DriveDownloader` implementation."""

    def __init__(
        self,
        files: dict[str, tuple[DriveFile, bytes]] | None = None,
    ) -> None:
        self._files: dict[str, tuple[DriveFile, bytes]] = dict(files or {})

    def add_fake_file(
        self,
        file_id: str,
        name: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        md5_checksum: str | None = None,
    ) -> DriveFile:
        """Seed a file. Returns the `DriveFile` for caller convenience."""
        meta = DriveFile(
            id=file_id,
            name=name,
            size_bytes=len(content),
            mime_type=mime_type,
            md5_checksum=md5_checksum,
        )
        self._files[file_id] = (meta, content)
        return meta

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        entry = self._files.get(file_id)
        return entry[0] if entry else None

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        entry = self._files.get(file_id)
        if entry is None:
            raise FileNotFoundError(
                f"drive file {file_id!r} not in fake — call add_fake_file(...) first"
            )
        meta, content = entry
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return meta


__all__ = ["FakeDriveDownloader"]
