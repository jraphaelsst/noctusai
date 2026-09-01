"""
NoctusAI IgIg — Reference Implementation

The simplest possible product. Just the spine, no domain code.
Proves that the seed framework works end-to-end.

Run with: uvicorn app.main:app --reload --port 8013

LLM access is inherited automatically — `create_product_app()` auto-wires
credential resolution + the default multi-provider LLMConfig. If this
product grew AI features, it would call:

    from noctusai_lib.integrations.llm import chat_completion
    reply = await chat_completion(messages=[...], org_id=org_id)

…and that's all. To override the default chat model (say, prefer `gpt-4o`
over `gpt-4o-mini`):

    from noctusai_seed import default_llm_config
    app = create_product_app(
        ...,
        llm_config=default_llm_config(default_chat_model="gpt-4o"),
    )
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers.cliente_router import router as cliente_router
from app.routers.esteira_router import router as esteira_router
from app.routers.marca_router import router as marca_router
from app.routers.distribuicao_router import router as distribuicao_router
from app.routers.comercial_router import router as comercial_router
from app.routers.financeiro_router import router as financeiro_router
from app.routers.integracoes_router import router as integracoes_router
from app.routers.pauta_router import router as pauta_router
from app.routers.custos_router import router as custos_router
from app.routers.webhook_router import router as webhook_router

# Per-route body-size cap. The app-wide default (`settings.max_body_bytes`,
# 1 MB — see `noctusai_seed.ProductSettings`) exists to DoS-guard inbound
# webhooks; browser uploads legitimately exceed it and need their own,
# larger, per-route ceiling instead of weakening the default everywhere.
# Both routes below have a dynamic path segment BEFORE the upload leaf, so
# both need the single-segment wildcard pattern shape rather than a plain
# prefix — a bare `/api/pautas` / `/api/marcas` prefix would also raise
# the cap on every JSON route under those routers. See
# `products/social-wiring/backend/app/main.py`'s `_MAX_BODY_PATH_OVERRIDES`
# block for the wildcard-pattern footgun this avoids, and
# `noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring for the
# exact-segment-count matching rule.
_MAX_BODY_PATH_OVERRIDES = {
    # Pauta creative-piece upload (POST /api/pautas/{pauta_id}/pecas —
    # `routers/pauta_router.py::enviar_peca`). The route's own
    # `_PECA_MAX_BYTES` (50 MB) is the real business-policy limit — it
    # raises a clear "Peça excede 50 MB" 413 once the bytes are already
    # read into memory (`await arquivo.read()`). This outer bound sits
    # ~20% above it so THAT message is what the user sees, not an opaque
    # 413 from the middleware.
    "/api/pautas/*/pecas": 60 * 1024 * 1024,  # 60 MB
    # Brand logo upload (POST /api/marcas/{marca_id}/logo —
    # `routers/marca_router.py::enviar_logo`). The route's own
    # `_LOGO_MAX_BYTES` (2 MB) is the business-policy limit, same
    # read-into-memory shape as pecas above. A logo is a much smaller
    # asset than a creative piece, so the outer bound scales down with
    # it — 3 MB gives headroom above the 2 MB cap without approaching
    # the pecas ceiling.
    "/api/marcas/*/logo": 3 * 1024 * 1024,  # 3 MB
}

app = create_product_app(
    name="IgIg",
    schema="igig",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Per-product routers. The seed's `example_router` scaffold was removed
    # once the six módulos landed — it shipped a live /api/example CRUD in a
    # production agency ERP. `webhook_router` stays as the signed-receiver
    # shape the signature provider will use (NOC-REMEDIATE[igig-assinatura]).
    routers=[
        cliente_router, esteira_router, marca_router, pauta_router,
        distribuicao_router, integracoes_router, financeiro_router, comercial_router,
        custos_router, webhook_router,
    ],
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
    # 🔴 Chaves sem as quais este produto NÃO deve subir em produção. O guard
    # de boot (`require_prod_config`) aborta listando todas as faltantes de
    # uma vez, e `noctus.dev.predeploy_check` lê ESTA MESMA lista
    # estaticamente — então a lacuna aparece antes do deploy, não no startup.
    # Mesmo padrão de `products/p-studio/backend/app/main.py`.
    #
    # Só entra uma chave cuja ausência produz comportamento ERRADO E
    # SILENCIOSO:
    #   • IGIG_COFRE_KEY — sem ela `marca_router._chave_cofre()` e
    #     `integracoes_router._chave()` recusam TODA gravação no Cofre e em
    #     Integrações com 409 "Cofre/Criptografia não configurada" — e essa
    #     é exatamente a falha que ficou semanas silenciosa em produção
    #     porque nada a declarava aqui. Ela SÓ entra agora porque foi
    #     verificado primeiro, deliberadamente, que a chave já está setada
    #     no `.env` de produção (roundtrip Fernet real testado dentro do
    #     container, 2026-08-31) — declarar uma chave AUSENTE transforma um
    #     aviso em recusa de boot, ou seja, em uma queda. Antes de declarar
    #     uma segunda chave aqui, confirme em produção do mesmo jeito.
    required_prod_config=["IGIG_COFRE_KEY"],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
