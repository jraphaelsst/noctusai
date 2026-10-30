"""Brand upload intake — caps, magic bytes, SVG refusal (CONTRACT §3).

The declared content type and the filename are CLAIMS; the bytes decide. A file
is accepted only when its extension AND its leading bytes agree on one of the
allowed kinds. SVG is refused outright (script-capable XML), whatever it is
named. Filenames never reach a storage key: objects are stored under
``<org_id>/<identity_id>/<area>/<index>.<ext>``; the (sanitised) original name
is kept only as metadata.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from noctusai_lib.integrations.documents.mime_sniff import sniff_real_mimetype

MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_DESCRIPTION_CHARS = 2000
MAX_FONTS = 6
#: MaxBodySizeMiddleware ceilings (multipart framing slack on top of the file caps).
INGEST_BODY_LIMIT = MAX_TOTAL_BYTES + 1024 * 1024
ASSET_BODY_LIMIT = MAX_FILE_BYTES + 512 * 1024

KIND_MARKDOWN = "markdown"
KIND_PDF = "pdf"
KIND_IMAGE = "image"
KIND_FONT = "font"

_EXT_KIND = {
    ".md": (KIND_MARKDOWN, "text/markdown"),
    ".markdown": (KIND_MARKDOWN, "text/markdown"),
    ".pdf": (KIND_PDF, "application/pdf"),
    ".png": (KIND_IMAGE, "image/png"),
    ".jpg": (KIND_IMAGE, "image/jpeg"),
    ".jpeg": (KIND_IMAGE, "image/jpeg"),
    ".webp": (KIND_IMAGE, "image/webp"),
    ".woff2": (KIND_FONT, "font/woff2"),
}
_STORED_EXT = {"text/markdown": "md", "application/pdf": "pdf", "image/png": "png",
               "image/jpeg": "jpg", "image/webp": "webp", "font/woff2": "woff2"}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ \-]")
_SVG_HEAD_RE = re.compile(rb"^\s*(<\?xml|<!doctype\s+svg|<svg)", re.I)


class UploadRefused(ValueError):
    """A file (or the batch) was refused. ``codigo`` is a stable machine code."""

    def __init__(self, codigo: str, message: str) -> None:
        super().__init__(message)
        self.codigo = codigo
        self.message = message


@dataclass(frozen=True)
class AcceptedFile:
    index: int
    name: str          # sanitised original name (metadata only)
    kind: str
    mime: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def stored_ext(self) -> str:
        return _STORED_EXT[self.mime]


def safe_name(filename: Optional[str]) -> str:
    base = (filename or "arquivo").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _SAFE_NAME_RE.sub("_", base).strip(" .") or "arquivo"
    return cleaned[:120]


def _ext_of(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot >= 0 else ""


def classify(filename: Optional[str], data: bytes, *, index: int = 0) -> AcceptedFile:
    """Accept or refuse ONE file. Extension and bytes must agree."""
    name = safe_name(filename)
    ext = _ext_of(name)
    if ext == ".svg" or _SVG_HEAD_RE.match(data[:256] or b""):
        raise UploadRefused("svg_recusado", f"{name}: SVG não é aceito (envie PNG, JPG ou WEBP)")
    if not data:
        raise UploadRefused("arquivo_vazio", f"{name}: arquivo vazio")
    if len(data) > MAX_FILE_BYTES:
        raise UploadRefused("arquivo_grande", f"{name}: excede {MAX_FILE_BYTES // (1024 * 1024)} MB")
    spec = _EXT_KIND.get(ext)
    if spec is None:
        raise UploadRefused("tipo_nao_suportado", f"{name}: tipo não suportado")
    kind, mime = spec
    sniffed = sniff_real_mimetype(data)
    if kind == KIND_MARKDOWN:
        if sniffed is not None or b"\x00" in data:
            raise UploadRefused("conteudo_invalido", f"{name}: conteúdo não é texto")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRefused("conteudo_invalido", f"{name}: texto não está em UTF-8") from exc
    elif kind == KIND_FONT:
        if not data.startswith(b"wOF2"):
            raise UploadRefused("conteudo_invalido", f"{name}: não é uma fonte WOFF2")
    elif sniffed != mime:
        raise UploadRefused("conteudo_invalido", f"{name}: o conteúdo não corresponde à extensão")
    return AcceptedFile(index=index, name=name, kind=kind, mime=mime, data=data)


def check_batch(files: list[tuple[Optional[str], bytes]]) -> list[AcceptedFile]:
    if not files:
        raise UploadRefused("sem_arquivos", "Envie ao menos um arquivo")
    if len(files) > MAX_FILES:
        raise UploadRefused("arquivos_demais", f"No máximo {MAX_FILES} arquivos")
    total = sum(len(d) for _, d in files)
    if total > MAX_TOTAL_BYTES:
        raise UploadRefused("lote_grande", f"O total excede {MAX_TOTAL_BYTES // (1024 * 1024)} MB")
    accepted = [classify(n, d, index=i) for i, (n, d) in enumerate(files)]
    names = [a.name for a in accepted]
    if len(set(names)) != len(names):
        raise UploadRefused("nomes_repetidos", "Dois arquivos com o mesmo nome")
    return accepted


def parse_descriptions(raw: Optional[str], names: list[str]) -> dict[str, str]:
    """``descriptions`` form field: JSON map filename → text. Keys must name an
    uploaded file (sanitised name); values are bounded text."""
    import json

    if raw is None or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise UploadRefused("descricoes_invalidas", "descriptions: JSON inválido") from exc
    if not isinstance(data, dict):
        raise UploadRefused("descricoes_invalidas", "descriptions: deve ser um objeto nome→texto")
    out: dict[str, str] = {}
    known = set(names)
    for key, value in data.items():
        name = safe_name(str(key))
        if name not in known:
            raise UploadRefused("descricoes_invalidas", f"descriptions: {name!r} não corresponde a um arquivo enviado")
        if not isinstance(value, str) or len(value) > MAX_DESCRIPTION_CHARS:
            raise UploadRefused("descricoes_invalidas", f"descriptions: texto de {name!r} inválido ou longo demais")
        out[name] = value
    return out


async def read_capped(upload, cap: int = MAX_FILE_BYTES) -> bytes:
    """Read an UploadFile without trusting its declared size: at most ``cap + 1``."""
    data = await upload.read(cap + 1)
    if len(data) > cap:
        raise UploadRefused("arquivo_grande", f"{safe_name(upload.filename)}: excede {cap // (1024 * 1024)} MB")
    return data


# ── asset slot mapping (CONTRACT §4 step 4) ─────────────────────────────────

IMAGE_SLOTS = ("logo_light", "logo_dark", "logo_mark", "favicon")
ASSET_SLOTS = IMAGE_SLOTS + ("font",)

_SLOT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("favicon", ("favicon", "fav-icon")),
    ("logo_mark", ("mark", "simbolo", "símbolo", "icone", "ícone", "isotipo", "monograma")),
    ("logo_dark", ("dark", "escuro", "negativo", "negativa", "white", "branco", "branca")),
    ("logo_light", ("logo", "marca", "light", "claro", "positivo", "positiva")),
)


def slot_for_image(name: str, description: str = "") -> Optional[str]:
    """Deterministic slot from filename/description hints; ``None`` when no hint
    matches (the contract leaves such an image unassigned)."""
    hay = f"{name} {description}".lower()
    for slot, hints in _SLOT_HINTS:
        if any(h in hay for h in hints):
            return slot
    return None


def font_family_from_name(name: str) -> str:
    """A family label for an uploaded font file (``Lora-Regular.woff2`` → ``Lora``)."""
    stem = name.rsplit(".", 1)[0]
    stem = re.split(r"[-_](thin|light|regular|medium|semibold|bold|black|italic|\d{3})", stem, flags=re.I)[0]
    cleaned = re.sub(r"[^A-Za-z0-9 \-]", " ", stem).strip()
    return (re.sub(r"\s+", " ", cleaned) or "Brand Font")[:64]
