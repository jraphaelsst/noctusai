"""Knowledge-bundle JSONL parsing + validation (contract §B.6).

A bundle line has the shape:

    {"path": "<repo-relative path>", "git_sha": "...", "git_author_raw": "...",
     "git_committed_at": "...", "git_message": "...", "content": "<file text at that commit>"}

``parse_bundle_lines`` turns raw JSONL text/bytes into a list of
``BundleLine``, enforcing, in order:

1. the size cap (422-class ``BundleTooLarge`` — 20 MB or 5,000 lines),
2. per-line shape (422-class ``BundleInvalid`` — malformed JSON or a
   missing/non-string required field),
3. the path denylist (``SecretDetected(path)`` — ``.env*``, ``*.pem``,
   ``*.key``, ``id_rsa*``, ``*secret*``, ``credentials*``, ``.npmrc``),
4. the content secret scan (``SecretDetected(path)``, via
   ``secrets.scan_content`` — same class as the denylist since both are
   the contract's single 422 ``secret_detected`` outcome).
"""
from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.importer.secrets import scan_content

MAX_BUNDLE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_BUNDLE_LINES = 5000

_REQUIRED_FIELDS: tuple[str, ...] = (
    "path",
    "git_sha",
    "git_author_raw",
    "git_committed_at",
    "git_message",
    "content",
)

# Contract §B.6 refusal list. Checked against both the basename and the
# full path (lower-cased) so a nested ``config/.env.production`` or
# ``secrets/foo.txt`` is caught, not just a root-level file.
_PATH_DENYLIST_PATTERNS: tuple[str, ...] = (
    ".env*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "*secret*",
    "credentials*",
    ".npmrc",
)


class BundleInvalid(Exception):
    """A bundle line is malformed or missing a required field (422)."""


class BundleTooLarge(Exception):
    """The bundle exceeds the 20 MB / 5,000-line cap (422)."""


class SecretDetected(Exception):
    """A bundle line's path matched the denylist, or its content tripped
    the secret scan (422 ``secret_detected``). Carries the offending
    PATH only — never the value.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"secret detected at path: {path}")


@dataclass(frozen=True, slots=True)
class BundleLine:
    """One parsed + validated bundle line."""

    path: str
    git_sha: str
    git_author_raw: str
    git_committed_at: str
    git_message: str
    content: str

    @property
    def git_committed_at_dt(self) -> datetime:
        """``git_committed_at`` parsed to an aware ``datetime``."""
        return datetime.fromisoformat(self.git_committed_at.replace("Z", "+00:00"))


def path_is_denylisted(path: str) -> bool:
    """True if ``path`` matches the §B.6 path denylist."""
    basename = os.path.basename(path).lower()
    full = path.lower()
    for pattern in _PATH_DENYLIST_PATTERNS:
        if fnmatch.fnmatch(basename, pattern):
            return True
        if fnmatch.fnmatch(full, pattern) or fnmatch.fnmatch(full, f"*/{pattern}"):
            return True
    return False


def _split_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def parse_bundle_lines(raw: str | bytes) -> list[BundleLine]:
    """Parse + validate a full JSONL bundle. Raises on the first
    violation found (size cap, shape, denylist, or content secret scan).
    """
    if isinstance(raw, bytes):
        if len(raw) > MAX_BUNDLE_BYTES:
            raise BundleTooLarge(
                f"bundle is {len(raw)} bytes, exceeds the {MAX_BUNDLE_BYTES}-byte cap"
            )
        text = raw.decode("utf-8")
    else:
        text = raw
        encoded_len = len(text.encode("utf-8"))
        if encoded_len > MAX_BUNDLE_BYTES:
            raise BundleTooLarge(
                f"bundle is {encoded_len} bytes, exceeds the {MAX_BUNDLE_BYTES}-byte cap"
            )

    raw_lines = _split_lines(text)
    if len(raw_lines) > MAX_BUNDLE_LINES:
        raise BundleTooLarge(
            f"bundle has {len(raw_lines)} lines, exceeds the {MAX_BUNDLE_LINES}-line cap"
        )

    parsed: list[BundleLine] = []
    for i, raw_line in enumerate(raw_lines):
        try:
            obj: Any = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise BundleInvalid(f"line {i}: invalid JSON ({exc})") from exc

        if not isinstance(obj, dict):
            raise BundleInvalid(f"line {i}: expected a JSON object")

        missing = [f for f in _REQUIRED_FIELDS if f not in obj]
        if missing:
            raise BundleInvalid(f"line {i}: missing field(s) {missing}")

        for field_name in _REQUIRED_FIELDS:
            if not isinstance(obj[field_name], str):
                raise BundleInvalid(
                    f"line {i}: field {field_name!r} must be a string"
                )

        line = BundleLine(**{f: obj[f] for f in _REQUIRED_FIELDS})

        if path_is_denylisted(line.path):
            raise SecretDetected(line.path)
        if scan_content(line.content):
            raise SecretDetected(line.path)

        parsed.append(line)

    return parsed
