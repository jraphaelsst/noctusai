"""ERP AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 3 (2026-04-27). 10 features:
  - 9 user-facing (default `toggleable=True`, `default_granted=True` per §7.2)
  - 1 infrastructure-tier (`erp.embeddings`, `toggleable=False`, locked-on
    per §7.6 — visible for billing transparency, can't be disabled)

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.
"""
from __future__ import annotations

from noctusai_lib.ai import register_feature

# E1 — Imovel description generation (low-risk: org-internal property metadata)
register_feature(
    "erp.imovel_description",
    title="Geração de descrição de imóvel por IA",
    rationale=(
        "A IA gera descrições e títulos de imóveis a partir dos dados "
        "cadastrais (área, dormitórios, características, localização). "
        "Os dados do imóvel transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E2 — Lead score (medium-risk: lead PII in prompt)
register_feature(
    "erp.lead_score",
    title="Pontuação de leads por IA",
    rationale=(
        "A IA avalia perfis de clientes (nome, contato, interesses, "
        "histórico de interações) e atribui um score de 0-100 para "
        "priorização da equipe. Dados do lead transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E3 — Suggest price (low-risk: market analysis, no PII)
register_feature(
    "erp.suggest_price",
    title="Sugestão de preço por IA",
    rationale=(
        "A IA sugere uma faixa de preço para um imóvel comparando-o "
        "com imóveis similares na base. Apenas dados públicos do "
        "imóvel + comparáveis transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E4 — Lead follow-up draft (medium-risk: lead conversation history)
register_feature(
    "erp.lead_follow_up_draft",
    title="Rascunho de mensagem de follow-up para lead",
    rationale=(
        "A IA gera um rascunho de mensagem de follow-up baseado no "
        "histórico recente do lead (últimas atividades, último contato, "
        "imóvel de interesse). Dados do lead transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E5 — WhatsApp intent classification (medium-risk: message text)
register_feature(
    "erp.whatsapp_intent",
    title="Classificação de intenção em mensagens WhatsApp",
    rationale=(
        "A IA analisa o texto de mensagens recebidas via WhatsApp e "
        "classifica a intenção (interesse em comprar, dúvida, agendamento, "
        "etc.) para roteamento automático. O texto da mensagem transita "
        "pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E6 — Certidões score (medium-risk: legal docs)
register_feature(
    "erp.certidoes_score",
    title="Análise de certidões do cliente",
    rationale=(
        "A IA analisa as certidões anexadas (negativa de débitos, "
        "criminal, civil) e gera um sumário com pontuação de risco. "
        "O conteúdo das certidões transita pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E7 — Metas coach tip (low-risk: org-aggregated metas data)
register_feature(
    "erp.metas_coach_tip",
    title="Dicas de coaching para metas",
    rationale=(
        "A IA gera dicas práticas baseadas no progresso de metas da "
        "equipe (sem expor dados individuais). Apenas estatísticas "
        "agregadas transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E8 — Photo compliance (low-risk: photo metadata + URLs)
register_feature(
    "erp.photo_compliance",
    title="Conformidade de fotos do imóvel",
    rationale=(
        "A IA avalia se as fotos cadastradas atendem aos critérios "
        "exigidos pelos portais de divulgação (qualidade, ângulos, "
        "ausência de marcas d'água). Apenas URLs e metadados das "
        "fotos transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# E10 — Search relevance (low-risk: search query + listings text)
register_feature(
    "erp.search_relevance",
    title="Relevância de busca por IA",
    rationale=(
        "A IA pontua a relevância de imóveis encontrados em uma busca "
        "para refinar a ordenação. Apenas a query de busca + os imóveis "
        "candidatos transitam pelo provedor LLM."
    ),
    product="erp",
    default_granted=True,
)

# Embeddings — INFRASTRUCTURE TIER (toggleable=False per §7.6).
# Consumed silently by lead-matching + search-relevance + similar features.
# Visible in the catalog for billing transparency (users see what consumes
# their tokens) but locked-on; disabling individually would break dependent
# features.
register_feature(
    "erp.embeddings",
    title="Embeddings (infraestrutura de busca semântica)",
    rationale=(
        "Os embeddings são vetores numéricos gerados a partir dos textos "
        "de imóveis e perfis de clientes. Eles são consumidos silenciosamente "
        "por outras funcionalidades de IA (matching de leads, busca semântica, "
        "score de relevância) — esta linha existe para você ver o que está "
        "consumindo seus tokens. Como é infraestrutura, não pode ser desativada "
        "individualmente; desative recursos de IA específicos acima."
    ),
    product="erp",
    default_granted=True,
    toggleable=False,
)
