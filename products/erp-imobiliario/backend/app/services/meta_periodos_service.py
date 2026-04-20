"""
Meta Períodos Service — business logic for period CRUD and auto-generation.

Periods form a parent-child tree: quinzenal → mensal → trimestral → anual.
When the owner picks "generate for Q1 2026", this service produces a
trimestral root + 3 mensal children + 6 quinzenal grandchildren.

All date math is done in Python (no DB RPC round-trips), so the auto-
generation is testable without a live database.

See products/erp-imobiliario/METAS-PLAN.md §5 for design context.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from typing import Literal

logger = logging.getLogger(__name__)

TipoPeriodo = Literal["quinzenal", "mensal", "trimestral", "anual"]

VALID_TIPOS: set[str] = {"diaria", "semanal", "quinzenal", "mensal", "trimestral", "anual"}


# ── CRUD ─────────────────────────────────────────────────────────────

def listar_periodos(db, *, org_id: str | None = None, tipo: str | None = None) -> list[dict]:
    query = db.table("meta_periodos").select("*")
    if org_id:
        query = query.eq("org_id", org_id)
    if tipo:
        query = query.eq("tipo", tipo)
    result = query.order("data_inicio").execute()
    return result.data or []


def obter_periodo(db, periodo_id: str) -> dict | None:
    result = db.table("meta_periodos").select("*").eq("id", periodo_id).limit(1).execute()
    return (result.data or [None])[0]


def criar_periodo(db, *, org_id: str, nome: str, tipo: str,
                  data_inicio: str, data_fim: str,
                  parent_periodo_id: str | None = None) -> dict:
    if tipo not in VALID_TIPOS:
        raise ValueError(f"tipo inválido: {tipo}")
    payload = {
        "org_id": org_id,
        "nome": nome.strip(),
        "tipo": tipo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "parent_periodo_id": parent_periodo_id,
        "status": "aberto",
    }
    result = db.table("meta_periodos").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao criar período")
    return result.data[0]


def atualizar_periodo(db, periodo_id: str, patch: dict) -> dict:
    clean = {k: v for k, v in patch.items() if v is not None}
    if not clean:
        existing = obter_periodo(db, periodo_id)
        if existing is None:
            raise LookupError("Período não encontrado")
        return existing
    if "tipo" in clean and clean["tipo"] not in VALID_TIPOS:
        raise ValueError(f"tipo inválido: {clean['tipo']}")
    result = db.table("meta_periodos").update(clean).eq("id", periodo_id).execute()
    if not result.data:
        raise LookupError("Período não encontrado")
    return result.data[0]


def deletar_periodo(db, periodo_id: str) -> None:
    """Hard delete — cascades to metas_empresa / metas_equipe via FK ON DELETE CASCADE."""
    result = db.table("meta_periodos").delete().eq("id", periodo_id).execute()
    if not result.data:
        raise LookupError("Período não encontrado")


# ── Date math (pure, testable) ──────────────────────────────────────

def quinzena_bounds(ref: date) -> tuple[date, date]:
    """Return (inicio, fim) of the quinzena containing `ref`.

    Quinzenas: days 1–15 and 16–<last day of month>.
    """
    if ref.day <= 15:
        inicio = ref.replace(day=1)
        fim = ref.replace(day=15)
    else:
        inicio = ref.replace(day=16)
        last_day = calendar.monthrange(ref.year, ref.month)[1]
        fim = ref.replace(day=last_day)
    return inicio, fim


def mes_bounds(ref: date) -> tuple[date, date]:
    inicio = ref.replace(day=1)
    last_day = calendar.monthrange(ref.year, ref.month)[1]
    fim = ref.replace(day=last_day)
    return inicio, fim


def trimestre_bounds(year: int, quarter: int) -> tuple[date, date]:
    """Quarter is 1-4. Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"trimestre inválido: {quarter}")
    start_month = 3 * (quarter - 1) + 1
    end_month = start_month + 2
    inicio = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    fim = date(year, end_month, last_day)
    return inicio, fim


def _months_in_trimestre(year: int, quarter: int) -> list[int]:
    start = 3 * (quarter - 1) + 1
    return [start, start + 1, start + 2]


def _month_name_pt(month: int) -> str:
    names = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return names[month]


# ── Auto-generation ─────────────────────────────────────────────────

def plan_trimestre_structure(year: int, quarter: int) -> dict:
    """Return a deterministic nested plan for a trimestre WITHOUT touching the DB.

    Useful for tests and for UI preview before confirming creation.
    Shape: {trimestre: {...}, meses: [{mes, quinzenas: [...]}]}
    """
    t_start, t_end = trimestre_bounds(year, quarter)
    trimestre = {
        "nome": f"{quarter}º Trimestre {year}",
        "tipo": "trimestral",
        "data_inicio": t_start.isoformat(),
        "data_fim": t_end.isoformat(),
    }
    meses = []
    for month in _months_in_trimestre(year, quarter):
        m_start, m_end = mes_bounds(date(year, month, 1))
        q1_start, q1_end = quinzena_bounds(date(year, month, 1))
        q2_start, q2_end = quinzena_bounds(date(year, month, 16))
        meses.append({
            "mes": {
                "nome": f"{_month_name_pt(month)} {year}",
                "tipo": "mensal",
                "data_inicio": m_start.isoformat(),
                "data_fim": m_end.isoformat(),
            },
            "quinzenas": [
                {
                    "nome": f"{_month_name_pt(month)} {year} — 1ª quinzena",
                    "tipo": "quinzenal",
                    "data_inicio": q1_start.isoformat(),
                    "data_fim": q1_end.isoformat(),
                },
                {
                    "nome": f"{_month_name_pt(month)} {year} — 2ª quinzena",
                    "tipo": "quinzenal",
                    "data_inicio": q2_start.isoformat(),
                    "data_fim": q2_end.isoformat(),
                },
            ],
        })
    return {"trimestre": trimestre, "meses": meses}


def gerar_trimestre(db, *, org_id: str, year: int, quarter: int) -> dict:
    """Create the trimestral + mensal + quinzenal period chain for a quarter.

    Idempotent-ish: if a trimestre with identical (org_id, nome, data_inicio, data_fim)
    already exists, reuses it rather than duplicating. Child periods are
    created fresh only if their (org_id, nome, data_inicio, data_fim) triple
    doesn't exist yet.

    Returns the created/reused structure with DB IDs attached.
    """
    plan = plan_trimestre_structure(year, quarter)

    # 1. Trimestre (reuse if already present by name + bounds)
    trimestre_row = _get_or_create_periodo(db, org_id=org_id, **plan["trimestre"])

    # 2. Months → children of trimestre
    meses_out = []
    for m in plan["meses"]:
        mes_row = _get_or_create_periodo(
            db, org_id=org_id, parent_periodo_id=trimestre_row["id"], **m["mes"]
        )
        quinzenas_out = []
        for q in m["quinzenas"]:
            q_row = _get_or_create_periodo(
                db, org_id=org_id, parent_periodo_id=mes_row["id"], **q
            )
            quinzenas_out.append(q_row)
        meses_out.append({"mes": mes_row, "quinzenas": quinzenas_out})

    return {"trimestre": trimestre_row, "meses": meses_out}


def _get_or_create_periodo(db, *, org_id: str, nome: str, tipo: str,
                           data_inicio: str, data_fim: str,
                           parent_periodo_id: str | None = None) -> dict:
    existing = (
        db.table("meta_periodos").select("*")
        .eq("org_id", org_id)
        .eq("nome", nome)
        .eq("data_inicio", data_inicio)
        .eq("data_fim", data_fim)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]
    return criar_periodo(
        db,
        org_id=org_id,
        nome=nome,
        tipo=tipo,
        data_inicio=data_inicio,
        data_fim=data_fim,
        parent_periodo_id=parent_periodo_id,
    )
