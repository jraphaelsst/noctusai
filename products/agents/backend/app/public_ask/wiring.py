"""Production wiring of the public-ask service (cached singleton).

The factory is only reached when the feature flag is on.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from uuid import UUID

from noctusai_lib.integrations.risk_classifier import make_risk_classifier

from app.config import settings
from app.stores.studio_knowledge import get_studio_knowledge_store

from . import limiar
from .breaker import DailyCostBreaker
from .postfilter import aplicar_posfiltro, pacote_posfiltro_padrao
from .safety_pack import load_engine
from .service import RETRIEVAL_TOP_K, PublicAskService, Retriever, Snippet

logger = logging.getLogger(__name__)


def make_knowledge_retriever(store, *, org_id: str, agent_id: str, colecao: str) -> Retriever:
    """Retrieval over ONE collection of the Limiar agent (`ativo` docs only —
    the store filters), by the STATIC per-tema query — never the user's text."""

    async def retrieve(tema: str) -> list[Snippet]:
        if not (org_id and agent_id and colecao):
            return []
        found = await asyncio.to_thread(
            store.search,
            UUID(org_id),
            UUID(agent_id),
            limiar.TEMA_QUERY[tema],
            colecao=colecao,
            limite=RETRIEVAL_TOP_K,
        )
        return [Snippet(fonte_id=r.slug, titulo=r.titulo, trecho=r.trecho) for r in found]

    return retrieve


@functools.lru_cache(maxsize=1)
def build_default_service() -> PublicAskService:
    from noctusai_lib.integrations.llm import chat_completion

    return PublicAskService(
        engine=load_engine(),
        classifier=make_risk_classifier(),
        retrieve=make_knowledge_retriever(
            get_studio_knowledge_store(settings),
            org_id=settings.public_ask_org_id,
            agent_id=settings.public_ask_agent_id,
            colecao=settings.public_ask_colecao,
        ),
        generate=chat_completion,
        posfiltro=aplicar_posfiltro,
        pacote=pacote_posfiltro_padrao(),
        breaker=DailyCostBreaker(settings.public_ask_daily_call_cap),
        on_outage=settings.on_classifier_outage,  # type: ignore[arg-type]
    )


__all__ = ["build_default_service", "make_knowledge_retriever"]
