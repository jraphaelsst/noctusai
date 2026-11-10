"""Every owner notification the Agentes product sends — declared, so core's "Notificações" page lists it and the owner can
switch it off (`noctusai_lib.domain.notification_catalog`).

Adding a send = adding a kind HERE in the same change. Texts are pt-BR and shown verbatim to the owner: say what arrives and
exactly what triggers it. Imported by ``app/main.py`` at boot so the kinds register with the seed gate (seed ``app.py`` §3c).
"""
from __future__ import annotations

from noctusai_lib.domain.notification_catalog import NotificationKind, declare_kinds

PRODUCT = "agents"

KIND_EVAL_LOOP_PARADA = "eval_loop_parada"
KIND_EVAL_LOOP_CHECKPOINT = "eval_loop_checkpoint"

KINDS: tuple[NotificationKind, ...] = (
    NotificationKind(
        kind=KIND_EVAL_LOOP_PARADA,
        titulo="Loop de avaliação parado",
        descricao="Aviso de que um loop de avaliação de agente parou, com o motivo (nota máxima, 2 rodadas sem melhora, "
                  "orçamento atingido, rodadas esgotadas ou parada manual), a melhor nota, o gasto e o link para o painel.",
        gatilho="Um loop de avaliação (comportamento ou mecanismo) é encerrado pelas regras do portão: nota 100%, duas "
                "rodadas seguidas sem melhora, orçamento (US$ 20) atingido, rodadas planejadas esgotadas ou parada manual.",
        canais=("whatsapp", "in_app"),
    ),
    NotificationKind(
        kind=KIND_EVAL_LOOP_CHECKPOINT,
        titulo="Checkpoint de loop de avaliação",
        descricao="Resumo de andamento de um loop de avaliação ainda ativo: rodada atual, notas, gasto e rodadas sem melhora.",
        gatilho="Um loop de avaliação ativo conclui uma rodada que atinge um checkpoint (rodadas 5, 10 e 15, dentro do planejado).",
        canais=("whatsapp", "in_app"),
    ),
)

declare_kinds(PRODUCT, KINDS)
