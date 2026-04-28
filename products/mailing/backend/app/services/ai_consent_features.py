"""Mailing AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 2 (2026-04-27). This module is imported
once by `app.main` so its `register_feature(...)` calls populate the
platform-wide consent catalog at boot.

All 7 mailing features default to `default_granted=True` per the §7.2
rubric (low/medium-risk org-internal AI). Users still see them in
`/api/me/consents` for transparency (LGPD + billing) and can toggle off.
"""
from __future__ import annotations

from noctusai_lib.ai import register_feature

# M1 — Subject-line generation (low-risk: org-internal copy)
register_feature(
    "mailing.subject_gen",
    title="Geração de linha de assunto por IA",
    rationale=(
        "A IA lê o resumo da campanha e sugere variantes de assunto "
        "(3-5 opções com tons diferentes). Conteúdo do resumo transita "
        "pelo provedor LLM para gerar as sugestões."
    ),
    product="mailing",
    default_granted=True,
)

# M2 — Template draft from prompt (low-risk: org-internal copy)
register_feature(
    "mailing.template_draft",
    title="Rascunho de template de e-mail por IA",
    rationale=(
        "A IA gera um rascunho HTML responsivo a partir do briefing "
        "fornecido. O briefing transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
)

# M5 — Re-engagement variants (low-risk: org-internal copy)
register_feature(
    "mailing.reengagement_variants",
    title="Variantes de re-engajamento",
    rationale=(
        "A IA gera 3 variantes de e-mail de re-engajamento (leve, direto, "
        "valor) a partir do contexto. O contexto transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
)

# M6 — Deliverability review (low-risk: org-internal copy)
register_feature(
    "mailing.deliverability_review",
    title="Revisão de entregabilidade",
    rationale=(
        "A IA analisa o HTML e o assunto para sinalizar palavras de "
        "spam, problemas de formatação, ou outros riscos de entrega. "
        "Apenas o conteúdo da campanha (sem dados de contatos) entra "
        "no prompt."
    ),
    product="mailing",
    default_granted=True,
)

# M7 — Translation (low-risk: org-internal copy)
register_feature(
    "mailing.translate",
    title="Tradução de templates",
    rationale=(
        "A IA traduz o HTML do template (PT → EN/ES/FR) preservando a "
        "estrutura. O conteúdo do template transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
)

# M3 — Contact segmentation (medium-risk: contact PII in embeddings)
register_feature(
    "mailing.segment_contacts",
    title="Segmentação automática de contatos",
    rationale=(
        "A IA gera embeddings e agrupa seus contatos em segmentos por "
        "similaridade (nome, empresa, tags, campos customizados). Os "
        "dados de contato entram no provedor LLM apenas para gerar "
        "embeddings — não são armazenados externamente."
    ),
    product="mailing",
    default_granted=True,
)

# M4 — Campaign debrief (low-risk: anonymous aggregates)
register_feature(
    "mailing.campaign_debrief",
    title="Resumo automático de campanha (debrief)",
    rationale=(
        "Após cada envio, a IA gera um relatório de 3 parágrafos com "
        "métricas agregadas (entregues / abertos / cliques) + comentário "
        "narrativo. Apenas estatísticas anônimas entram no prompt — "
        "nenhum e-mail individual ou conteúdo de contato."
    ),
    product="mailing",
    default_granted=True,
)
