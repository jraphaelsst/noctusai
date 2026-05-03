"""PF onboarding service — first-login bootstrap.

Wraps the seed-side `ensure_personal_org` helper with PF-specific concerns:
the `Pessoal — {email}` name template and the per-org "starter set" of 19
default categorias. The mechanism (auto-create personal org) is platform
domain logic; the data (which categorias to seed, what name template to use)
is PF-specific.

Per `pf-org-scoping-migration` §7.2=B — categorias defaults are per-org
copies, not a single global row. Every new org gets its own 19 starter
categorias which the org can then rename / delete freely.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from noctusai_lib.domain.org import ensure_personal_org

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PF default categorias — 19 starter rows seeded into every new org.
# Source of truth: the historical `user_id IS NULL` rows from the legacy
# user-scoped schema, snapshotted 2026-05-03 at the schema flip. If you
# change this list, also reflect the change in the live DB for existing orgs
# (or accept that older orgs keep the old set).
# ---------------------------------------------------------------------------

PF_DEFAULT_CATEGORIAS: List[Dict[str, Any]] = [
    # Despesa (14)
    {"nome": "Alimentacao", "tipo": "despesa", "cor": "#f59e0b", "icone": "🛒"},
    {"nome": "Assinaturas", "tipo": "despesa", "cor": "#0ea5e9", "icone": "📱"},
    {"nome": "Compras", "tipo": "despesa", "cor": "#a855f7", "icone": "🛍️"},
    {"nome": "Contas e Utilidades", "tipo": "despesa", "cor": "#6366f1", "icone": "💡"},
    {"nome": "Educacao", "tipo": "despesa", "cor": "#8b5cf6", "icone": "📚"},
    {"nome": "Investimentos Aporte", "tipo": "despesa", "cor": "#6366f1", "icone": "📊"},
    {"nome": "Lazer", "tipo": "despesa", "cor": "#ec4899", "icone": "🎬"},
    {"nome": "Moradia", "tipo": "despesa", "cor": "#ef4444", "icone": "🏠"},
    {"nome": "Poupanca", "tipo": "despesa", "cor": "#22c55e", "icone": "🏦"},
    {"nome": "Restaurantes", "tipo": "despesa", "cor": "#f97316", "icone": "🍽️"},
    {"nome": "Saude", "tipo": "despesa", "cor": "#10b981", "icone": "🏥"},
    {"nome": "Seguros", "tipo": "despesa", "cor": "#64748b", "icone": "🛡️"},
    {"nome": "Transporte", "tipo": "despesa", "cor": "#3b82f6", "icone": "🚗"},
    {"nome": "Viagens", "tipo": "despesa", "cor": "#14b8a6", "icone": "✈️"},
    # Receita (4)
    {"nome": "Freelance", "tipo": "receita", "cor": "#3b82f6", "icone": "💻"},
    {"nome": "Investimentos", "tipo": "receita", "cor": "#8b5cf6", "icone": "📈"},
    {"nome": "Outros Rendimentos", "tipo": "receita", "cor": "#6b7280", "icone": "💵"},
    {"nome": "Salario", "tipo": "receita", "cor": "#10b981", "icone": "💰"},
    # Transferencia (1)
    {"nome": "Transferencia", "tipo": "transferencia", "cor": "#94a3b8", "icone": "🔄"},
]


async def seed_default_categories(db: Any, org_id: str) -> int:
    """Seed the 19 PF starter categorias into ``org_id``. Returns rows inserted.

    Idempotent: if the org already has any ``is_sistema=true`` categorias
    (i.e. was seeded before), this is a no-op and returns 0.
    """
    existing = (
        db.table("categorias")
        .select("id")
        .eq("org_id", org_id)
        .eq("is_sistema", True)
        .limit(1)
        .execute()
    )
    if existing.data:
        logger.debug("seed_default_categories: org_id=%s already seeded — skipping", org_id)
        return 0

    payload = [
        {**row, "org_id": org_id, "is_sistema": True}
        for row in PF_DEFAULT_CATEGORIAS
    ]
    db.table("categorias").insert(payload).execute()
    logger.info(
        "seed_default_categories: inserted %d default categorias for org_id=%s",
        len(payload),
        org_id,
    )
    return len(payload)


async def ensure_pf_personal_org(db: Any, user_id: str, email: str) -> str:
    """First-PF-login bootstrap. Returns the user's org_id.

    Wraps the seed-lib helper with PF's `Pessoal — {email}` template, then
    seeds the 19 default categorias if the org is brand-new. Idempotent: if
    the user already has an org, returns it; if the org already has its
    seeded categorias, no rows are inserted.
    """
    org_id = await ensure_personal_org(
        db,
        user_id,
        email=email,
        name_template="Pessoal — {email}",
        is_personal=True,
    )
    await seed_default_categories(db, org_id)
    return org_id
