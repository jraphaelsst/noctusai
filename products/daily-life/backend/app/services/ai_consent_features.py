"""Daily Life AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 4 (2026-04-27). 3 features, all
**high-risk** (personal narrative / clinical-adjacent text in prompt) and
therefore `default_granted=False` per §7.2 rubric — opt-in only. Users
must actively grant consent before any of these run.

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.
"""
from __future__ import annotations

from noctusai_lib.ai import register_feature

# D1 — Today's brief (HIGH-RISK: personal task / event / habit data in prompt)
register_feature(
    "daily_life.daily_brief",
    title="Resumo do dia por IA",
    rationale=(
        "A IA gera um resumo curto do seu dia (chip + summary) baseado nas "
        "tarefas pendentes, eventos do calendário e hábitos não checados. "
        "Esses dados pessoais transitam pelo provedor LLM. Opt-in: você "
        "precisa ativar explicitamente para que o resumo apareça no header."
    ),
    product="daily-life",
    default_granted=False,
)

# D6 — Weekly review (HIGH-RISK: personal narrative + clinical-adjacent metrics)
register_feature(
    "daily_life.weekly_review",
    title="Revisão semanal por IA",
    rationale=(
        "A IA gera uma narrativa de 3 parágrafos sobre sua semana — tarefas "
        "concluídas/pendentes, sequências de hábitos, anotações, sessões de "
        "foco. Inclui possíveis dados de saúde mental (humor, check-ins). "
        "Esses dados pessoais transitam pelo provedor LLM. Opt-in obrigatório."
    ),
    product="daily-life",
    default_granted=False,
)

# D4 — Note-to-task extraction (HIGH-RISK: full note body text in prompt)
register_feature(
    "daily_life.note_extract",
    title="Extração de tarefas de anotações",
    rationale=(
        "A IA lê o conteúdo completo da sua anotação e sugere tarefas a "
        "partir do texto. O conteúdo da anotação transita pelo provedor LLM "
        "para gerar as sugestões. Opt-in: ative manualmente quando quiser "
        "usar o botão de extração."
    ),
    product="daily-life",
    default_granted=False,
)
