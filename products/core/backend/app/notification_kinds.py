"""Every owner notification Core itself sends — declared, so the "Notificações" page lists it and the owner can switch it
off (`noctusai_lib.domain.notification_catalog`).

Adding a send = adding a kind HERE in the same change. Texts are pt-BR and shown verbatim to the owner: say what arrives and
exactly what triggers it. Imported by ``app/main.py`` at boot so the kinds register with the seed gate (seed ``app.py`` §3c).
"""
from __future__ import annotations

from noctusai_lib.domain.notification_catalog import NotificationKind, declare_kinds

PRODUCT = "core"

KIND_SKILL_SCOUT_NOVO_SKILL = "skill_scout_novo_skill"

KINDS: tuple[NotificationKind, ...] = (
    NotificationKind(
        kind=KIND_SKILL_SCOUT_NOVO_SKILL,
        titulo="Skill nova encontrada pelo skill-scout",
        descricao="Aviso de que o skill-scout achou uma skill externa que pode servir à plataforma: nome, resumo de uma "
                  "linha e o link da fonte. Só chega por WhatsApp — nada por e-mail nem pelo sino.",
        gatilho="O skill-scout termina uma busca e recomenda uma skill nova (uma mensagem por skill recomendada).",
        canais=("whatsapp",),
    ),
)

declare_kinds(PRODUCT, KINDS)
