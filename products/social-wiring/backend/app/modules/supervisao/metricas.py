"""Maya's deterministic metrics engine (maya-blocks CONTRACT §3).

Pure, read-only: every function here only SELECTs, org-filtered, inside one São Paulo calendar
day `[dia 00:00, dia+1 00:00)` converted to UTC. The formulas are EXACTLY §3.2 (rubric `sdr.v2`; `sdr.v1`
differed only in the first-response metrics, which credited human replies to Julia) and the §3.2 tail (human block
rubric `<bloco>.v1`).

Missing data is reported as missing, never as 0:
- a ratio with denominator 0 is `None` (numerator + denominator stored beside it);
- a percentile over zero samples is `None`;
- `handoffs_humanos_por_motivo` is `None` while human handoffs exist in the window but no
  `handoff` event recorded their motivo (S2 emits it; before that the motivo is unknowable);
- every handoff-derived metric is `None` for a window that started before supervision was
  switched on (`supervisionado_desde`): with supervision off no handoff row is written, so a
  count of 0 there would be a lie, not a measurement.
A source read that FAILS raises: the caller writes no scorecard rather than a fabricated one.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

SP = ZoneInfo("America/Sao_Paulo")

RUBRICA_SDR = "sdr.v2"
#: julia-v2 G4: supervision hooks that failed that day raised a `supervisao_falha` event; every scorecard of the org
#: for the day carries their count and `dados_incompletos`, so a day with missing registrations never reads clean.
TIPO_FALHA = "supervisao_falha"
GATILHOS_QUALIFICADO = ("qualificado", "visita", "captacao")
#: nearest-rank quantiles as exact fractions (num, den) -- float `0.9 * n` drifts (0.9 * 70 = 63.000...01).
P50 = (1, 2)
P90 = (9, 10)


# ── calendar ────────────────────────────────────────────────────────────────
def janela(dia: date) -> tuple[datetime, datetime]:
    """`[dia 00:00, dia+1 00:00)` in America/Sao_Paulo, as aware UTC datetimes."""
    inicio = datetime.combine(dia, time.min, tzinfo=SP)
    fim = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=SP)
    return inicio.astimezone(timezone.utc), fim.astimezone(timezone.utc)


def hoje_sp(agora: datetime) -> date:
    return agora.astimezone(SP).date()


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_ts(valor: Any) -> Optional[datetime]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── arithmetic ──────────────────────────────────────────────────────────────
def percentil(valores: Iterable[float], q: tuple[int, int]) -> Optional[float]:
    """Nearest rank: sort ascending, take element `ceil(q·n)` (1-based). `None` when n = 0."""
    ordenados = sorted(valores)
    n = len(ordenados)
    if n == 0:
        return None
    num, den = q
    rank = max(1, -(-num * n // den))  # exact integer ceil
    return float(ordenados[rank - 1])


def razao(numerador: Optional[int], denominador: Optional[int]) -> Optional[float]:
    """Fraction rounded to 4 places; `None` when either side is missing or the denominator is 0."""
    if numerador is None or not denominador:
        return None
    return round(numerador / denominador, 4)


# ── reads ───────────────────────────────────────────────────────────────────
def _linhas(client: Any, tabela: str, colunas: str, org_id: Any, inicio: datetime, fim: datetime,
            coluna_tempo: str = "created_at", filtros: Callable[[Any], Any] | None = None) -> list[dict[str, Any]]:
    """Every row of `tabela` for the org with `coluna_tempo` in `[inicio, fim)` -- paged (no 1 000-row cap)."""

    def fetch(start: int, end: int) -> Any:
        q = (client.table(tabela).select(colunas).eq("org_id", str(org_id))
             .gte(coluna_tempo, iso(inicio)).lt(coluna_tempo, iso(fim)))
        if filtros is not None:
            q = filtros(q)
        return q.order("id").range(start, end).execute().data

    rows = list(iter_paged_rows(fetch, label=f"supervisao {tabela}"))
    # belt and braces: the window is the contract, never trust a backend that ignored a filter
    out = []
    for r in rows:
        t = parse_ts(r.get(coluna_tempo))
        if t is not None and inicio <= t < fim:
            out.append(r)
    return out


def _handoff_metricas_nulas(chaves: Iterable[str]) -> dict[str, Any]:
    return {k: None for k in chaves}


def _nao_assumido(h: dict[str, Any], horas: int, calculado_at: datetime) -> bool:
    if h.get("status") == "expirado":
        return True
    criado = parse_ts(h.get("created_at"))
    return h.get("status") == "emitido" and criado is not None and criado + timedelta(hours=horas) <= calculado_at


def calcular_sdr(client: Any, org_id: Any, dia: date, *, horas_para_assumir: int, calculado_at: datetime,
                 supervisionado_desde: Optional[datetime]) -> dict[str, Any]:
    """Rubric `sdr.v1` (CONTRACT §3.2) for one org and one SP day."""
    inicio, fim = janela(dia)

    leads_entrada = len(_linhas(client, "julia_contatos", "id,created_at", org_id, inicio, fim))

    episodios = _linhas(client, "julia_interacoes", "id,iniciada_at,primeira_resposta_agente_at,primeira_resposta_humana_at",
                        org_id, inicio, fim, coluna_tempo="iniciada_at")
    tempos: list[float] = []
    tempos_humano: list[float] = []
    sem_resposta = 0
    humano_antes_do_agente = 0
    for e in episodios:
        iniciada = parse_ts(e["iniciada_at"])
        agente = parse_ts(e.get("primeira_resposta_agente_at"))
        humano = parse_ts(e.get("primeira_resposta_humana_at"))
        if humano is not None:
            tempos_humano.append((humano - iniciada).total_seconds())
        if agente is None:
            sem_resposta += 1  # answered only by a person (or not at all): Julia did not respond
        else:
            tempos.append((agente - iniciada).total_seconds())
        if humano is not None and (agente is None or humano < agente):
            humano_antes_do_agente += 1

    entregas = _linhas(client, "julia_envio_entregas", "id,contato_id,gatilho,status,created_at", org_id, inicio, fim)
    ok = [r for r in entregas if r.get("status") == "ok"]

    def distintos(gatilhos: tuple[str, ...]) -> int:
        return len({str(r["contato_id"]) for r in ok if r.get("gatilho") in gatilhos})

    qualificados = distintos(GATILHOS_QUALIFICADO)
    frios = distintos(("frio",))
    invalidos = distintos(("invalido",))
    entregas_manuais = sum(1 for r in ok if r.get("gatilho") == "manual")

    bloqueados = _linhas(client, "julia_eventos", "id,payload,created_at", org_id, inicio, fim,
                         filtros=lambda q: q.eq("tipo", "envio_bloqueado"))
    por_motivo: dict[str, int] = {}
    for r in bloqueados:
        motivo = str((r.get("payload") or {}).get("motivo") or "sem_motivo")
        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1

    handoffs_humanos = len(_linhas(client, "julia_atribuicoes", "id,created_at", org_id, inicio, fim,
                                   filtros=lambda q: q.eq("motivo", "handoff")))
    eventos_handoff = _linhas(client, "julia_eventos", "id,payload,created_at", org_id, inicio, fim,
                              filtros=lambda q: q.eq("tipo", "handoff"))
    humanos_por_motivo: Optional[dict[str, int]]
    if handoffs_humanos > 0 and not eventos_handoff:
        humanos_por_motivo = None  # handoffs happened but nothing recorded why (S2 not emitting yet)
    else:
        humanos_por_motivo = {}
        for r in eventos_handoff:
            codigo = str((r.get("payload") or {}).get("motivo_codigo") or "outro")
            humanos_por_motivo[codigo] = humanos_por_motivo.get(codigo, 0) + 1

    metricas: dict[str, Any] = {
        "leads_entrada": leads_entrada,
        "tpr_n": len(tempos),
        "tpr_p50_s": percentil(tempos, P50),
        "tpr_p90_s": percentil(tempos, P90),
        "tpr_sem_resposta": sem_resposta,
        "tpr_humano_n": len(tempos_humano),
        "tpr_humano_p50_s": percentil(tempos_humano, P50),
        "tpr_humano_p90_s": percentil(tempos_humano, P90),
        "respondidos_por_humano_antes_do_agente": humano_antes_do_agente,
        "qualificados": qualificados,
        "qualificacao_taxa": razao(qualificados, leads_entrada),
        "frios": frios,
        "frio_taxa": razao(frios, leads_entrada),
        "invalidos": invalidos,
        "invalido_taxa": razao(invalidos, leads_entrada),
        "entregas_manuais": entregas_manuais,
        "envios_bloqueados": len(bloqueados),
        "envios_bloqueados_por_motivo": por_motivo,
        "handoffs_humanos": handoffs_humanos,
        "handoffs_humanos_por_motivo": humanos_por_motivo,
        "horas_para_assumir": horas_para_assumir,
    }
    if supervisionado_desde is None or inicio < supervisionado_desde:
        metricas.update(_handoff_metricas_nulas(("handoffs_emitidos", "handoffs_nao_assumidos")))
        return metricas
    emitidos = _linhas(client, "atendimento_handoffs", "id,status,created_at", org_id, inicio, fim,
                       filtros=lambda q: q.eq("de_bloco", "sdr"))
    metricas["handoffs_emitidos"] = len(emitidos)
    metricas["handoffs_nao_assumidos"] = sum(1 for h in emitidos if _nao_assumido(h, horas_para_assumir, calculado_at))
    return metricas


CHAVES_HUMANO = ("handoffs_recebidos", "handoffs_assumidos", "assumir_p50_s", "assumir_p90_s", "handoffs_nao_assumidos")


def calcular_bloco_humano(client: Any, org_id: Any, bloco: str, dia: date, *, horas_para_assumir: int,
                          calculado_at: datetime, supervisionado_desde: Optional[datetime]) -> dict[str, Any]:
    """Rubric `<bloco>.v1` (CONTRACT §3.2 tail): handoff metrics of a block run by humans (or a later agent)."""
    inicio, fim = janela(dia)
    if supervisionado_desde is None or inicio < supervisionado_desde:
        return {**_handoff_metricas_nulas(CHAVES_HUMANO), "horas_para_assumir": horas_para_assumir}
    recebidos = _linhas(client, "atendimento_handoffs", "id,status,created_at,assumido_at", org_id, inicio, fim,
                        filtros=lambda q: q.eq("para_bloco", bloco))
    assumidos = [h for h in recebidos if h.get("status") == "assumido"]
    tempos = [(parse_ts(h["assumido_at"]) - parse_ts(h["created_at"])).total_seconds()
              for h in assumidos if h.get("assumido_at")]
    return {
        "handoffs_recebidos": len(recebidos),
        "handoffs_assumidos": len(assumidos),
        "assumir_p50_s": percentil(tempos, P50),
        "assumir_p90_s": percentil(tempos, P90),
        "handoffs_nao_assumidos": sum(1 for h in recebidos if _nao_assumido(h, horas_para_assumir, calculado_at)),
        "horas_para_assumir": horas_para_assumir,
    }


def rubrica(bloco: str) -> str:
    return RUBRICA_SDR if bloco == "sdr" else f"{bloco}.v1"


def marcar_falhas(client: Any, org_id: Any, dia: date, metricas: dict[str, Any]) -> dict[str, Any]:
    """G4: `falhas_registro` = the day's `supervisao_falha` events (a supervision hook failed and said so);
    `dados_incompletos` is true when there is any. Applied to EVERY block's scorecard of the org for that day."""
    inicio, fim = janela(dia)
    falhas = len(_linhas(client, "julia_eventos", "id,created_at", org_id, inicio, fim,
                         filtros=lambda q: q.eq("tipo", TIPO_FALHA)))
    return {**metricas, "falhas_registro": falhas, "dados_incompletos": falhas > 0}


def calcular(client: Any, org_id: Any, bloco: str, dia: date, **kw: Any) -> dict[str, Any]:
    if bloco == "sdr":
        metricas = calcular_sdr(client, org_id, dia, **kw)
    else:
        metricas = calcular_bloco_humano(client, org_id, bloco, dia, **kw)
    return marcar_falhas(client, org_id, dia, metricas)


__all__ = ["RUBRICA_SDR", "TIPO_FALHA", "calcular", "marcar_falhas", "calcular_bloco_humano", "calcular_sdr", "hoje_sp", "iso", "janela",
           "parse_ts", "percentil", "razao", "rubrica"]
