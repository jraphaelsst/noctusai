"""``noctus.sw.*`` — social-wiring product tools (HTTP clients of the product API).

``noctus.sw.ad_lead_intake`` — status / backfill of the ad-lead intake (Meta form lead -> property + corretor).
``noctus.sw.vista_clientes_sync`` — status / bounded sync of Vista clientes into our lead people (fill-empty-only; owner-triggered).
``noctus.sw.imoveis_sync`` — status / run of the Vista imóveis refresh (the scheduled 2-hourly job's manual twin).
``noctus.sw.imovel_videos_vista_import`` — dry_run / run / status of the import of Vista's videos into the imóvel YouTube field (platform admin).
``noctus.sw.estruturas_import`` — plan / apply / status of the Estruturas library load (platform admin; counts + reason codes only, never row text).
Config (env, loaded from the repo-root ``.env`` by the server/CLI bootstrap): ``NOCTUS_SW_URL`` (the product base URL,
e.g. https://social-wiring.noctusai.com) and ``NOCTUS_SW_TOKEN`` (an org ADMIN's bearer session token; never logged
or returned).
"""

from __future__ import annotations


def register_all(server) -> None:
    from . import ad_lead_intake, estruturas_import, imoveis_sync, imovel_videos_vista_import, vista_clientes_sync

    ad_lead_intake.register(server)
    estruturas_import.register(server)
    imoveis_sync.register(server)
    imovel_videos_vista_import.register(server)
    vista_clientes_sync.register(server)


__all__ = ["register_all"]
