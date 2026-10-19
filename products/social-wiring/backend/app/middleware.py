"""
Middleware namespace shortcut for Social Wiring.

Re-exports everything from the shared package so product code can
``from app.middleware import CorrelationIdMiddleware`` etc. without
reaching into ``noctusai_lib.api.middleware`` directly. Mirrors the
4-product convention (core, ERP, PF, therapy).

The seed's ``create_product_app(...)`` already wires the middleware
chain via the lib — this module exists for downstream imports and as
the canonical place to layer product-specific middleware on top.
"""
from noctusai_lib.api.middleware import *  # noqa: F401,F403


class LegacyLaisPathAlias:
    """Serves the pre-rename `/api/lais/*` and `/api/public/lais/*` URLs on the renamed `/api/julia/*` routes.

    The module was renamed Lais -> Julia (owner order 2026-10-19). Agents' tools client, an already-sent privacy-notice
    link and the previous image during the deploy window still call the old paths; rewriting the ASGI path in front of
    routing keeps ONE route table (no duplicated routers, OpenAPI shows only the new paths).
    NOC-REMEDIATE[drop-lais-route-alias]: delete this class and its `add_middleware` once agents calls
    `/api/julia/ferramentas/*` and no old link is in circulation -- 2026-10-19 + one release.
    """

    _PAIRS = (("/api/public/lais", "/api/public/julia"), ("/api/lais", "/api/julia"))

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            for old, new in self._PAIRS:
                if path == old or path.startswith(old + "/"):
                    renamed = new + path[len(old):]
                    scope = dict(scope, path=renamed)
                    if scope.get("raw_path"):
                        scope["raw_path"] = renamed.encode()
                    break
        await self.app(scope, receive, send)
