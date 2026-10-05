"""Parse a design-system FOLDER (as a flat list of files) into a branding bundle.

The import path accepts the folder exactly as the Branding Template and the
imported design systems lay it out::

    tokens.json                     required — validated by :mod:`.tokens_schema`
    README.md                       the brand book (markdown)
    design-system.json              optional — only its ``title`` (default name)
    sections/<NN-name>.md           extra brand-book sections (title = first H1)
    components/<Name>/README.md     the component guideline (markdown)
    components/<Name>/preview.html  the preview (validated by :mod:`.html_guard`)
    assets/Logos/<file>             logos        -> reference kind ``logo``
    assets/References/<file>        post models  -> reference kind ``model``
    assets/<Group>/README.md        group notes  -> an extra section
    fonts/<file>                    font files   -> reference kind ``font``

Anything else (``source/**`` dumps, ``.DS_Store``) is NOT imported and is
REPORTED in ``ignored`` — never dropped silently. A browser folder picker
prefixes every path with the picked folder's name; that single common prefix is
stripped when ``tokens.json`` is not at the root.

Binary assets are checked by MAGIC BYTES (the file's own bytes decide its type,
never the name or a declared MIME) and size-capped; SVG is deliberately not
accepted (it can carry script and is opened directly from storage).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.modules.media_creation.branding.html_guard import (
    PreviewHtmlRejected,
    validate_preview_html,
)
from app.modules.media_creation.branding.tokens_schema import (
    TokensValidationError,
    validate_tokens,
)

MAX_FILES = 400
MAX_ASSETS = 80
MAX_ASSET_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_COMPONENTS = 60
MAX_SECTIONS = 40

COMPONENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")

#: ``assets/<Group>`` folder name (case-insensitive) -> reference ``kind``.
ASSET_GROUP_KIND = {"logos": "logo", "references": "model", "fonts": "font"}

_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "image"),
    (b"\xff\xd8\xff", "image/jpeg", "image"),
    (b"GIF87a", "image/gif", "image"),
    (b"GIF89a", "image/gif", "image"),
    (b"wOF2", "font/woff2", "font"),
    (b"wOFF", "font/woff", "font"),
    (b"OTTO", "font/otf", "font"),
    (b"\x00\x01\x00\x00", "font/ttf", "font"),
    (b"true", "font/ttf", "font"),
)


class BundleError(ValueError):
    """The bundle is not importable; ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def sniff_asset(data: bytes) -> tuple[str, str] | None:
    """Return ``(content_type, family)`` (family: image|font) or ``None``."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "image"
    for magic, ctype, family in _MAGIC:
        if data.startswith(magic):
            return ctype, family
    return None


@dataclass(frozen=True)
class ParsedComponent:
    name: str
    guideline_md: str
    preview_html: str
    position: int


@dataclass(frozen=True)
class ParsedAsset:
    kind: str          # logo | model | font
    label: str         # the file name
    content_type: str
    data: bytes
    group: str


@dataclass
class ParsedBundle:
    name: str
    tokens: dict[str, Any]
    brand_book: str = ""
    sections: list[dict[str, str]] = field(default_factory=list)
    components: list[ParsedComponent] = field(default_factory=list)
    assets: list[ParsedAsset] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("/"):
        raise BundleError([f"unsafe path {path!r}"])
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise BundleError([f"unsafe path {path!r}"])
    return "/".join(parts)


def _strip_common_prefix(paths: list[str]) -> dict[str, str]:
    if "tokens.json" in paths:
        return {p: p for p in paths}
    first = {p.split("/", 1)[0] for p in paths}
    if len(first) == 1 and all("/" in p for p in paths):
        prefix = next(iter(first)) + "/"
        return {p: p[len(prefix):] for p in paths}
    return {p: p for p in paths}


def _text(path: str, data: bytes, errors: list[str]) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"{path}: not valid UTF-8 text")
        return ""
    if len(text) > MAX_TEXT_CHARS:
        errors.append(f"{path}: larger than {MAX_TEXT_CHARS} characters")
        return ""
    return text


def _section_title(file_name: str, text: str) -> str:
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if m:
        return m.group(1)[:200]
    stem = file_name.rsplit(".", 1)[0]
    return re.sub(r"^\d+[-_ ]*", "", stem).replace("-", " ").replace("_", " ").strip().title()[:200] or stem


def parse_bundle(files: Iterable[tuple[str, bytes]]) -> ParsedBundle:
    """Parse ``(relative_path, bytes)`` pairs; raise :class:`BundleError`."""
    errors: list[str] = []
    raw: dict[str, bytes] = {}
    for path, data in files:
        norm = _norm(path)
        if not norm:
            continue
        if norm in raw:
            errors.append(f"duplicate file {norm!r}")
        raw[norm] = data
    if len(raw) > MAX_FILES:
        raise BundleError([f"too many files ({len(raw)} > {MAX_FILES})"])
    mapping = _strip_common_prefix(sorted(raw))
    rel = {mapping[p]: raw[p] for p in raw}

    if "tokens.json" not in rel:
        raise BundleError(["tokens.json is required at the root of the design-system folder"])

    bundle = ParsedBundle(name="", tokens={})
    ignored: list[str] = []

    # tokens ------------------------------------------------------------
    try:
        parsed = json.loads(rel["tokens.json"].decode("utf-8"))
        bundle.tokens = validate_tokens(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"tokens.json: not valid JSON ({exc})")
    except TokensValidationError as exc:
        errors.append(f"tokens.json: {exc}")

    # default name ---------------------------------------------------------
    title = ""
    if "design-system.json" in rel:
        try:
            title = str(json.loads(rel["design-system.json"].decode("utf-8")).get("title") or "")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            errors.append("design-system.json: not valid JSON")
    bundle.name = (title or str(bundle.tokens.get("name") or "")).strip()

    if "README.md" in rel:
        bundle.brand_book = _text("README.md", rel["README.md"], errors)
    else:
        bundle.warnings.append("README.md is missing — the brand book will be empty")

    comp_files: dict[str, dict[str, bytes]] = {}
    sections: list[tuple[str, dict[str, str]]] = []
    asset_total = 0

    for path in sorted(rel):
        data = rel[path]
        parts = path.split("/")
        head = parts[0].lower()
        if path in ("tokens.json", "README.md", "design-system.json"):
            continue
        if head == "sections" and len(parts) == 2 and parts[1].lower().endswith(".md"):
            text = _text(path, data, errors)
            sections.append((parts[1], {"title": _section_title(parts[1], text), "markdown": text}))
        elif head == "components" and len(parts) == 3:
            comp_files.setdefault(parts[1], {})[parts[2]] = data
        elif head == "fonts" and len(parts) == 2:
            asset_total = _add_asset(bundle, errors, path, parts[1], "font", "Fonts", data, asset_total)
        elif head == "assets" and len(parts) == 3:
            group = parts[1]
            if parts[2].lower() == "readme.md":
                text = _text(path, data, errors)
                if text.strip():
                    sections.append((f"~{group}", {"title": f"Assets: {group}", "markdown": text}))
                continue
            kind = ASSET_GROUP_KIND.get(group.lower())
            if kind is None:
                errors.append(
                    f"{path}: unknown asset group {group!r} (accepted: Logos, References, Fonts)"
                )
                continue
            asset_total = _add_asset(bundle, errors, path, parts[2], kind, group, data, asset_total)
        else:
            ignored.append(path)

    # components --------------------------------------------------------
    for position, name in enumerate(sorted(comp_files)):
        if not COMPONENT_NAME.match(name):
            errors.append(f"components/{name}: invalid component name")
            continue
        files_in = comp_files[name]
        guideline = _text(f"components/{name}/README.md", files_in["README.md"], errors) if "README.md" in files_in else ""
        preview = ""
        if "preview.html" in files_in:
            preview = _text(f"components/{name}/preview.html", files_in["preview.html"], errors)
            try:
                if preview:
                    validate_preview_html(preview)
            except PreviewHtmlRejected as exc:
                errors.append(f"components/{name}/preview.html: {exc}")
        for other in sorted(set(files_in) - {"README.md", "preview.html"}):
            ignored.append(f"components/{name}/{other}")
        bundle.components.append(ParsedComponent(name, guideline, preview, position))
    if len(bundle.components) > MAX_COMPONENTS:
        errors.append(f"too many components ({len(bundle.components)} > {MAX_COMPONENTS})")

    sections.sort(key=lambda s: s[0])
    bundle.sections = [s for _, s in sections]
    if len(bundle.sections) > MAX_SECTIONS:
        errors.append(f"too many sections ({len(bundle.sections)} > {MAX_SECTIONS})")

    if len(bundle.assets) > MAX_ASSETS:
        errors.append(f"too many assets ({len(bundle.assets)} > {MAX_ASSETS})")

    declared = {f["file"].split("/")[-1] for f in bundle.tokens.get("type", {}).get("fonts", [])}
    present = {a.label for a in bundle.assets if a.kind == "font"}
    for missing in sorted(declared - present):
        bundle.warnings.append(
            f"tokens declare the font file {missing!r} but it is not in the bundle (preview falls back)"
        )

    bundle.ignored = ignored
    if not bundle.name:
        errors.append("no name: set design-system.json `title` or tokens.json `name`")
    if errors:
        raise BundleError(errors)
    return bundle


def _add_asset(
    bundle: ParsedBundle, errors: list[str], path: str, label: str,
    kind: str, group: str, data: bytes, total: int,
) -> int:
    if label.startswith(".") or label.lower().endswith((".md", ".txt")):
        bundle.ignored.append(path)
        return total
    if len(data) > MAX_ASSET_BYTES:
        errors.append(f"{path}: larger than {MAX_ASSET_BYTES // (1024 * 1024)} MB")
        return total
    sniffed = sniff_asset(data)
    if sniffed is None:
        errors.append(f"{path}: not a PNG/JPEG/WebP/GIF image or a WOFF/WOFF2/TTF/OTF font")
        return total
    ctype, family = sniffed
    if (kind == "font") != (family == "font"):
        errors.append(f"{path}: a {family} file cannot go in the {group!r} group")
        return total
    total += len(data)
    if total > MAX_TOTAL_ASSET_BYTES:
        errors.append(f"assets exceed {MAX_TOTAL_ASSET_BYTES // (1024 * 1024)} MB in total")
        return total
    bundle.assets.append(ParsedAsset(kind, label, ctype, data, group))
    return total
