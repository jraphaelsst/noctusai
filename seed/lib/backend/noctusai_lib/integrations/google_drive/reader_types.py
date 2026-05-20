"""Google Drive v3 *read/inspection* value objects + Protocol.

Reconciled 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E3
from the live-validated workspace package
`youtube-crawler/app/services/drive_api/`
(`reference/.promotions/drive-api-client.md`,
`SESSION-NOTES_drive-api-2026-05-13.md`).

Enriched 2026-05-19 by `social-wiring-google-seed-consume` Phase 6a-drive
(projection-enrichment): the original `DriveSearchHit` was a narrower
projection than the absorbed product's `DriveFile` (missing
`parents`/`owners`/`icon_link`/`is_folder`/`raw`; `id` vs `file_id`
rename; `modified_time: str` vs `modified_at: datetime`). The enriched
shape adds the missing fields as ADDITIVE back-compat-defaulted
attributes + derived properties — every prior consumer keeps working
unchanged; new consumers read the enriched fields. The
`absorbed-product-seed-shape-seam` pattern: defaults reproduce today,
projection upgrades the seed never degrade the consumer.

WHY a sibling surface (not a change to `DriveDownloader`)
---------------------------------------------------------
The existing `DriveDownloader` Protocol (download-to-disk for the
youtube-crawler upload pipeline) is a different operation from the
chatbot's *inspect-my-Drive* surface (search / list / metadata /
read-content-for-the-LLM). They have different return shapes and
different consumers. Per `protocol.py`'s own note ("Drive supports
many more endpoints … out of scope until the second consumer
arrives — add to the Protocol then"), the second consumer has now
arrived (social-wiring chatbot Drive tools). We add a SECOND
Protocol (`DriveReader`) in the SAME package rather than overloading
the download contract — both ship Fake+Real+factory.

`read_file` returns raw exported bytes + a `rendered_as` hint, NOT
extracted PDF/Docx text. PDF→text / video-keyframe extraction is
owned by the multimodal `media` seam (Wave 1.E5) — keeping this
module dependency-light (no PyMuPDF/pdfminer import at module level).
The `DriveFileContent.text` convenience property routes PDF bytes
through `noctusai_lib.integrations.media.extract_pdf_text` lazily so
consumers can read `content.text` uniformly without importing the
heavy deps at module-load time. Sheets→CSV and Docs→text/plain ARE
done here because they are Drive `files.export` MIME selections, not
content parsing.

Rendered-as vocabulary
----------------------
Both vocabularies are accepted (translation layer):

- Seed canonical: `"text/csv"` / `"text/plain"` / `"passthrough"` /
  `"binary"` (Drive MIME-aligned; what the Real adapter emits).
- Product legacy (post-absorb consumer migration): `"csv"` / `"text"`
  / `"pdf-text"` / `"binary"` (chatbot-tool-description aligned).

The `RENDERED_AS_CANONICAL` / `RENDERED_AS_LEGACY` constants + the
`translate_rendered_as(...)` helper let consumers/tests map between
them without silent surprises. Default emission stays canonical
(`"text/csv"` / `"text/plain"` / `"passthrough"` / `"binary"`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path  # noqa: F401 — re-export convenience for consumers
from typing import Any, Protocol


# ─── Rendered-as vocabulary constants + translation ──────────────────────

#: Canonical seed vocabulary (Drive-MIME aligned; what `RealDriveReader`
#: emits and what every NEW consumer should match against).
RENDERED_AS_CSV = "text/csv"
RENDERED_AS_TEXT = "text/plain"
RENDERED_AS_PASSTHROUGH = "passthrough"
RENDERED_AS_BINARY = "binary"
RENDERED_AS_PDF_TEXT = "pdf-text"
"""Set by `DriveFileContent.text` (and consumers calling
`extract_pdf_text(...)`) AFTER lifting a PDF binary to extracted text;
the underlying `rendered_as` on emission from the seed Real adapter is
still `"binary"` because the seed module doesn't import PyMuPDF."""

RENDERED_AS_CANONICAL = (
    RENDERED_AS_CSV,
    RENDERED_AS_TEXT,
    RENDERED_AS_PASSTHROUGH,
    RENDERED_AS_BINARY,
    RENDERED_AS_PDF_TEXT,
)
"""All canonical vocabulary values."""

#: Legacy product vocabulary (the absorbed `drive_api` surface used
#: shorthand labels for chatbot-tool descriptions). Translation layer
#: maps both directions so existing tool-description strings continue
#: matching on consumer-side reads of `rendered_as`.
_LEGACY_TO_CANONICAL = {
    "csv": RENDERED_AS_CSV,
    "text": RENDERED_AS_TEXT,
    "pdf-text": RENDERED_AS_PDF_TEXT,
    "binary": RENDERED_AS_BINARY,
}
_CANONICAL_TO_LEGACY = {
    RENDERED_AS_CSV: "csv",
    RENDERED_AS_TEXT: "text",
    RENDERED_AS_PASSTHROUGH: "text",  # passthrough is consumed as plain text
    RENDERED_AS_PDF_TEXT: "pdf-text",
    RENDERED_AS_BINARY: "binary",
}


def translate_rendered_as(label: str, *, to: str = "canonical") -> str:
    """Translate a `rendered_as` label between vocabularies.

    `to="canonical"`: map a legacy label (`"csv"`, `"text"`,
    `"pdf-text"`) to its canonical equivalent (`"text/csv"`,
    `"text/plain"`, `"pdf-text"`). Already-canonical labels
    pass through unchanged. Unknown labels pass through verbatim
    (no silent drop).

    `to="legacy"`: inverse — map canonical → legacy. Useful when
    feeding a tool description that was authored against the legacy
    vocabulary.
    """
    if to == "canonical":
        return _LEGACY_TO_CANONICAL.get(label, label)
    if to == "legacy":
        return _CANONICAL_TO_LEGACY.get(label, label)
    raise ValueError(f"translate_rendered_as: unknown to={to!r}")


# ─── Folder MIME + content-decode helpers ────────────────────────────────

FOLDER_MIME = "application/vnd.google-apps.folder"
"""Drive's special MIME for folder rows (used by `DriveSearchHit.is_folder`)."""

_TEXTUAL_PASSTHROUGH_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/csv",
)


def _parse_modified_time(value: Any) -> datetime | None:
    """Parse a Drive `modifiedTime` ISO-8601 string to `datetime`.

    Returns `None` on failure (not raising) because `modified_at` is
    a convenience for consumers — broken-clock files shouldn't crash
    the search call."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ─── Value objects ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriveSearchHit:
    """One result row from a Drive search / list call.

    `capabilities` surfaces the Drive `capabilities` sub-object
    (`canDownload`, `canEdit`, ...) so a consumer can distinguish
    "permission denied" from "no tool" from "404" — the gotcha from
    the drive-api session note (a shared spreadsheet looked
    inaccessible but actually had `canDownload: true`; the real issue
    was the bot lacked a read tool).

    Enriched fields (2026-05-19): `parents`, `owners`, `icon_link`,
    `raw` are additive with empty defaults so existing constructors /
    serializers keep working. `file_id` is an alias property for `id`
    (the absorbed product used `file_id`); `modified_at` is a
    derived property that parses `modified_time` to `datetime` on
    demand. `is_folder` derives from `mime_type == FOLDER_MIME`."""

    id: str
    name: str
    mime_type: str
    modified_time: str | None = None
    size_bytes: int | None = None
    web_view_link: str | None = None
    """The Drive UI URL. Treated as IMMUTABLE — see the LLM-URL-rewrite
    gotcha (`SESSION-NOTES_google-integrations-2026-05-12.md` §3): an
    LLM that inserts `/u/0/` or rewrites the domain breaks the link
    (Google returns 400). Consumers surfacing this to an LLM MUST
    instruct it to copy the value verbatim."""
    capabilities: dict[str, Any] = field(default_factory=dict)
    parents: list[str] = field(default_factory=list)
    """Drive folder ids this file lives under (Drive supports multi-parent
    historically, but in practice today each file has at most one parent).
    Empty list when the API didn't return parents (e.g. trashed files,
    permission-restricted projections)."""
    owners: list[str] = field(default_factory=list)
    """Owner identifiers — email addresses when available, else display
    names — flattened from the Drive `owners[]` sub-object. Empty when
    the API didn't return owners (anyone-with-link API-key auth)."""
    icon_link: str | None = None
    """URL to the small Drive icon for this file's type — handy for
    chatbot UI rendering."""
    raw: dict[str, Any] = field(default_factory=dict)
    """Full Drive response body, preserved verbatim. Forward-compat
    escape hatch: consumers needing a field the seed doesn't yet
    surface read from `raw[...]` without waiting for a seed re-ship."""

    # ─── Derived properties — additive, no constructor change ────────

    @property
    def file_id(self) -> str:
        """Alias for `id` — matches the absorbed product's field name
        so post-migration consumer code can read `hit.file_id`
        identically to the pre-migration `DriveFile.file_id`."""
        return self.id

    @property
    def modified_at(self) -> datetime | None:
        """`modified_time` parsed to `datetime` — convenience for
        consumers that prefer typed dates over ISO strings."""
        return _parse_modified_time(self.modified_time)

    @property
    def is_folder(self) -> bool:
        """True when `mime_type == FOLDER_MIME`. Derived (not stored)
        so the constructor surface stays unchanged."""
        return self.mime_type == FOLDER_MIME


@dataclass(frozen=True)
class DriveSearchResult:
    hits: list[DriveSearchHit]
    next_page_token: str | None = None

    @property
    def files(self) -> list[DriveSearchHit]:
        """Alias for `hits` — matches the absorbed product's field
        name (`DriveSearchResult.files`). Post-migration consumers can
        read `result.files` identically to the pre-migration shape."""
        return self.hits


@dataclass(frozen=True)
class DriveFileContent:
    """The content of a Drive file as exported/streamed bytes.

    `rendered_as` tells the consumer how `data` was produced so it can
    decide how to decode / extract:

    - `"text/csv"`      — Google Sheets exported to CSV (UTF-8 text)
    - `"text/plain"`    — Google Docs exported to plain text (UTF-8)
    - `"passthrough"`   — TXT / CSV / JSON streamed verbatim
    - `"binary"`        — PDF / DOCX / image / video etc. — NOT decoded
                          here by default; the `.text` property routes
                          PDF bytes through
                          `noctusai_lib.integrations.media.extract_pdf_text`
                          lazily; other binaries return `""`.
    - `"pdf-text"`      — set by a consumer that already extracted PDF
                          text and wants to record the post-extraction
                          rendered_as for downstream tooling.

    Enriched fields (2026-05-19): `text` / `bytes_read` / `raw_mime` /
    `is_truncated` are convenience properties derived from `data` +
    `rendered_as`. Empty constructor surface unchanged — existing
    tests / Fake bodies that pass `data=...` keep working; new
    consumers read `.text` for decoded content."""

    file_id: str
    name: str
    mime_type: str
    rendered_as: str
    data: bytes
    truncated: bool = False
    """True when `max_bytes` clipped the payload (large sheets/docs).
    Consumers should tell the LLM the data is partial so it doesn't
    over-claim completeness."""
    raw_mime: str | None = None
    """The MIME the bytes are encoded as (export target for native
    types, or the original `mime_type` for binary streams). Set
    explicitly by the Real adapter; defaults to `mime_type` when
    omitted."""

    # ─── Derived properties — additive, no constructor change ────────

    @property
    def is_truncated(self) -> bool:
        """Alias for `truncated` — matches the absorbed product's
        field name."""
        return self.truncated

    @property
    def bytes_read(self) -> int:
        """Byte length of `data` — the absorbed product reported this
        explicitly; here it's derived (no storage cost)."""
        return len(self.data)

    @property
    def text(self) -> str:
        """Decoded text payload.

        Routing:

        - `text/csv` / `text/plain` / `passthrough` / `pdf-text` →
          UTF-8 decode (the bytes are already text per `rendered_as`).
        - `binary` + `mime_type == "application/pdf"` → lazy
          `noctusai_lib.integrations.media.extract_pdf_text(data)`.
          Returns `""` when PyMuPDF/pdfminer are unavailable (slim
          envs); consumers can `is_pdf_text_supported()`-gate if they
          need to distinguish.
        - any other `binary` → `""` (defer to `media` seam).
        """
        if self.rendered_as in (
            RENDERED_AS_CSV,
            RENDERED_AS_TEXT,
            RENDERED_AS_PASSTHROUGH,
            RENDERED_AS_PDF_TEXT,
        ):
            try:
                return self.data.decode("utf-8", errors="replace")
            except Exception:
                return ""
        if self.rendered_as == RENDERED_AS_BINARY and self.mime_type == "application/pdf":
            # Lazy import — keeps `reader_types` PyMuPDF-free; consumers in
            # slim envs without PyMuPDF/pdfminer get `""` (the function's
            # documented degraded mode), never a crash.
            try:
                from noctusai_lib.integrations.media import extract_pdf_text
            except ImportError:
                return ""
            try:
                return extract_pdf_text(self.data) or ""
            except Exception:
                return ""
        return ""


class DriveReader(Protocol):
    """Drive v3 read/inspection contract.

    Concrete impls in this package: `FakeDriveReader` (deterministic
    in-memory dev/test default) + `RealDriveReader` (googleapiclient,
    service-account OR OAuth creds). Build via `make_drive_reader(...)`.

    Auth-agnostic like `DriveDownloader`: the Real adapter takes
    either an `api_key` (anyone-with-link) OR `oauth_credentials`
    (private files). The recommended quick-start for new products is
    the *share-the-folder-with-the-service-account email* path — no
    GCP redirect-URI registration, the SA sees whatever is shared
    recursively (drive-api session note §2)."""

    async def search(
        self,
        query: str,
        *,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> DriveSearchResult:
        """Name + full-text search. `query` is matched against file
        name AND content; `mime_type` / `folder_id` narrow it."""
        ...

    async def list_recent(self, *, page_size: int = 20) -> DriveSearchResult:
        """Most-recently-modified files the credentials can see."""
        ...

    async def get_file(self, file_id: str) -> DriveSearchHit | None:
        """Metadata-only lookup (incl. `capabilities`). `None` when the
        file doesn't exist OR the creds can't see it (Drive returns 404
        for both, by design — don't leak existence)."""
        ...

    async def read_file(
        self, file_id: str, *, max_bytes: int = 200_000
    ) -> DriveFileContent | None:
        """Fetch a file's content. Google-native types are exported
        (Sheets→CSV, Docs→text/plain); other types stream verbatim and
        carry `rendered_as="passthrough"` (text) or `"binary"` (defer
        extraction to the `media` seam). Clips at `max_bytes`. `None`
        when the file is missing/inaccessible."""
        ...


__all__ = [
    "DriveSearchHit",
    "DriveSearchResult",
    "DriveFileContent",
    "DriveReader",
    "FOLDER_MIME",
    "RENDERED_AS_CSV",
    "RENDERED_AS_TEXT",
    "RENDERED_AS_PASSTHROUGH",
    "RENDERED_AS_BINARY",
    "RENDERED_AS_PDF_TEXT",
    "RENDERED_AS_CANONICAL",
    "translate_rendered_as",
]
