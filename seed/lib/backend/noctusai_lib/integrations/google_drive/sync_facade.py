"""Sync facade over the async `DriveReader` Protocol.

Built for sync FastAPI consumers (the absorbed `social-wiring`
`drive_api/` surface was sync because its consumer methods originally
ran inside sync handlers + `asyncio.to_thread`). The facade absorbs
the `asyncio.run` / `asyncio.run_coroutine_threadsafe` boilerplate so
consumer code reads like the absorbed product without losing the
async Protocol underneath.

Decision (2026-05-19, Phase 6a-drive): we ship BOTH the async
Protocol (canonical) and this sync wrapper rather than forcing one
shape on every consumer. Async-native consumers (the social-wiring
chatbot intake methods, which are already `async def`) `await
reader.search(...)` directly; sync consumers
(`SyncDriveReader(reader).search(...)`) avoid hand-rolled
`asyncio.to_thread` glue.

The facade detects whether a loop is already running:

- No running loop (the common sync-handler case) → `asyncio.run(...)`
  drives the coroutine to completion.
- A loop IS running on this thread (someone called us from `async
  def`) → run the coroutine on a fresh background loop in a worker
  thread (avoids the `RuntimeError: This event loop is already
  running` trap).

This dual mode is the same shape `Anthropic.run_sync` / `httpx.Client`
use; consumers don't have to know which mode they're in.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from noctusai_lib.integrations.google_drive.reader_types import (
    DriveFileContent,
    DriveReader,
    DriveSearchHit,
    DriveSearchResult,
)


def _drive_sync(coro: Any) -> Any:
    """Drive an awaitable to completion from a sync caller.

    Handles both "no loop on this thread" (normal sync-handler call;
    use `asyncio.run`) and "loop already running" (called from inside
    an `async def`; run the coro on a fresh loop in a worker thread)
    transparently."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop on this thread — safe to use asyncio.run.
        return asyncio.run(coro)

    # A loop IS running — can't reuse it; spin a worker thread that
    # owns a fresh loop and run the coroutine there. This keeps the
    # facade callable from anywhere without surprising the caller.
    def _runner() -> Any:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_runner).result()


class SyncDriveReader:
    """Sync wrapper over a `DriveReader`.

    Construct with any `DriveReader` (Fake or Real) and call the same
    method names sync — `search` / `list_recent` / `get_file` /
    `read_file`. The async-vs-sync split stays a consumer choice; both
    shapes share the same enriched value objects."""

    def __init__(self, reader: DriveReader) -> None:
        self._reader = reader

    @property
    def reader(self) -> DriveReader:
        """The wrapped async reader — handy for tests or for handing
        off to async-native code paths."""
        return self._reader

    def search(
        self,
        query: str,
        *,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> DriveSearchResult:
        return _drive_sync(
            self._reader.search(
                query,
                mime_type=mime_type,
                folder_id=folder_id,
                page_size=page_size,
            )
        )

    def list_recent(self, *, page_size: int = 20) -> DriveSearchResult:
        return _drive_sync(self._reader.list_recent(page_size=page_size))

    def get_file(self, file_id: str) -> DriveSearchHit | None:
        return _drive_sync(self._reader.get_file(file_id))

    def read_file(
        self, file_id: str, *, max_bytes: int = 200_000
    ) -> DriveFileContent | None:
        return _drive_sync(self._reader.read_file(file_id, max_bytes=max_bytes))


def make_sync_drive_reader(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
) -> SyncDriveReader:
    """Convenience factory — `make_drive_reader(...)` + sync wrap."""
    from noctusai_lib.integrations.google_drive.reader_factory import (
        make_drive_reader,
    )

    return SyncDriveReader(
        make_drive_reader(
            use_fake=use_fake,
            api_key=api_key,
            oauth_credentials=oauth_credentials,
        )
    )


__all__ = ["SyncDriveReader", "make_sync_drive_reader"]
