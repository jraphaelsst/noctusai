"""Funnel coherence: commercial events move the atendimento's funil stage.

CONTRACT sw-lead-to-contract §6. One mover, imported by the roteiro, proposta
and intake slices, so "the card is on the stage its commercial state implies"
has a single definition instead of one hand-rolled stage move per slice.

Rules (all from the contract):

* Only FORWARD. An atendimento already on or past the target stage is left
  alone (`motivo='ja_na_etapa'` / `'ja_adiante'`), never dragged back.
* The same completeness gate the manual `mover-etapa` applies
  (`stage_gate.pendencias`) applies here. A refusal is a RETURN VALUE
  (`moveu=False`, `motivo` = the message naming what is missing), never a
  raise: the caller is a roteiro/proposta write that must not fail because the
  funnel is not ready to follow it. The caller surfaces `motivo`.
* A stage is addressed by its `slug` (the contract's `chave`). An org that
  renamed or removed it gets `motivo='etapa_inexistente'`, not a silent skip.
* Every move is recorded by `move_card` in `pipeline_movimentos` with
  `motivo='etapa_auto:<evento>'`; the card timeline renders that row (the
  `etapa_auto` timeline event). No second history table.
* `proposta_aceita` moves to `proposta_decisao` and then calls
  `app.modules.pipeline.aceite.aceitar_proposta` (the one acceptance path,
  contract §5.4). That module is built by the proposta slice and imported LAZILY
  here: when it is not importable the result carries
  `motivo='aceite_indisponivel'`, never a silent skip.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.domain.pipeline import list_stages, move_card
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.pipeline import stage_gate
from app.modules.pipeline.configs import PIPELINE_FUNIL

logger = logging.getLogger(__name__)

STATUS_ABERTA = "aberta"

#: evento -> stage slug (`chave`) it moves the atendimento to.
EVENTO_ETAPA: dict[str, str] = {
    "lead_criado": "qualificacao",
    "roteiro_criado": "visitas",
    "proposta_criada": "proposta_recebida",
    "proposta_aceita": "proposta_decisao",
}

#: `lead_criado` is a no-op by contract: the spawn trigger already places the
#: card. It is accepted (so callers need no special case) and reported.
EVENTOS_NOOP = frozenset({"lead_criado"})


def _actor_id(actor: Any) -> Optional[str]:
    """`actor` may be a user object (`.id`), an id, or None (system)."""
    if actor is None:
        return None
    return str(getattr(actor, "id", actor))


def _resultado(moveu: bool, de: Optional[str], para: Optional[str], motivo: Optional[str], **extra: Any) -> dict:
    return {"moveu": moveu, "de": de, "para": para, "motivo": motivo, **extra}


def mover_por_evento(
    client: Any,
    org_id: Any,
    atendimento_id: Any,
    evento: str,
    actor: Any,
) -> dict:
    """Move the atendimento forward to the stage `evento` implies.

    Returns `{moveu, de, para, motivo}` (`de`/`para` are stage slugs; for
    `proposta_aceita` also `aceite` with the acceptance result when it ran).
    """
    if evento not in EVENTO_ETAPA:
        raise ValueError(f"evento desconhecido: {evento!r}")
    org = str(org_id)
    aid = str(atendimento_id)
    alvo_slug = EVENTO_ETAPA[evento]

    rows = (
        client.table("atendimentos")
        .select("id, status, cliente_id, etapa_id")
        .eq("id", aid)
        .eq("org_id", org)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Atendimento", aid)
    atendimento = rows[0]

    etapas = list_stages(client, PIPELINE_FUNIL, org_id=org)
    por_id = {str(e["id"]): e for e in etapas}
    atual = por_id.get(str(atendimento.get("etapa_id")))
    atual_slug = atual.get("slug") if atual else None

    if evento in EVENTOS_NOOP:
        return _resultado(False, atual_slug, atual_slug, "noop")

    alvo = next((e for e in etapas if e.get("slug") == alvo_slug), None)
    if alvo is None:
        return _resultado(False, atual_slug, None, "etapa_inexistente")

    if atendimento.get("status") != STATUS_ABERTA:
        return _resultado(False, atual_slug, alvo_slug, f"atendimento_{atendimento.get('status')}")

    pos_atual = (atual or {}).get("posicao")
    if atual is not None and pos_atual is not None and pos_atual > alvo["posicao"]:
        return _resultado(False, atual_slug, alvo_slug, "ja_adiante")

    moveu = False
    if atual is not None and str(atual["id"]) == str(alvo["id"]):
        motivo: Optional[str] = "ja_na_etapa"
    else:
        pendentes = stage_gate.pendencias(client, org, atendimento.get("cliente_id"))
        if pendentes:
            return _resultado(False, atual_slug, alvo_slug, stage_gate.mensagem(pendentes), pendencias=pendentes)
        move_card(
            client,
            PIPELINE_FUNIL,
            card_id=aid,
            to_stage_id=str(alvo["id"]),
            user_id=_actor_id(actor),
            motivo=f"etapa_auto:{evento}",
            org_id=org,
        )
        moveu = True
        motivo = None

    resultado = _resultado(moveu, atual_slug, alvo_slug, motivo)
    if evento == "proposta_aceita":
        resultado = _aceitar(client, org, aid, actor, resultado)
    return resultado


def _aceitar(client: Any, org: str, aid: str, actor: Any, resultado: dict) -> dict:
    """Run the one acceptance path after the stage move (contract §5.4)."""
    try:
        from app.modules.pipeline.aceite import aceitar_proposta
    except ImportError:
        logger.warning("funil_eventos: pipeline.aceite not importable; aceite skipped (atendimento %s)", aid)
        return {**resultado, "motivo": "aceite_indisponivel"}
    try:
        aceite = aceitar_proposta(client, org, aid, _actor_id(actor))
    except (ValidationError_, NotFoundError) as exc:
        return {**resultado, "motivo": f"aceite_recusado: {exc}"}
    return {**resultado, "aceite": aceite}
