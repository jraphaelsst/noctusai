"""
NoctusAI Assistant -- a shadow of one personal WhatsApp line that can ANSWER it through the owner's agent (live reply).

* WhatsApp connection (QR, admin) + the signed inbound webhook -- `app/routers/whatsapp_router.py` (no send / mark-read /
  backfill / chat-read route is mounted; the only sender is the live reply, `app/live/`, off by default);
* the intake queue + its append-only events -- `app/services/intake.py`, migration 015;
* the scheduling classifier (S3, classification ONLY: no reply, no send) -- `app/shadow/`, migration 017: a seed
  `Worker` started in the lifespan + the admin replay / blind-sample routes (`app/routers/classificacao_router.py`).

Run with: uvicorn app.main:app --reload --port 8021
"""
from noctusai_lib.integrations.whatsapp import (
    make_line_event_sink, parse_line_policy, register_line_policy, set_default_line_event_sink,
)
from noctusai_seed import create_product_app
from app.config import settings
from app.auth_context import get_auth_context
from app.dependencies import get_admin_client
from app.rate_limit import limiter
from app.live.wiring import assert_live_reply_config, drain as drain_replies
from app.routers.classificacao_router import router as classificacao_router
from app.routers.google_router import callback_router as google_callback_router, router as google_router
from app.routers.whatsapp_router import router as whatsapp_router
from app.services.agents_grant import build_router as build_agents_grant_router
from app.shadow.worker import start_worker, stop_worker

# Line policy v1: declare the Assistant's own line (`ASSISTANT_WAHA_LINE_POLICY`, from waha-instances.yml; the personal
# live shape: send enabled, no edge). A malformed value fails the boot; an absent one leaves the line undeclared => the seed
# refuses its writes (fail-closed), so the live reply cannot send.
if settings.assistant_waha_base_url and settings.assistant_waha_line_policy:
    # The personal live line (`send: enabled`, mark_online/full_sync/auto_repair off, no edge) still REFUSES things the
    # policy forbids (auto-repair, presence); those refusals land in the append-only `whatsapp_line_events` (migration 020)
    # through a PERSISTENT sink (a `send: disabled` line would not even register without one). The Real sink builds its
    # client lazily (only on a refusal), so importing the app under tests needs no DB; tests that exercise a refusal swap in
    # the Fake via `set_default_line_event_sink`.
    set_default_line_event_sink(make_line_event_sink(schema="assistant", client_factory=get_admin_client))
    register_line_policy(
        settings.assistant_waha_base_url,
        parse_line_policy(settings.assistant_waha_line_policy),
        session=settings.assistant_waha_session,
    )

async def stop_worker_and_replies() -> None:
    await drain_replies()
    await stop_worker()


# The live reply is OFF unless ASSISTANT_REPLY_ENABLED; when on, a deploy missing any piece of its CONFIG refuses to boot. The agents
# credential is not config: it is the platform grant (no grant = the reply refuses to answer, declared, per org).
assert_live_reply_config(settings)

app = create_product_app(
    name="Assistant",
    schema="assistant",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # A deploy without these refuses to boot: the Fernet key (WAHA api key at rest), the webhook HMAC secret (plan
    # item 10) and the identity key (no raw third-party phone is stored).
    required_prod_config=["ENCRYPTION_KEY", "ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET", "ASSISTANT_IDENTITY_HMAC_KEY"],
    # The platform grant receiver: `agents` delivers the owner agent's channel token here (one-shot delivery token, never pasted).
    routers=[whatsapp_router, classificacao_router, google_router, google_callback_router,
             build_agents_grant_router(get_auth_context)],
    lifespan_startup=start_worker,
    lifespan_shutdown=stop_worker_and_replies,
)
