"""Pure URL mappers.

`parse_drive_url` mirrors `noctusai_lib.integrations.google_drive.parse_drive_url`:
accepts the common Drive URL shapes (and bare ids) and returns the id.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# /file/d/<id>/...  or  /folders/<id>  or  /d/<id>
_PATH_ID = re.compile(r"/(?:file/d|folders|d)/([A-Za-z0-9_-]+)")
_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def parse_drive_url(url_or_id: str) -> str:
    """Extract the Drive file/folder id from a URL or a bare id.

    Handles: /file/d/{id}/..., /folders/{id}, /d/{id}, open?id={id},
    uc?id={id}, uc?export=download&id={id}, and bare ids.

    Raises ValueError when no id can be found.
    """
    candidate = url_or_id.strip()
    if _BARE_ID.match(candidate):
        return candidate

    parsed = urlparse(candidate)
    m = _PATH_ID.search(parsed.path)
    if m:
        return m.group(1)

    qs = parse_qs(parsed.query)
    if "id" in qs and qs["id"]:
        return qs["id"][0]

    raise ValueError(f"Could not parse a Drive id from: {url_or_id!r}")


def is_folder_url(url: str) -> bool:
    """True if the URL points at a Drive folder (vs a single file)."""
    return "/folders/" in url or "/drive/folders/" in url


__all__ = ["parse_drive_url", "is_folder_url"]
