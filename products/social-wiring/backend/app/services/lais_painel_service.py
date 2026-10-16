"""Lais > Início "Painel" (wave 9): the live numbers of the landing page, for one month.

Everything is computed in America/Sao_Paulo (month edges AND the hour/weekday buckets), from
`lais_contatos` (the funnel and every chart: one row per person Julia talks to, bucketed by
`created_at` = first contact), `lais_eventos` (Cobranças de atendimento) and `lais_visitas`
(Pré-agendamentos). The agents side ("Consumo do plano") is a live call that may fail: it then
reads `null`, never an error.

A7: a member only sees the numbers of the contatos they own (`lais_acesso`); admins see the whole org.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import AgentsClient, AgentsClientError
from app.services import lais_acesso
from app.services.lais_envio_service import STATUS_ENVIADOS

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")
T_CONTATOS = "lais_contatos"
T_EVENTOS = "lais_eventos"
T_VISITAS = "lais_visitas"
TIPO_COBRANCA = "cobranca_atendimento"
HORA_INICIO, HORA_FIM = 8, 20  # business hours [08:00, 20:00); anything else is "fora do horário"
MESES_HISTORICO = 6
_MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def mes_atual() -> str:
    return datetime.now(TZ).strftime("%Y-%m")


def validar_mes(mes: Optional[str]) -> str:
    """`YYYY-MM`; omitted -> the current month in Sao Paulo."""
    if mes is None:
        return mes_atual()
    if not _MES_RE.match(mes):
        raise AppException("mes_invalido", "Use mes=YYYY-MM.", status_code=422)
    return mes


def _inicio_do_mes(ano: int, mes: int) -> datetime:
    ano += (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return datetime(ano, mes, 1, tzinfo=TZ)


def janela(mes: str) -> tuple[datetime, datetime]:
    """`[start, end)` of the month, as SP-aware datetimes."""
    ano, m = (int(p) for p in mes.split("-"))
    return _inicio_do_mes(ano, m), _inicio_do_mes(ano, m + 1)


def ultimos_meses(mes: str, n: int = MESES_HISTORICO) -> list[str]:
    """The `n` months ending at `mes` (inclusive), oldest first."""
    ano, m = (int(p) for p in mes.split("-"))
    out = []
    for k in range(n - 1, -1, -1):
        d = _inicio_do_mes(ano, m - k)
        out.append(f"{d.year:04d}-{d.month:02d}")
    return out


def _em_sp(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, str) and valor:
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _varrer(client: Any, tabela: str, colunas: str, org_id: UUID | str, ini: datetime, fim: datetime,
            label: str, extra: Optional[Callable[[Any], Any]] = None) -> list[dict[str, Any]]:
    def pagina(a: int, b: int) -> Any:
        q = (
            client.table(tabela).select(colunas).eq("org_id", str(org_id))
            .gte("created_at", _utc(ini)).lt("created_at", _utc(fim))
        )
        if extra:
            q = extra(q)
        return q.order("id").range(a, b).execute().data

    return list(iter_paged_rows(pagina, label=label))


def _estado(contato: dict[str, Any]) -> str:
    st = str(contato.get("status_envio"))
    return "enviado" if st in STATUS_ENVIADOS else ("erro" if st == "erro" else "nao_pronto")


def calcular(contatos: Iterable[dict[str, Any]], *, mes: str) -> dict[str, Any]:
    """Pure math over the (already visible) contatos of the last 6 months."""
    cont = list(contatos)
    ini, fim = janela(mes)
    no_mes: list[dict[str, Any]] = []
    por_mes = {m: {"enviado": 0, "nao_enviado": 0} for m in ultimos_meses(mes)}
    for c in cont:
        dt = _em_sp(c.get("created_at"))
        if dt is None:
            continue
        chave = f"{dt.year:04d}-{dt.month:02d}"
        if chave in por_mes:
            por_mes[chave]["enviado" if _estado(c) == "enviado" else "nao_enviado"] += 1
        if ini <= dt < fim:
            no_mes.append({**c, "_dt": dt})

    canais: dict[str, int] = {}
    status_canal: dict[str, dict[str, int]] = {}
    por_hora = [0] * 24
    por_dia = [0] * 7
    atendidos = enviados = 0
    for c in no_mes:
        canal = c.get("canal") or "whatsapp"
        canais[canal] = canais.get(canal, 0) + 1
        estado = _estado(c)
        status_canal.setdefault(canal, {"enviado": 0, "nao_pronto": 0, "erro": 0})[estado] += 1
        por_hora[c["_dt"].hour] += 1
        por_dia[c["_dt"].weekday()] += 1  # 0 = segunda ... 6 = domingo
        atendidos += 1 if c.get("ultimo_outbound_at") else 0
        enviados += 1 if estado == "enviado" else 0

    topo = len(no_mes)
    fora = sum(n for h, n in enumerate(por_hora) if h < HORA_INICIO or h >= HORA_FIM)
    ordem = sorted(canais, key=lambda k: (-canais[k], k))
    return {
        "funil": {"topo": topo, "atendidos": atendidos, "enviados": enviados},
        "por_canal": [{"canal": k, "total": canais[k]} for k in ordem],
        "status_por_canal": [{"canal": k, **status_canal[k]} for k in ordem],
        "por_hora": por_hora,
        "fora_horario_pct": round(100.0 * fora / topo, 1) if topo else 0.0,
        "por_dia_semana": por_dia,
        "melhor_dia": por_dia.index(max(por_dia)) if topo else None,
        "seis_meses": [{"mes": m, **v} for m, v in por_mes.items()],
    }


async def consumo(client_agents: Optional[AgentsClient], mes: str) -> Optional[dict[str, Any]]:
    """agents' month usage vs the daily cap; `None` when agents is unconfigured / unreachable / refuses."""
    if client_agents is None:
        return None
    try:
        uso = await client_agents.uso(mes)
    except AgentsClientError as exc:
        logger.warning("lais painel: agents uso unavailable (%s)", type(exc).__name__)
        return None
    return {"turnos": uso.turnos, "custo_usd": uso.custo_usd, "limite_diario_usd": uso.limite_diario_usd}


async def painel(client: Any, ctx: lais_acesso.AcessoCtx, *, mes: str, client_agents: Optional[AgentsClient]) -> dict[str, Any]:
    org_id = ctx.org_id
    ini, fim = janela(mes)
    inicio_hist = janela(ultimos_meses(mes)[0])[0]
    contatos = _varrer(
        client, T_CONTATOS,
        "id,org_id,connection_id,responsavel_user_id,canal,status_envio,ultimo_outbound_at,created_at",
        org_id, inicio_hist, fim, "lais painel contatos",
    )
    contatos = lais_acesso.filtrar_contatos(client, ctx, contatos)
    cobrancas = _varrer(client, T_EVENTOS, "id,contato_id", org_id, ini, fim, "lais painel eventos",
                        extra=lambda q: q.eq("tipo", TIPO_COBRANCA))
    visitas = _varrer(client, T_VISITAS, "id,contato_id", org_id, ini, fim, "lais painel visitas")
    cobrancas = lais_acesso.filtrar_por_contato(client, ctx, cobrancas)
    visitas = lais_acesso.filtrar_por_contato(client, ctx, visitas)
    dados = calcular(contatos, mes=mes)
    return {
        "atividades": {
            # org-wide spend is not a member's number (A7): admins only
            "consumo": await consumo(client_agents, mes) if ctx.admin else None,
            "cobrancas": len(cobrancas),
            "pre_agendamentos": len(visitas),
        },
        **dados,
    }


__all__ = ["calcular", "consumo", "janela", "mes_atual", "painel", "ultimos_meses", "validar_mes"]
