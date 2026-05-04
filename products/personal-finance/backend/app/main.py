"""
NoctusAI Financas Pessoais — Personal Finance Hub

Born from the seed framework. Includes APScheduler for recurring transactions.
Run with: uvicorn app.main:app --reload --port 8002
"""
from noctusai_seed import HealthEndpointConfig, create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.scheduler import configure as _configure_scheduler, start_scheduler, stop_scheduler

_configure_scheduler()
from app.routers import (
    contas, transacoes, categorias, orcamentos, metas,
    carteira, ativos, operacoes, watchlist, recorrentes,
    patrimonio, relatorios, cotacoes, dashboard, ai,
)


async def _readiness_db_ping() -> tuple[bool, str | None]:
    """Cheap admin-client SELECT to confirm Supabase is reachable.

    Reads `app.state.db` lazily (only when the probe fires) so import-time
    ordering doesn't matter. The seed-baked `/_ready` endpoint catches any
    exception and maps it to `(False, str(exc))`; we keep this body
    narrow so a healthy DB is the ONLY path that returns `True`.
    """
    try:
        admin = app.state.db.get_admin_client()
        admin.table("contas").select("id").limit(1).execute()
        return (True, None)
    except Exception as exc:  # noqa: BLE001 — probe is opaque on purpose
        return (False, f"db_ping failed: {exc}")


_readiness_db_ping.__name__ = "db_ping"


app = create_product_app(
    name="Financas Pessoais",
    schema="personal-finance",
    settings=settings,
    routers=[
        contas.router,
        transacoes.router,
        categorias.router,
        orcamentos.router,
        metas.router,
        carteira.router,
        ativos.router,
        operacoes.router,
        watchlist.router,
        recorrentes.router,
        patrimonio.router,
        relatorios.router,
        cotacoes.router,
        dashboard.router,
        ai.router,
    ],
    version="0.1.0",
    limiter=limiter,
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
    standard_routers=["health", "notificacoes", "team", "ai_outputs", "ai_feedback"],
    consent_features="app.services.ai_consent_features",
    # Ops endpoints — `/_health` (liveness, always cheap) + `/_ready`
    # (readiness, may include vendor pings). Empty `liveness_hooks` keeps
    # `/_health` instant; readiness adds a Supabase round-trip so probes
    # know the DB is reachable.
    health_config=HealthEndpointConfig(
        readiness_hooks=[_readiness_db_ping],
    ),
)
