"""Website catalog — the public showcase mirrors `public.products`.

Fixed projection `slug, nome, descricao, icone, status`, filtered to
`exibir_no_site = true`. `status` is derived HERE, on the server only:

    ativo AND deploy_scope='live'  -> disponivel
    ativo AND deploy_scope='dev'   -> em_breve
    NOT ativo                      -> lista_de_espera  (whatever deploy_scope is)

Raw `ativo` / `deploy_scope` / `url_base` / ports never leave this module.
60s in-process cache (one per worker, same tradeoff as website_settings_service),
dropped by `invalidate_cache()` which the products admin router calls on writes.
"""
from __future__ import annotations

import logging
import time
from typing import Literal, Optional

from noctusai_lib.api import StrictHttpModel

from app.database import get_admin_client

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60.0

CatalogStatus = Literal["disponivel", "lista_de_espera", "em_breve"]


class CatalogProduct(StrictHttpModel):
    """The ONLY shape the public site sees. extra='forbid' => a leaked field is a hard error."""

    slug: str
    nome: str
    descricao: Optional[str] = None
    icone: Optional[str] = None
    status: CatalogStatus


# {"expires_at": float, "data": list[CatalogProduct]} | None
_cache: Optional[dict] = None


def derive_status(ativo: bool, deploy_scope: Optional[str]) -> CatalogStatus:
    if not ativo:
        return "lista_de_espera"
    return "disponivel" if deploy_scope == "live" else "em_breve"


def invalidate_cache() -> None:
    global _cache
    _cache = None


def list_public(*, client=None, now: Optional[float] = None) -> list[CatalogProduct]:
    """Public catalog projection, cached 60s. Sync (the PostgREST client is blocking).

    `client` / `now` are DI seams for tests (default: the admin client / monotonic clock).
    """
    global _cache
    now = time.monotonic() if now is None else now
    if _cache is not None and _cache["expires_at"] > now:
        return list(_cache["data"])

    rows = (
        (client or get_admin_client())
        .table("products")
        .select("slug,nome,descricao,icone,ativo,deploy_scope")
        .eq("exibir_no_site", True)
        .order("slug")
        .execute()
        .data
        or []
    )
    data = [
        CatalogProduct(
            slug=r["slug"],
            nome=r["nome"],
            descricao=r.get("descricao"),
            icone=r.get("icone"),
            status=derive_status(bool(r.get("ativo")), r.get("deploy_scope")),
        )
        for r in rows
    ]
    _cache = {"expires_at": now + _CACHE_TTL_SECONDS, "data": data}
    return list(data)


__all__ = ["CatalogProduct", "derive_status", "invalidate_cache", "list_public"]
