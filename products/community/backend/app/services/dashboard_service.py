"""Dashboard KPIs + series — CONTRACT.md §Cashflow + dashboard, slice BE-C.

Every KPI/series formula below is the contract's own literal wording
("Definitions (tests assert these)"). Nothing is sampled or hardcoded —
every number is derived from `membros`, `planos`, `assinaturas`,
`lancamentos` and `grupoterapia_*` rows fetched for THIS org, paged via
`iter_paged_rows` rather than a bare unbounded select (a 24-month window
can legitimately cross PostgREST's 1 000-row cap — KB §
PATTERNS/backend/postgrest-row-cap.md). "Now" is read through
`noctusai_lib.primitives.timeutil.now_utc()`/`today_utc()` so tests pin
it via `frozen_time(...)` instead of monkeypatching this module.

State reconstruction (`estado_em`)
-----------------------------------
`assinaturas` stores only the LATEST transition timestamps (`ativa_em`,
`cancelada_em`, `expirada_em`) — there is no state-history table — so
"MRR as of a past month-end" (`mensal[].mrr_centavos`) and "the base for
this month's churn" are both reconstructed from exactly those three
columns, as the contract names them. `carencia`/`inadimplente` have no
historical timestamp of their own (`inadimplente_desde`/`carencia_ate`
track only the CURRENT episode) — under this reconstruction a
subscription that was in `carencia` during month M but is `ativa` again
by the report month reads as the same group ("ativa_ou_carencia") for M,
which is the closest approximation the stored columns support. This is
reported as a contract deviation in the delivery note, not silently
assumed.

Two DIFFERENT MRR reads
------------------------
The top-level `kpis.mrr_centavos`/`arpu_centavos`/`em_carencia` read the
CURRENT `assinaturas.estado` column directly (contract: "subscriptions
in {ativa, carencia}" — present tense). `mensal[].mrr_centavos` uses the
`estado_em()` reconstruction instead (contract: "reconstructed from
ativa_em/cancelada_em/expirada_em"), because it is asking about a PAST
month-end. Using the same current-estado shortcut for both would silently
compute every past month's MRR off today's subscription roster.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.timeutil import now_utc, today_utc

_MEMBROS_TABLE = "membros"
_PLANOS_TABLE = "planos"
_ASSINATURAS_TABLE = "assinaturas"
_LANCAMENTOS_TABLE = "lancamentos"
_GT_SESSOES_TABLE = "grupoterapia_sessoes"
_GT_RESERVAS_TABLE = "grupoterapia_reservas"

#: CONTRACT.md: "membros_ativos = status ∈ {ativo, atrasado}". Kept as a
#: literal local constant (not imported from `acesso_service.
#: STATUS_COM_ACESSO`, which is semantically about ENTITLEMENTS, not
#: this specific KPI) so this module's own contract citation stays
#: self-contained and doesn't silently drift if the two concepts diverge.
MEMBROS_ATIVOS_STATUSES = frozenset({"ativo", "atrasado"})

#: CONTRACT.md: "mrr_centavos = Σ plan price ... over subscriptions in
#: {ativa, carencia}".
MRR_ESTADOS = frozenset({"ativa", "carencia"})


# ── pure helpers (unit-testable in isolation — one per contract definition) ──


def _to_date(value: Any) -> date | None:
    """Coerce a DB timestamp/date value (str, date, datetime or None) to
    a `date`."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _to_datetime(value: Any) -> datetime | None:
    """Coerce a DB timestamp value to an aware UTC `datetime`."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def month_bounds(ano: int, mes: int) -> tuple[date, date]:
    """(first day, last day) of `ano-mes`."""
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_window(meses: int, reference: date) -> list[date]:
    """The first day of each of the `meses` calendar months ending at
    `reference`'s own month, OLDEST FIRST (contract: "All months in the
    window are present (zero-filled), oldest first")."""
    out: list[date] = []
    y, m = reference.year, reference.month
    for _ in range(meses):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    return out


def monthly_equivalent_centavos(preco_centavos: int, ciclo: str) -> int:
    """The plan's price expressed as a MONTHLY amount (contract: "Σ plan
    price (anual ÷ 12, rounded)"). `mensal` passes through unchanged;
    `anual` divides by 12 with standard money rounding (half-up) — the
    same convention `products/core/backend/app/services/billing_metrics.py`
    uses for the identical "yearly ÷ 12" conversion.
    """
    if ciclo != "anual":
        return preco_centavos
    return int(
        (Decimal(preco_centavos) / Decimal(12)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def estado_em(assinatura: dict[str, Any], as_of: date) -> str:
    """The subscription's reconstructed state GROUP as of `as_of`, from
    `ativa_em`/`cancelada_em`/`expirada_em` only (contract: "reconstructed
    from ativa_em/cancelada_em/expirada_em"). One of:

    - `"ativa_ou_carencia"` — counts toward a reconstructed MRR/churn-base
    - `"cancelada"` / `"expirada"` — already ended by `as_of`
    - `"nenhuma"` — not yet active as of `as_of` (or never activated)
    """
    ativa_em = _to_date(assinatura.get("ativa_em"))
    if ativa_em is None or ativa_em > as_of:
        return "nenhuma"
    cancelada_em = _to_date(assinatura.get("cancelada_em"))
    if cancelada_em is not None and cancelada_em <= as_of:
        return "cancelada"
    expirada_em = _to_date(assinatura.get("expirada_em"))
    if expirada_em is not None and expirada_em <= as_of:
        return "expirada"
    return "ativa_ou_carencia"


def churn_transition_date(assinatura: dict[str, Any]) -> date | None:
    """The date THIS subscription became `cancelada`/`expirada` — the
    timestamp matching its CURRENT `estado`, or None when it is
    currently in neither terminal state."""
    if assinatura.get("estado") == "cancelada":
        return _to_date(assinatura.get("cancelada_em"))
    if assinatura.get("estado") == "expirada":
        return _to_date(assinatura.get("expirada_em"))
    return None


def _pct(numerator: int, denominator: int) -> float:
    """`numerator / denominator * 100`, 0.0 when the base is 0 (every
    contract percentage definition names this rule explicitly)."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _round_div_centavos(numerator: int, denominator: int) -> int:
    """Integer division with standard money rounding (half-up), 0 when
    the base is 0 (contract: "arpu = mrr ÷ paying members (0 when none)")."""
    if denominator <= 0:
        return 0
    return int(
        (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


class DashboardService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── fetch (paged — KB § PATTERNS/backend/postgrest-row-cap.md) ─────

    def _fetch_all(self, table: str, *, select: str = "*") -> list[dict]:
        def _page(start: int, end: int):
            return (
                self._client.table(table).select(select)
                .eq("org_id", self._org_id)
                .order("id").range(start, end).execute().data
            )

        return list(iter_paged_rows(_page, label=f"{table} (dashboard) org={self._org_id}"))

    def _fetch_lancamentos(self, *, de: date, ate: date) -> list[dict]:
        def _page(start: int, end: int):
            return (
                self._client.table(_LANCAMENTOS_TABLE).select("*")
                .eq("org_id", self._org_id)
                .gte("data", de.isoformat()).lte("data", ate.isoformat())
                .order("id").range(start, end).execute().data
            )

        return list(iter_paged_rows(_page, label=f"lancamentos (dashboard) org={self._org_id}"))

    def _fetch_reservas_confirmadas_por_sessao(self) -> dict[str, int]:
        def _page(start: int, end: int):
            return (
                self._client.table(_GT_RESERVAS_TABLE).select("id,sessao_id,status")
                .eq("org_id", self._org_id).eq("status", "confirmada")
                .order("id").range(start, end).execute().data
            )

        rows = list(iter_paged_rows(
            _page, label=f"grupoterapia_reservas (dashboard) org={self._org_id}",
        ))
        counts: dict[str, int] = {}
        for r in rows:
            sid = str(r.get("sessao_id"))
            counts[sid] = counts.get(sid, 0) + 1
        return counts

    # ── build ────────────────────────────────────────────────────────

    async def build(self, *, meses: int = 12) -> dict:
        now = now_utc()
        hoje = today_utc()
        cur_start, cur_end = month_bounds(hoje.year, hoje.month)
        window_start = month_window(meses, hoje)[0]

        membros = self._fetch_all(_MEMBROS_TABLE)
        planos = self._fetch_all(_PLANOS_TABLE)
        assinaturas = self._fetch_all(_ASSINATURAS_TABLE)
        lancamentos_janela = self._fetch_lancamentos(de=window_start, ate=cur_end)
        sessoes = self._fetch_all(_GT_SESSOES_TABLE)
        reservas_por_sessao = self._fetch_reservas_confirmadas_por_sessao()

        planos_by_id = {str(p["id"]): p for p in planos}

        kpis = self._compute_kpis(
            membros=membros, planos_by_id=planos_by_id, assinaturas=assinaturas,
            lancamentos_janela=lancamentos_janela,
            hoje=hoje, cur_start=cur_start, cur_end=cur_end,
        )
        series = {
            "mensal": self._compute_mensal(
                meses=meses, reference=hoje, membros=membros, assinaturas=assinaturas,
                planos_by_id=planos_by_id, lancamentos_janela=lancamentos_janela,
            ),
            "origem_membros": self._group_counts(membros, "origem"),
            "status_membros": self._group_counts(membros, "status"),
            "grupoterapia": self._compute_grupoterapia_series(
                sessoes, reservas_por_sessao, now=now,
            ),
        }
        return {"kpis": kpis, "series": series, "gerado_em": now}

    # ── KPIs ─────────────────────────────────────────────────────────

    def _compute_kpis(
        self, *, membros, planos_by_id, assinaturas, lancamentos_janela,
        hoje: date, cur_start: date, cur_end: date,
    ) -> dict:
        membros_total = len(membros)
        membros_ativos_rows = [m for m in membros if m.get("status") in MEMBROS_ATIVOS_STATUSES]
        membros_ativos = len(membros_ativos_rows)

        mrr_centavos = self._compute_mrr_atual(assinaturas, planos_by_id)
        pagantes = {
            str(a["membro_id"]) for a in assinaturas if a.get("estado") in MRR_ESTADOS
        }
        arpu_centavos = _round_div_centavos(mrr_centavos, len(pagantes))
        em_carencia = sum(1 for a in assinaturas if a.get("estado") == "carencia")

        novos_mes = sum(
            1 for m in membros
            if (d := _to_date(m.get("entrou_em"))) and cur_start <= d <= cur_end
        )
        # Base "at the month's start" reconstructed as of the PREVIOUS
        # month's last day (i.e. before any of this month's own
        # transitions) — see module docstring for why a same-day
        # comparison against `cur_start` would be ambiguous.
        prev_year, prev_month = (cur_start.year, cur_start.month - 1) \
            if cur_start.month > 1 else (cur_start.year - 1, 12)
        prev_month_last_day = month_bounds(prev_year, prev_month)[1]
        base = sum(1 for a in assinaturas if estado_em(a, prev_month_last_day) == "ativa_ou_carencia")
        cancelamentos_mes = sum(
            1 for a in assinaturas
            if (d := churn_transition_date(a)) and cur_start <= d <= cur_end
        )
        churn_mes_pct = _pct(cancelamentos_mes, base)

        lancs_mes = [
            r for r in lancamentos_janela
            if (d := _to_date(r.get("data"))) and cur_start <= d <= cur_end
        ]
        receita_mes_centavos = sum(r["valor_centavos"] for r in lancs_mes if r.get("tipo") == "entrada")
        saidas_mes_centavos = sum(r["valor_centavos"] for r in lancs_mes if r.get("tipo") == "saida")
        saldo_mes_centavos = receita_mes_centavos - saidas_mes_centavos

        pagantes_ativos = sum(
            1 for m in membros_ativos_rows
            if (p := planos_by_id.get(str(m.get("plano_id")))) and (p.get("preco_centavos") or 0) > 0
        )
        conversao_pago_pct = _pct(pagantes_ativos, membros_ativos)

        return {
            "membros_total": membros_total,
            "membros_ativos": membros_ativos,
            "por_plano": self._compute_por_plano(planos_by_id, membros_ativos_rows),
            "mrr_centavos": mrr_centavos,
            "arpu_centavos": arpu_centavos,
            "em_carencia": em_carencia,
            "novos_mes": novos_mes,
            "cancelamentos_mes": cancelamentos_mes,
            "churn_mes_pct": churn_mes_pct,
            "receita_mes_centavos": receita_mes_centavos,
            "saldo_mes_centavos": saldo_mes_centavos,
            "conversao_pago_pct": conversao_pago_pct,
        }

    @staticmethod
    def _compute_mrr_atual(assinaturas: list[dict], planos_by_id: dict[str, dict]) -> int:
        total = 0
        for a in assinaturas:
            if a.get("estado") not in MRR_ESTADOS:
                continue
            plano = planos_by_id.get(str(a.get("plano_id")))
            if not plano:
                continue
            total += monthly_equivalent_centavos(
                plano.get("preco_centavos") or 0, plano.get("ciclo") or "mensal",
            )
        return total

    @staticmethod
    def _compute_por_plano(planos_by_id: dict[str, dict], membros_ativos_rows: list[dict]) -> list[dict]:
        contagem: dict[str, int] = {}
        for m in membros_ativos_rows:
            pid = m.get("plano_id")
            if pid:
                contagem[str(pid)] = contagem.get(str(pid), 0) + 1
        planos_ordenados = sorted(
            planos_by_id.values(), key=lambda p: (p.get("ordem") or 0, p.get("nome") or ""),
        )
        out = []
        for p in planos_ordenados:
            pid = str(p["id"])
            nivel = (p.get("entitlements") or {}).get("grupoterapia") or "nenhum"
            out.append({
                "plano_id": pid, "nome": p["nome"], "nivel_grupoterapia": nivel,
                "membros": contagem.get(pid, 0),
            })
        return out

    # ── series ───────────────────────────────────────────────────────

    def _compute_mensal(
        self, *, meses: int, reference: date, membros: list[dict],
        assinaturas: list[dict], planos_by_id: dict[str, dict],
        lancamentos_janela: list[dict],
    ) -> list[dict]:
        lanc_por_mes: dict[str, list[dict]] = {}
        for r in lancamentos_janela:
            d = _to_date(r.get("data"))
            if d is None:
                continue
            lanc_por_mes.setdefault(month_key(d), []).append(r)

        novos_por_mes: dict[str, int] = {}
        for m in membros:
            d = _to_date(m.get("entrou_em"))
            if d is None:
                continue
            key = month_key(d)
            novos_por_mes[key] = novos_por_mes.get(key, 0) + 1

        churn_por_mes: dict[str, int] = {}
        for a in assinaturas:
            d = churn_transition_date(a)
            if d is None:
                continue
            key = month_key(d)
            churn_por_mes[key] = churn_por_mes.get(key, 0) + 1

        out = []
        for month_start in month_window(meses, reference):
            _, month_end = month_bounds(month_start.year, month_start.month)
            key = month_key(month_start)
            lancs = lanc_por_mes.get(key, [])
            entradas = sum(r["valor_centavos"] for r in lancs if r.get("tipo") == "entrada")
            saidas = sum(r["valor_centavos"] for r in lancs if r.get("tipo") == "saida")
            mrr = 0
            for a in assinaturas:
                if estado_em(a, month_end) != "ativa_ou_carencia":
                    continue
                plano = planos_by_id.get(str(a.get("plano_id")))
                if not plano:
                    continue
                mrr += monthly_equivalent_centavos(
                    plano.get("preco_centavos") or 0, plano.get("ciclo") or "mensal",
                )
            out.append({
                "mes": key,
                "entradas_centavos": entradas,
                "saidas_centavos": saidas,
                "novos_membros": novos_por_mes.get(key, 0),
                "cancelamentos": churn_por_mes.get(key, 0),
                "mrr_centavos": mrr,
            })
        return out

    @staticmethod
    def _group_counts(rows: list[dict], field: str) -> list[dict]:
        counts: dict[str, int] = {}
        for r in rows:
            key = r.get(field) or "desconhecido"
            counts[key] = counts.get(key, 0) + 1
        return [{field: k, "membros": v} for k, v in sorted(counts.items())]

    @staticmethod
    def _compute_grupoterapia_series(
        sessoes: list[dict], reservas_por_sessao: dict[str, int], *, now: datetime,
    ) -> list[dict]:
        """The next 10 (upcoming, soonest first) and last 10 (most
        recently held) sessions, returned in one chronologically-ordered
        list (contract: "grupoterapia = the next 10 and last 10 sessions")."""
        com_inicio = [(s, dt) for s in sessoes if (dt := _to_datetime(s.get("inicio"))) is not None]
        futuras = sorted((s for s, dt in com_inicio if dt >= now), key=lambda s: s["inicio"])[:10]
        passadas = sorted(
            (s for s, dt in com_inicio if dt < now), key=lambda s: s["inicio"], reverse=True,
        )[:10]
        combinadas = sorted(passadas + futuras, key=lambda s: s["inicio"])
        return [
            {
                "sessao_id": s["id"], "titulo": s["titulo"], "inicio": s["inicio"],
                "vagas_fala": s["vagas_fala"],
                "reservas": reservas_por_sessao.get(str(s["id"]), 0),
            }
            for s in combinadas
        ]
