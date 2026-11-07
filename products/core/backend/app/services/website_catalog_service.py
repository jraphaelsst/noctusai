"""Website catalog — the public showcase mirrors `public.products`.

Fixed projection `slug, nome, descricao, icone, destaque_no_site, status`, filtered to
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
    # Featured position 1..6 on the landing (display order); None = not featured.
    # Public + non-sensitive. The frontend orders and falls back (none featured => first 6).
    destaque_no_site: Optional[int] = None
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
        .select("slug,nome,descricao,icone,destaque_no_site,ativo,deploy_scope")
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
            destaque_no_site=r.get("destaque_no_site"),
            status=derive_status(bool(r.get("ativo")), r.get("deploy_scope")),
        )
        for r in rows
    ]
    _cache = {"expires_at": now + _CACHE_TTL_SECONDS, "data": data}
    return list(data)


MAX_DESTAQUES = 6


class DestaqueRefused(Exception):
    """An admin write would break the featured-products rules. `detail` is pt-BR, shown as-is."""

    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def check_destaque_write(db, product_id: str, fields: dict) -> None:
    """Refuse (never silently swap) a write that would break the featured rules.

    `fields` is the patch about to be written; only `destaque_no_site` / `exibir_no_site`
    matter here. The DB constraints (migration 100) are the race-proof backstop; this gives
    the owner a clear reason first.
    """
    touches_destaque = "destaque_no_site" in fields
    novo = fields.get("destaque_no_site")
    if not touches_destaque and fields.get("exibir_no_site") is not False:
        return

    cur = (
        db.table("products").select("id,slug,nome,exibir_no_site,destaque_no_site")
        .eq("id", product_id).execute().data
    )
    if not cur:
        return  # the write itself answers 404
    cur = cur[0]
    exibir = fields.get("exibir_no_site", cur.get("exibir_no_site"))

    if not touches_destaque:
        # Hiding a product that is currently featured would leave a hidden-but-featured row.
        if cur.get("destaque_no_site") is not None:
            raise DestaqueRefused(
                f"'{cur.get('nome')}' está em destaque na posição {cur['destaque_no_site']}. "
                "Remova o destaque antes de ocultá-lo do site."
            )
        return

    if novo is None:
        return  # un-featuring is always allowed
    if not isinstance(novo, int) or isinstance(novo, bool) or not 1 <= novo <= MAX_DESTAQUES:
        raise DestaqueRefused(
            f"A posição de destaque deve ser de 1 a {MAX_DESTAQUES}. "
            f"A página inicial exibe no máximo {MAX_DESTAQUES} produtos em destaque.",
            status_code=422,
        )
    if exibir is not True:
        raise DestaqueRefused(
            f"'{cur.get('nome')}' está oculto do site e não pode ser colocado em destaque. "
            "Exiba-o no site primeiro."
        )
    others = [
        o for o in (
            db.table("products").select("id,nome,destaque_no_site")
            .neq("id", product_id).execute().data or []
        )
        if o.get("destaque_no_site") is not None
    ]
    holder = next((o for o in others if o.get("destaque_no_site") == novo), None)
    if holder:
        raise DestaqueRefused(
            f"A posição {novo} já está ocupada por '{holder.get('nome')}'. "
            "Libere essa posição antes (nada é trocado automaticamente)."
        )
    if cur.get("destaque_no_site") is None and len(others) >= MAX_DESTAQUES:
        raise DestaqueRefused(
            f"Já existem {MAX_DESTAQUES} produtos em destaque. "
            "Remova o destaque de um deles antes de adicionar outro."
        )


__all__ = [
    "CatalogProduct", "DestaqueRefused", "MAX_DESTAQUES", "check_destaque_write",
    "derive_status", "invalidate_cache", "list_public",
]
