"""
NoctusAI Financas Pessoais — Personal Finance Hub

Born from the seed framework. Includes APScheduler for recurring transactions.
Run with: uvicorn app.main:app --reload --port 8002
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    contas, transacoes, categorias, orcamentos, metas,
    carteira, ativos, operacoes, watchlist, recorrentes,
    patrimonio, relatorios, cotacoes, dashboard,
)

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
    ],
    version="0.1.0",
    limiter=limiter,
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
)
