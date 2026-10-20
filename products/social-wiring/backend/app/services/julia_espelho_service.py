"""SW's READ MIRROR of agents' qualification state (julia-v2 CONTRACT 1.2 / 8.1, D4).

Agents owns the qualification: the model records criteria through agents' tools, a pure engine computes score and stage,
and the state lives in agents. SW keeps a DISPLAY MIRROR so its own pages (Leads, Conversas, reports, the CRM note)
keep working without a call per row:

  * `julia_contatos.slots` / `operacao` (+ `nome` / `email` when still empty) and the open `julia_interacoes.slots` --
    written ONLY from agents' answer after a turn (never from a model action: `salvar_slots` / `definir_operacao` are
    retired), so the mirror can lag agents but can never disagree because SW invented a value;
  * `ai_outputs(ref_type='julia_contato', kind='score', label=<stage>, score)` -- the seed P1 pattern, written when the
    computed stage or score CHANGES (so the table is a history of qualification, not one row per turn).

Nothing here ever decides anything: SW's triggers (the CRM send) read the stage agents computed (`julia_envio_service`),
not this mirror. Every function is best-effort and never raises into the turn path -- the reply is already out.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional
from uuid import UUID

from noctusai_lib.domain.ai.outputs import fetch_outputs_for, safe_persist_indicator

from app.clients.agents import AgentsClient, AgentsClientError, QualificacaoEstado, QualificacaoResumo, TurnResult
from app.services import julia_contatos_service as contatos
from app.services import julia_slots_sensiveis as sensiveis

logger = logging.getLogger(__name__)

REF_TYPE = "julia_contato"
SLOT_VALOR_MAX = 500
_OPERACOES_ESPELHO = frozenset({"compra", "aluguel", "administracao"})
_EMAIL_RE = re.compile(r"^[^@\s]{1,100}@[^@\s]{1,100}\.[^@\s]{2,30}$")


def _texto(valor: Any) -> Optional[str]:
    """One recorded value as the display text the Leads page always showed (a string)."""
    if valor is None or isinstance(valor, dict):
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (list, tuple)):
        itens = [str(i).strip() for i in valor if i is not None and not isinstance(i, (dict, list))]
        texto = ", ".join(i for i in itens if i)
    else:
        texto = str(valor).strip()
    return texto[:SLOT_VALOR_MAX] or None


def slots_do_espelho(valores: Mapping[str, Any]) -> dict[str, str]:
    """`valores` (agents' recorded criteria) -> the string slots of the mirror. The columns `nome` / `email` /
    `operacao` are columns, handled apart; sensitive keys are never mirrored."""
    saida: dict[str, str] = {}
    for chave, valor in valores.items():
        chave = str(chave)
        if chave in sensiveis.SENSIVEIS or chave in ("nome", "email", "operacao"):
            continue
        texto = _texto(valor)
        if texto is not None:
            saida[chave] = texto
    return saida


def aplicar_valores(client: Any, org_id: UUID | str, contato: dict[str, Any], valores: Mapping[str, Any],
                    interacao: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Write the mirror columns from agents' `valores`; only what changed. Returns the patch applied."""
    atual = contato
    patch: dict[str, Any] = {}
    slots = slots_do_espelho(valores)
    if slots != (atual.get("slots") or {}):
        patch["slots"] = slots
    operacao = valores.get("operacao")
    if operacao in _OPERACOES_ESPELHO and operacao != atual.get("operacao"):
        patch["operacao"] = operacao
    nome = _texto(valores.get("nome"))
    if nome and not (atual.get("nome") or "").strip():
        patch["nome"] = nome[:200]
    email = _texto(valores.get("email"))
    if email and _EMAIL_RE.match(email) and not (atual.get("email") or "").strip():
        patch["email"] = email.lower()
    if patch:
        contatos.atualizar_contato(client, contato["id"], patch)
        if interacao is not None:
            inter_patch = {k: v for k, v in patch.items() if k in ("slots", "operacao")}
            if inter_patch:
                client.table(contatos.T_INTERACOES).update(inter_patch).eq("id", str(interacao["id"])).execute()
    return patch


def registrar_estagio(client: Any, contato_id: UUID | str, resumo: Optional[QualificacaoResumo]) -> bool:
    """`ai_outputs` row for a CHANGED computed stage/score. True = a row was written."""
    if resumo is None or not resumo.estagio:
        return False
    try:
        ultimos = fetch_outputs_for(client, None, REF_TYPE, str(contato_id), limit=1)
        if ultimos and ultimos[0].get("label") == resumo.estagio and _num(ultimos[0].get("score")) == _num(resumo.score):
            return False
        out = safe_persist_indicator(
            client, schema=None, ref_type=REF_TYPE, ref_id=str(contato_id),
            out={
                "kind": "score", "label": resumo.estagio, "score": resumo.score, "chip": resumo.estagio[:20],
                "prompt_version": resumo.versao,
            },
            logger=logger,
        )
        return out.get("id") is not None
    except Exception:
        logger.exception("julia: could not mirror the stage into ai_outputs contato=%s", contato_id)
        return False


def _num(valor: Any) -> Optional[float]:
    try:
        return None if valor is None else float(valor)
    except (TypeError, ValueError):
        return None


async def espelhar_apos_turno(
    client: Any, *, org_id: UUID | str, contato: dict[str, Any], result: TurnResult,
    agents_client: Optional[AgentsClient], interacao: Optional[dict[str, Any]] = None,
) -> Optional[QualificacaoResumo]:
    """After a turn agents SERVED: refresh the mirror from agents' computed state. The values come from the `lead_pronto`
    action when this turn carried one (it embeds `valores`), else from `GET .../qualificacao` (one cheap read). Never
    raises; returns the stage summary the caller's triggers may use (None when agents sent no qualification)."""
    resumo = result.qualificacao
    if resumo is None and not any(a.type == "lead_pronto" for a in result.julia_actions):
        return None
    try:
        valores: Optional[Mapping[str, Any]] = next(
            (a.payload.get("valores") for a in result.julia_actions if a.type == "lead_pronto"
             and isinstance(a.payload.get("valores"), dict)), None,
        )
        if valores is None and agents_client is not None:
            try:
                estado: Optional[QualificacaoEstado] = await agents_client.qualificacao(str(contato["id"]))
            except AgentsClientError as exc:
                logger.warning("julia: qualification read failed (%s) contato=%s -- mirror keeps its last values",
                               type(exc).__name__, contato.get("id"))
                estado = None
            if estado is not None:
                valores = estado.valores
                if resumo is None:
                    resumo = QualificacaoResumo(estagio=estado.estagio, score=estado.score, faltando=estado.faltando,
                                                estagios=estado.estagios)
        if valores is not None:
            aplicar_valores(client, org_id, contato, valores, interacao)
        registrar_estagio(client, contato["id"], resumo)
    except Exception:
        logger.exception("julia: qualification mirror failed contato=%s (the reply IS out)", contato.get("id"))
    return resumo


async def qualificacao_do_contato(
    client: Any, org_id: UUID | str, contato: dict[str, Any], agents_client: Optional[AgentsClient],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """For the conversation header / "Dados do lead": `(qualificacao, dados_lead)`.

    `qualificacao` = `{estagio, rotulo, score, fonte}` and `dados_lead` = `{valores, faltando, fonte}`; label and
    score only, NEVER a rule, weight or criterion body. `fonte` is `agents` (live read of the computed state) or
    `espelho` (SW's own last mirror: the `ai_outputs` stage row + the contato's slots) when agents is
    unconfigured/unreachable. Either is None when nothing is known. Never raises."""
    estado: Optional[QualificacaoEstado] = None
    rotulos: dict[str, str] = {}
    if agents_client is not None:
        try:
            estado = await agents_client.qualificacao(str(contato["id"]))
            if estado is not None:
                rotulos = {e.chave: e.rotulo for e in await agents_client.estagios("julia")}
        except AgentsClientError as exc:
            logger.warning("julia: qualification read failed (%s) contato=%s -- falling back to the mirror",
                           type(exc).__name__, contato.get("id"))
    if estado is not None and estado.estagio:
        qualificacao = {"estagio": estado.estagio, "rotulo": rotulos.get(estado.estagio), "score": estado.score, "fonte": "agents"}
        dados = {"valores": slots_do_espelho(estado.valores), "faltando": list(estado.faltando), "fonte": "agents"}
        return qualificacao, dados
    qualificacao = None
    try:
        ultimos = fetch_outputs_for(client, None, REF_TYPE, str(contato["id"]), limit=1)
        if ultimos and ultimos[0].get("label"):
            qualificacao = {"estagio": ultimos[0]["label"], "rotulo": rotulos.get(ultimos[0]["label"]),
                            "score": ultimos[0].get("score"), "fonte": "espelho"}
    except Exception:
        logger.exception("julia: could not read the mirrored stage contato=%s", contato.get("id"))
    slots = contato.get("slots") or {}
    dados = {"valores": dict(slots), "faltando": [], "fonte": "espelho"} if slots else None
    return qualificacao, dados


__all__ = ["REF_TYPE", "aplicar_valores", "espelhar_apos_turno", "qualificacao_do_contato", "registrar_estagio", "slots_do_espelho"]
