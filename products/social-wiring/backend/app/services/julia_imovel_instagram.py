"""Julia > the listing an Instagram post/reel advertises (Lais study S6, owner 2026-11-17).

A lead who pastes `instagram.com/p/<code>` or `/reel/<code>` means the listing that post shows. Nothing in `ig_media` /
`cs_posts` links a post to a listing, so the link is its own dated row (`julia_post_instagram_imovel`, migration 356), set by
an admin. This module is the pure URL parsing (`analisar`) and the org-scoped lookup (`codigos`); `julia_ferramentas_service
.resolver_imovel` walks the mapped code through the catalog. Never invents: an unmapped post = the typed `sem_mapeamento`, so
Julia asks for the listing code instead of guessing.

A `/share/p/<id>` link is an opaque redirect token, NOT the shortcode (it needs an HTTP hop we do not make); it is reported as
`link_compartilhado` (typed not-found), never mapped by guess.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

T = "julia_post_instagram_imovel"
SHORTCODE_MAX = 6
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am", "www.instagr.am"}
_TIPOS = {"p", "reel", "reels", "tv"}
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,40}$")

#: Typed reasons when nothing resolved.
SEM_MAPEAMENTO = "sem_mapeamento"
LINK_COMPARTILHADO = "link_compartilhado"


def analisar(texto: str) -> tuple[list[str], bool]:
    """`(shortcodes, tem_link_compartilhado)` found in `texto`, in order, de-duplicated, at most `SHORTCODE_MAX`.
    Accepts `/p/<c>`, `/reel/<c>`, `/reels/<c>`, `/tv/<c>` with an optional `/<user>/` prefix, any query string / trailing slash."""
    achados: list[str] = []
    compartilhado = False
    for bruta in _URL_RE.findall(texto or ""):
        url = urlparse(bruta.rstrip(".,;:!?)"))
        if (url.hostname or "").lower() not in _HOSTS:
            continue
        seg = [s for s in url.path.split("/") if s]
        if seg and seg[0].lower() == "share":
            compartilhado = True
            continue
        for i, s in enumerate(seg[:-1]):
            if s.lower() in _TIPOS and _CODE_RE.match(seg[i + 1]):
                if seg[i + 1] not in achados:
                    achados.append(seg[i + 1])
                break
    return achados[:SHORTCODE_MAX], compartilhado


def codigos(client: Any, org_id: UUID, codes: list[str]) -> list[str]:
    """Listing codes mapped (by an admin) to these shortcodes for THIS org, in the order given. Unmapped ones are skipped."""
    if not codes:
        return []
    rows = client.table(T).select("shortcode, codigo_imovel").eq("org_id", str(org_id)).in_("shortcode", codes).execute().data or []
    por_code = {r["shortcode"]: r["codigo_imovel"] for r in rows}
    return [por_code[c] for c in codes if c in por_code]


__all__ = ["LINK_COMPARTILHADO", "SEM_MAPEAMENTO", "analisar", "codigos"]
