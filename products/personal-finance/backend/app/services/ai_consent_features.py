"""Personal Finance AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 5 (2026-04-27). 3 features:
  - 2 medium-risk (transaction descriptions in prompt) → `default_granted=True`
    (preserves current product behavior; users still see in /api/me/consents).
  - 1 high-risk (personal financial narrative) → `default_granted=False`
    (opt-in only; matches Daily Life weekly_review posture).

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.
"""
from __future__ import annotations

from noctusai_lib.ai import register_feature

# P1-opp — Transaction auto-categorization (medium-risk: transaction
# description / merchant text in prompt — but org-internal, not personal narrative)
register_feature(
    "pf.transaction_categorize",
    title="Categorização de transações por IA",
    rationale=(
        "A IA sugere uma categoria para uma transação a partir de sua "
        "descrição, comerciante e valor. Esses dados transitam pelo "
        "provedor LLM. A sugestão respeita as categorias já cadastradas "
        "na sua organização."
    ),
    product="personal-finance",
    default_granted=True,
)

# P3-opp — Recurring expense flag (medium-risk: same shape as P1-opp but with
# 12 months of same-merchant history)
register_feature(
    "pf.recurring_flag",
    title="Detecção de despesas recorrentes",
    rationale=(
        "A IA analisa até 12 meses de transações do mesmo comerciante "
        "para sinalizar gastos potencialmente recorrentes (assinaturas, "
        "contas, mensalidades). Os dados das transações transitam pelo "
        "provedor LLM."
    ),
    product="personal-finance",
    default_granted=True,
)

# P2-opp — Monthly narrative (HIGH-RISK: personal financial story, 30 days
# of receita/despesa/fluxo aggregated + top categorias context)
register_feature(
    "pf.monthly_narrative",
    title="Narrativa financeira mensal",
    rationale=(
        "A IA gera uma narrativa em 3 parágrafos sobre suas finanças do "
        "mês — receita, despesa, fluxo líquido, taxa de poupança e top "
        "categorias. A narrativa é uma história pessoal sobre seu dinheiro; "
        "os dados financeiros transitam pelo provedor LLM. Opt-in: ative "
        "manualmente para receber o resumo mensal."
    ),
    product="personal-finance",
    default_granted=False,
)
