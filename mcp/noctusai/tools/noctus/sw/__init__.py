"""``noctus.sw.*`` — social-wiring product tools (HTTP clients of the product API).

``noctus.sw.ad_lead_intake`` — status / backfill of the ad-lead intake (Meta form lead -> property + corretor).
``noctus.sw.imoveis_sync`` — status / run of the Vista imóveis refresh (the scheduled 2-hourly job's manual twin).
Config (env, loaded from the repo-root ``.env`` by the server/CLI bootstrap): ``NOCTUS_SW_URL`` (the product base URL,
e.g. https://social-wiring.noctusai.com) and ``NOCTUS_SW_TOKEN`` (an org ADMIN's bearer session token; never logged
or returned).
"""

from __future__ import annotations


def register_all(server) -> None:
    from . import ad_lead_intake, imoveis_sync

    ad_lead_intake.register(server)
    imoveis_sync.register(server)


__all__ = ["register_all"]
