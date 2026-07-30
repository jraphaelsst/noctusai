"""
`PipelineConfig` — everything a consumer declares to get the whole mechanic.

The point of this dataclass is that it is the ONLY thing that differs between
two boards. Before it existed, `negociacoes_venda.mover_etapa` and
`processos_venda.mover_etapa` were the same ~35 lines of read-current →
validate → update → record → log, forked once per board, and they had already
DRIFTED: the Funil wrote a stage-transition history row, Processos wrote none
at all, so the second board shipped with no audit trail and no answer to
"how long did this sit in Assinatura?".

Config-per-board rather than code-per-board makes that class of divergence
unrepresentable: there is one implementation, so a fix or a feature lands for
every pipeline at once.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    """Declarative description of one kanban pipeline.

    Attributes:
        pipeline: Stable key stored on `pipeline_stages.pipeline` and
            `pipeline_movimentos.pipeline`. Identifies the board.
        card_table: The table holding the cards (e.g. ``negociacoes_venda``).
        value_field: Column carrying the card's monetary value. The two boards
            genuinely disagree here — ``valor_estimado`` on a deal that might
            close, ``valor`` on one that did — so it is configured rather than
            normalised, which would have meant renaming a column to suit the
            abstraction.
        entity_label: Human noun for error messages ("negociação"/"processo").
        entity_label_plural: Its plural. Defaults to a pt-BR derivation, which
            exists because the messages used to append a bare "s" and produced
            "2 negociaçãos" — a user-facing message in broken Portuguese from
            the shared organ, on every board. Declared explicitly for any noun
            the derivation gets wrong.
        entity_kind: What the audit log records as `tipo_entidade`. Both
            routers previously logged the literal ``"cliente"`` while passing a
            negociação/processo id, so audit rows filtered by entity type
            silently mis-joined. Making it required here means a consumer
            cannot forget to say what it is.
        stages_table: Stage-definition table. Defaults to the canonical name.
        history_table: Stage-transition history. Defaults to the canonical name.
        cliente_field: Optional column on the card carrying a cliente id, used
            to denormalise history rows. ``None`` for pipelines with no such
            concept.
    """

    pipeline: str
    card_table: str
    value_field: str
    entity_label: str
    entity_kind: str
    stages_table: str = "pipeline_stages"
    history_table: str = "pipeline_movimentos"
    cliente_field: str | None = "cliente_id"
    entity_label_plural: str | None = None

    def count_label(self, total: int) -> str:
        """``"1 negociação"`` / ``"2 negociações"`` — never ``"2 negociaçãos"``."""
        if total == 1:
            return f"{total} {self.entity_label}"
        return f"{total} {self.entity_label_plural or _pluralize_pt(self.entity_label)}"


def _pluralize_pt(noun: str) -> str:
    """Enough pt-BR to be correct for the nouns this organ actually carries.

    Deliberately NOT a general pluralizer — that is a linguistics project. It
    covers the endings our entity labels use and leaves an explicit
    `entity_label_plural` as the escape hatch for anything else.
    """
    if noun.endswith("ão"):
        return f"{noun[:-2]}ões"      # negociação -> negociações
    if noun.endswith(("r", "z", "s")):
        return f"{noun}es"            # +es, not +s
    if noun.endswith("m"):
        return f"{noun[:-1]}ns"       # homem -> homens
    if noun.endswith("l"):
        return f"{noun[:-1]}is"       # contratual -> contratuais
    return f"{noun}s"
