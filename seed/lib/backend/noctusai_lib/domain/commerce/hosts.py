"""Storefront hosts — `hostname -> org`, the public storefront's only org source.

The storefront never trusts a client-sent org id: the org is whatever the
`Host` header resolves to here. Managing hosts is a PLATFORM-ADMIN act (the host
decides which hostnames noc is willing to serve for which client); the router
enforces that, this module only does the data work.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, now_iso, tbl
from .errors import conflict, invalid, not_found

_TABLE = "commerce_storefront_hosts"
_HOST_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_hostname(raw: str) -> str:
    """`Host` header value -> bare lowercase hostname (no port, no trailing dot)."""
    host = (raw or "").strip().lower()
    if host.startswith("["):  # IPv6 literal: never a storefront
        return ""
    host = host.split(":", 1)[0].rstrip(".")
    return host


def resolve_host(db: Any, host_header: str) -> Optional[dict]:
    """The host row for a request's `Host` header, or None (=> the route 404s)."""
    host = normalize_hostname(host_header)
    if not host:
        return None
    resp = tbl(db, _TABLE).select("*").eq("hostname", host).limit(1).execute()
    return first(resp)


def list_hosts(db: Any, org_id: Any) -> list[dict]:
    resp = tbl(db, _TABLE).select("*").eq("org_id", str(org_id)).order("hostname").limit(200).execute()
    return [dict(r) for r in (resp.data or [])]


def add_host(db: Any, org_id: Any, hostname: str, *, is_primary: bool = False) -> dict:
    host = normalize_hostname(hostname)
    if not _HOST_RE.match(host):
        raise invalid("hostname", "Hostname inválido.", code="hostname_invalido")
    row = {"hostname": host, "org_id": str(org_id), "is_primary": bool(is_primary), "created_at": now_iso()}
    if resolve_host(db, host) is not None:
        raise conflict("host_ja_existe", "Este hostname já está em uso.")
    if is_primary:
        tbl(db, _TABLE).update({"is_primary": False}).eq("org_id", str(org_id)).execute()
    try:
        saved = first(tbl(db, _TABLE).insert(row).execute())
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict("host_ja_existe", "Este hostname já está em uso.") from exc
        raise
    return saved or row


def delete_host(db: Any, org_id: Any, hostname: str) -> None:
    host = normalize_hostname(hostname)
    deleted = tbl(db, _TABLE).delete().eq("org_id", str(org_id)).eq("hostname", host).execute()
    if not (deleted.data or []):
        raise not_found("Hostname")


__all__ = ["add_host", "delete_host", "list_hosts", "normalize_hostname", "resolve_host"]
