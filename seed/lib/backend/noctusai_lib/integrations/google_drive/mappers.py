"""Pure functions for Google Drive — URL → file id extraction.

Drive surfaces file ids in several URL shapes depending on the entry
point. Consumers should call `parse_drive_url(...)` rather than hand-
rolling a regex; the mapper accepts every shape we've seen in the wild
and a bare id as a defensive fallback.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# Drive file ids are URL-safe base64 (`[A-Za-z0-9_-]+`), typically 28-44
# chars long but unbounded in spec. We require ≥20 to filter out tiny
# strings that happen to match the alphabet (e.g. "id" alone).
_DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_FILE_PATH_RE = re.compile(r"^/file/d/([A-Za-z0-9_-]+)")
_DRIVE_HOSTS = frozenset({"drive.google.com", "docs.google.com"})


def parse_drive_url(url_or_id: str) -> str:
    """Extract a file id from a Drive URL or accept a bare id.

    Supported shapes:
    - `https://drive.google.com/file/d/{id}/view`
    - `https://drive.google.com/file/d/{id}/edit`
    - `https://drive.google.com/file/d/{id}/`
    - `https://drive.google.com/open?id={id}`
    - `https://drive.google.com/uc?id={id}`
    - `https://drive.google.com/uc?export=download&id={id}`
    - `https://docs.google.com/document/d/{id}/...`
    - bare file id (≥20 chars from `[A-Za-z0-9_-]`)

    Raises `ValueError` when the input is neither a recognized Drive URL
    nor a plausible bare id."""
    s = (url_or_id or "").strip()
    if not s:
        raise ValueError("empty input")

    # Bare id fast-path.
    if _DRIVE_ID_RE.match(s):
        return s

    parsed = urlparse(s)
    if parsed.netloc not in _DRIVE_HOSTS:
        raise ValueError(f"not a google drive URL: {url_or_id!r}")

    # /file/d/{id}/... and /document/d/{id}/...
    for prefix in ("/file/d/", "/document/d/", "/spreadsheets/d/", "/presentation/d/"):
        if parsed.path.startswith(prefix):
            tail = parsed.path[len(prefix) :]
            file_id = tail.split("/", 1)[0]
            if _DRIVE_ID_RE.match(file_id):
                return file_id
            break

    # /file/d/{id}/... (legacy regex path; kept for any path we missed above)
    m = _FILE_PATH_RE.search(parsed.path)
    if m and _DRIVE_ID_RE.match(m.group(1)):
        return m.group(1)

    # ?id={id}
    qs = parse_qs(parsed.query)
    candidates = qs.get("id") or []
    if candidates and _DRIVE_ID_RE.match(candidates[0]):
        return candidates[0]

    raise ValueError(f"could not extract file id from drive URL: {url_or_id!r}")


__all__ = ["parse_drive_url"]
