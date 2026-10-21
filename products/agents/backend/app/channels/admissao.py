"""Admission control and the loop / flood breaker of a channel turn (Julia v2 guardrails B5).

The goal is to stop somebody trying to break the operation on purpose -- floods, many fresh numbers, bots
talking to the bot, cost burn -- WITHOUT touching a legitimate long conversation. Hence nothing here caps how
long a conversation may be; every limit is a per-agent column of ``canal_limites`` (data, editable in the
Studio), and every refusal is a distinct response status SW routes to a human, never silence.

* :func:`motivo_novo_lead_limitado` -- new-lead admission per hour / per day, and the budget reservation (new
  threads may spend only ``1 - reserva_leads_existentes_pct`` of the org's daily channel cap, so a flood of
  fresh numbers cannot starve the threads already in progress);
* :func:`avisar_orcamento` -- owner alerts when the org's daily cap crosses 50 / 80 / 100 % (one in-app notice
  per admin per day per threshold);
* :func:`detectar_loop` -- three pure signals over the lead's recent messages: the same text again and again,
  an echo of the agent's own last reply, replies faster than a person types.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from app.channels import conformidade as conf
from app.qualificacao.matcher import normalizar

logger = logging.getLogger(__name__)

__all__ = [
    "LIMIARES_ORCAMENTO",
    "MOTIVO_LOOP_ECO",
    "MOTIVO_LOOP_LATENCIA",
    "MOTIVO_LOOP_REPETICAO",
    "MOTIVO_NOVOS_LEADS_DIA",
    "MOTIVO_NOVOS_LEADS_HORA",
    "MOTIVO_ORCAMENTO_RESERVADO",
    "Mensagem",
    "avisar_orcamento",
    "dia_de",
    "detectar_loop",
    "inicio_do_dia",
    "motivo_novo_lead_limitado",
]

_SP = ZoneInfo("America/Sao_Paulo")

MOTIVO_NOVOS_LEADS_HORA = "novos_leads_hora"
MOTIVO_NOVOS_LEADS_DIA = "novos_leads_dia"
MOTIVO_ORCAMENTO_RESERVADO = "orcamento_reservado"
MOTIVO_LOOP_REPETICAO = "repeticao"
MOTIVO_LOOP_ECO = "eco"
MOTIVO_LOOP_LATENCIA = "latencia"

#: The percentages of the daily cap an owner is told about.
LIMIARES_ORCAMENTO = (50, 80, 100)

KIND_ORCAMENTO = "canal_orcamento"
_TITULO_ORCAMENTO = "Limite diário do canal"


def inicio_do_dia(agora: datetime) -> datetime:
    """Start of the São Paulo day containing ``agora``, as a UTC instant (the day the daily caps count)."""
    return agora.astimezone(_SP).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def dia_de(agora: datetime) -> date:
    """The São Paulo calendar day of ``agora`` (the day the daily caps and their notices count)."""
    return agora.astimezone(_SP).date()


# ── new-lead admission + budget reservation ─────────────────────────────────


def motivo_novo_lead_limitado(
    *, conversations: Any, messages: Any, org_id: UUID, agent_id: UUID, limites: Any, agora: datetime,
    teto_diario_usd: float,
) -> str | None:
    """Why a lead the agent never served must NOT be admitted now (``None`` = admit).

    Per-agent counters of threads opened in the last hour / the São Paulo day, then the budget reservation: with a
    daily cap ``teto_diario_usd`` > 0, new threads may only spend ``(1 - reserva_leads_existentes_pct)`` of it."""
    if conversations.count_threads_created_since(
        org_id, agent_id, agora - timedelta(hours=1), ate=limites.max_novos_leads_hora,
    ) >= limites.max_novos_leads_hora:
        return MOTIVO_NOVOS_LEADS_HORA
    if conversations.count_threads_created_since(
        org_id, agent_id, inicio_do_dia(agora), ate=limites.max_novos_leads_dia,
    ) >= limites.max_novos_leads_dia:
        return MOTIVO_NOVOS_LEADS_DIA
    if teto_diario_usd > 0 and limites.reserva_leads_existentes_pct > 0:
        _turnos, gasto = messages.usage_between(org_id, inicio_do_dia(agora), agora + timedelta(seconds=1))
        if gasto >= teto_diario_usd * (100 - limites.reserva_leads_existentes_pct) / 100:
            return MOTIVO_ORCAMENTO_RESERVADO
    return None


def avisar_orcamento(
    sink: Any, org_id: UUID, *, gasto_usd: float, teto_diario_usd: float, dia: date,
) -> list[int]:
    """Tell the org's owners/admins the daily channel cap crossed 50 / 80 / 100 %. One in-app notice per admin per
    day per threshold (deduped by ``dedup_key``). Best effort: a notice that cannot go out is logged, never raised
    -- the turn it follows has already been served. Returns the thresholds crossed."""
    if sink is None or teto_diario_usd <= 0:
        return []
    pct = gasto_usd / teto_diario_usd * 100
    cruzados = [p for p in LIMIARES_ORCAMENTO if pct >= p]
    if not cruzados:
        return []
    try:
        admins = sink.org_admin_ids(org_id)
        for p in cruzados:
            chave = f"{KIND_ORCAMENTO}:{org_id}:{dia.isoformat()}:{p}"
            mensagem = (
                f"O atendimento por canal usou {p}% do limite diário de gasto."
                + (" Novos leads só serão atendidos amanhã." if p >= 100 else "")
            )
            for user_id in admins:
                if sink.already_sent(user_id, chave):
                    continue
                sink.send(
                    user_id, kind=KIND_ORCAMENTO, title=_TITULO_ORCAMENTO, message=mensagem,
                    metadata={"dedup_key": chave, "limiar_pct": p, "product": "agents"}, org_id=org_id,
                )
    except Exception:  # noqa: BLE001 -- the alert is best effort; a failure is a log line, not a failed turn
        logger.exception("agents.canal.orcamento_aviso_falhou org_id=%s", org_id)
    return cruzados


# ── loop / flood / echo breaker ─────────────────────────────────────────────


@dataclass(frozen=True)
class Mensagem:
    """What the breaker reads of a stored message: who, when, the normalised text is derived here."""

    role: str  # "user" | "assistant"
    texto: str
    em: datetime


def _norm(texto: str) -> str:
    return " ".join(normalizar(texto).split())


_DIGITOS = re.compile(r"\d+")


def _repeticao(lead: Sequence[Mensagem], limites: Any) -> bool:
    """The newest lead message again and again: ``loop_repeticoes`` messages (the newest included) of at least
    ``loop_min_chars`` characters, within ``loop_janela_segundos`` of it, that are the same text (similarity >=
    ``loop_similaridade`` and the same numbers -- "2 quartos" then "3 quartos" is a lead refining a search, not a
    repeat)."""
    if not lead:
        return False
    ultima = lead[-1]
    alvo = _norm(ultima.texto)
    if len(alvo) < limites.loop_min_chars:
        return False
    corte = ultima.em - timedelta(seconds=limites.loop_janela_segundos)
    digitos = _DIGITOS.findall(alvo)
    iguais = 0
    for m in lead:
        if m.em < corte:
            continue
        x = _norm(m.texto)
        if len(x) < limites.loop_min_chars or _DIGITOS.findall(x) != digitos:
            continue
        if x == alvo or SequenceMatcher(None, x, alvo).ratio() >= limites.loop_similaridade:
            iguais += 1
    return iguais >= limites.loop_repeticoes


def _eco(lote_lead: Sequence[str], ultima_resposta: str | None, limites: Any) -> bool:
    if not ultima_resposta or not lote_lead:
        return False
    resposta = conf.shingles_de(ultima_resposta, limites.loop_eco_tokens)
    if not resposta:
        return False
    return any(resposta & conf.shingles_de(t, limites.loop_eco_tokens) for t in lote_lead)


def _latencias(historico: Sequence[Mensagem]) -> list[float]:
    """Seconds between each agent reply and the lead's NEXT message, oldest first."""
    out: list[float] = []
    pendente: datetime | None = None
    for m in historico:
        if m.role == "assistant":
            pendente = m.em
        elif m.role == "user" and pendente is not None:
            out.append((m.em - pendente).total_seconds())
            pendente = None
    return out


def _latencia(historico: Sequence[Mensagem], limites: Any) -> bool:
    lat = _latencias(historico)[-limites.loop_trocas:]
    if len(lat) < limites.loop_trocas:
        return False
    return statistics.median(lat) < limites.loop_latencia_mediana_s


def detectar_loop(historico: Sequence[Mensagem], lote_lead: Sequence[str], limites: Any) -> str | None:
    """The loop signal this turn trips, or ``None``. Pure.

    ``historico`` is the thread's recent messages oldest-first, ending with the batch just stored (``user`` rows);
    ``lote_lead`` the texts of that batch. Signals, each a column of ``canal_limites``:

    * ``repeticao`` -- ``loop_repeticoes`` or more recent lead messages that are the same text
      (similarity >= ``loop_similaridade``; texts under ``loop_min_chars`` never count: "ok" three times is a person);
    * ``eco`` -- the inbound contains ``loop_eco_tokens`` consecutive tokens of the agent's own last reply
      (another bot echoing us);
    * ``latencia`` -- the median lead response time over the last ``loop_trocas`` exchanges is under
      ``loop_latencia_mediana_s`` (no human answers that fast, turn after turn).
    """
    if not limites.loop_ativo:
        return None
    lead = [m for m in historico if m.role == "user"]
    if _repeticao(lead, limites):
        return MOTIVO_LOOP_REPETICAO
    ultima = next((m.texto for m in reversed(historico) if m.role == "assistant"), None)
    if _eco(lote_lead, ultima, limites):
        return MOTIVO_LOOP_ECO
    if _latencia(historico, limites):
        return MOTIVO_LOOP_LATENCIA
    return None
