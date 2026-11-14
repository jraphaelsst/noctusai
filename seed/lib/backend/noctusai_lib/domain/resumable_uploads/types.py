"""Value objects, policy and errors of the resumable-upload seam."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

__all__ = [
    "MIB", "STATUS_OPEN", "STATUS_COMPLETED", "STATUS_ABORTED", "STATUS_EXPIRED", "EVENT_KINDS",
    "UploadPolicy", "UploadSession", "PartInfo", "UploadError", "UploadNotFound", "UploadRejected",
    "UploadExpired", "UploadNotOpen", "PartInvalid", "PartsMissing", "safe_filename",
]

MIB = 1024 * 1024
STATUS_OPEN, STATUS_COMPLETED, STATUS_ABORTED, STATUS_EXPIRED = "open", "completed", "aborted", "expired"
#: Append-only event kinds (measurement-by-design): one row per lifecycle transition.
EVENT_KINDS = ("opened", "completed", "aborted", "expired")


@dataclass(frozen=True)
class UploadPolicy:
    """Per-consumer limits. `allowed_types` entries are exact MIME types or `type/*` prefixes."""

    max_bytes: int = 500 * MIB
    allowed_types: tuple[str, ...] = ("*/*",)
    part_size: int = 5 * MIB
    min_part_size: int = 256 * 1024
    max_part_size: int = 16 * MIB
    max_parts: int = 2000
    ttl_s: int = 24 * 3600

    def type_allowed(self, content_type: str) -> bool:
        ct = (content_type or "").split(";")[0].strip().lower()
        for rule in self.allowed_types:
            rule = rule.lower()
            if rule == "*/*" or rule == ct or (rule.endswith("/*") and ct.startswith(rule[:-1])):
                return True
        return False


@dataclass(frozen=True)
class UploadSession:
    id: str
    org_id: str
    user_id: Optional[str]
    filename: str
    content_type: str
    size_bytes: int
    part_size: int
    total_parts: int
    status: str
    created_at: datetime
    expires_at: datetime
    client_key: Optional[str] = None
    object_key: Optional[str] = None
    completed_at: Optional[datetime] = None

    def part_len(self, n: int) -> int:
        """Exact byte length part `n` (1-based) must have."""
        if n < self.total_parts:
            return self.part_size
        return self.size_bytes - self.part_size * (self.total_parts - 1)


@dataclass(frozen=True)
class PartInfo:
    number: int
    size: int


class UploadError(Exception):
    """Base error; `code` is the stable machine code the API answers with."""

    code = "upload_error"
    http_status = 400

    def __init__(self, message: str = "", **extra) -> None:
        super().__init__(message or self.code)
        self.extra = extra


class UploadNotFound(UploadError):
    code, http_status = "upload_nao_encontrado", 404


class UploadRejected(UploadError):
    code, http_status = "upload_recusado", 422


class UploadExpired(UploadError):
    code, http_status = "upload_expirado", 410


class UploadNotOpen(UploadError):
    code, http_status = "upload_nao_aberto", 409


class PartInvalid(UploadError):
    code, http_status = "parte_invalida", 422


class PartsMissing(UploadError):
    code, http_status = "partes_faltando", 409


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _SAFE.sub("_", base).strip("._") or "arquivo"
    return cleaned[:120]
