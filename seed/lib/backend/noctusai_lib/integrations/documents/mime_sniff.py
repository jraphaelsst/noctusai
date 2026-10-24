"""Content-derived MIME sniffing — the declared type is a claim, not a fact.

FINDING (live prod P2 test, 2026-09-30): an upload named `*.jpg` (declared
`image/jpeg`) was actually a PDF. `documents.ladder.looks_like_pdf` trusted
the declared mimetype/filename, so it skipped the free text-layer rung and
forwarded the PDF bytes downstream tagged as an image — the vision call then
failed outright (`LLMAPIError: 400 invalid_request_error — Could not process
image`), and the document died in `erro` instead of being read.

This module is the fix: a cheap magic-byte check that answers "what do the
first few BYTES actually say this is", independent of anything the uploader
claimed. `DocumentTextLadder.to_text` consults it before routing and, on a
mismatch, logs an aviso and uses the SNIFFED type for both (a) the
text-layer/vision routing decision and (b) the mimetype it forwards to the
media resolver — so a mislabelled upload is read as what it actually is, not
misrouted a second time downstream.

Deliberately narrow: only the signatures this package needs to tell a PDF
from an image apart (the case that crashes when confused) plus the sibling
image formats the identity-document pipeline already accepts — not a
general-purpose file-type sniffer. Pure, dependency-free, bytes-only; `None`
means "no opinion", never "unknown format error".
"""
from __future__ import annotations

from typing import Optional

#: `ftyp` brand codes that mean HEIC/HEIF, checked after the `ftyp` box
#: header at bytes 4-8. Covers Apple's default photo format (`heic`) and its
#: sequence/image-collection variants.
_HEIC_FTYP_BRANDS = frozenset({
    b"heic", b"heix", b"heim", b"heis",
    b"hevc", b"hevx", b"hevm", b"hevs",
    b"mif1", b"msf1",
})


def sniff_real_mimetype(content: bytes) -> Optional[str]:
    """Return the mimetype the BYTES themselves claim, or `None`.

    `None` means "no opinion" — the caller keeps trusting the declared
    mimetype/filename exactly as it did before this function existed. A
    concrete return is strong enough evidence to override the declared type
    outright (see `documents.ladder.DocumentTextLadder.to_text`).
    """
    if not content:
        return None
    head = content[:16]
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in _HEIC_FTYP_BRANDS:
        return "image/heic"
    return None


#: Leading bytes of executables/scripts. A document upload carrying these is
#: refused whatever it declares (declared pdf + exe bytes must not pass).
_EXECUTABLE_MAGICS = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")

_EXTENSION_BY_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


def resolve_upload_mimetype(declared: Optional[str], content: bytes) -> str:
    """The mimetype an upload should be validated AND stored under.

    Content wins over the declaration: a generic/missing declared type is
    replaced by the sniffed one, and a declared type the bytes contradict is
    replaced too (same rule as `DocumentTextLadder.to_text`). When the bytes
    are executable/script content the result is `application/octet-stream`
    so any document allowlist refuses it, even if a document type such as
    `application/pdf` was declared (other declared types are kept as-is). Unrecognised bytes keep the declared type (no opinion).
    """
    norm = (declared or "").split(";")[0].strip().lower()
    sniffed = sniff_real_mimetype(content)
    if sniffed:
        return sniffed
    if content.startswith(_EXECUTABLE_MAGICS) and (not norm or norm in _EXTENSION_BY_MIME):
        return "application/octet-stream"
    return norm or "application/octet-stream"


def ensure_extension(filename: str, mimetype: str) -> str:
    """Give an extension-less display name the extension matching `mimetype`.

    Extractors/readers may route by filename; a name with an extension is
    left untouched.
    """
    ext = _EXTENSION_BY_MIME.get(mimetype)
    name = filename or "arquivo"
    if not ext:
        return name
    base = name.rsplit("/", 1)[-1]
    if "." in base.strip("."):
        return name
    return f"{name}{ext}"


__all__ = ["sniff_real_mimetype", "resolve_upload_mimetype", "ensure_extension"]
