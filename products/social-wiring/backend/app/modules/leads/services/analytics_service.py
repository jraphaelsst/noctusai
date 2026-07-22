"""Analytics endpoints (§5.2/§5.3) — summary / timeseries / by-dimension /
heatmap. All four share the same filtered-rows-in-Python approach as
``leads_service.list_leads`` (see ``services/query.py`` for why); the
aggregation math (share_pct, variação, grouping) is plain Python over a
bounded row set (~12k rows for the source org), not SQL ``GROUP BY``.
"""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from app.modules.leads.services.query import LeadFilters, fetch_filtered

_MES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_TIPO_LABEL = {"novo": "Novo", "retorno": "Retorno", "desconhecido": "Desconhecido"}
_TIER_LABEL = {"simples": "Simples", "destaque": "Destaque", "super_destaque": "Super Destaque"}
_TIPO_ORDER = ["novo", "retorno", "desconhecido"]
_TIER_ORDER = ["simples", "destaque", "super_destaque"]


def _round1(value: float) -> float:
    return round(value, 1)


def _previous_window_rows(
    client: Any, org_id: UUID, filters: LeadFilters
) -> Optional[list[dict]]:
    """Rows for the immediately-preceding window of equal length — only
    resolvable when BOTH ``de``/``ate`` are set on the incoming filters
    (an unbounded window has no well-defined "preceding" length)."""
    if filters.de is None or filters.ate is None:
        return None
    span_days = (filters.ate - filters.de).days + 1
    prev_ate = filters.de - timedelta(days=1)
    prev_de = prev_ate - timedelta(days=span_days - 1)
    prev_filters = dataclasses.replace(filters, de=prev_de, ate=prev_ate)
    return fetch_filtered(client, org_id, prev_filters)


def summary(client: Any, org_id: UUID, filters: LeadFilters, refs: dict) -> dict:
    rows = fetch_filtered(client, org_id, filters)
    total = len(rows)
    novos = sum(1 for r in rows if r.get("tipo_lead") == "novo")
    retornos = sum(1 for r in rows if r.get("tipo_lead") == "retorno")
    origem_ids = {r["origem_id"] for r in rows if r.get("origem_id")}
    corretor_ids = {r["corretor_id"] for r in rows if r.get("corretor_id")}
    empreendimentos = {r["empreendimento"] for r in rows if r.get("empreendimento")}
    needs_review = sum(1 for r in rows if r.get("needs_review"))

    periodo = {
        "de": filters.de.isoformat() if filters.de else None,
        "ate": filters.ate.isoformat() if filters.ate else None,
    }

    comparativo = None
    prev_rows = _previous_window_rows(client, org_id, filters)
    if prev_rows is not None:
        total_anterior = len(prev_rows)
        variacao = (
            _round1((total - total_anterior) / total_anterior * 100)
            if total_anterior > 0
            else None
        )
        comparativo = {"total_anterior": total_anterior, "variacao_pct": variacao}

    if filters.de and filters.ate:
        span_days = (filters.ate - filters.de).days + 1
    else:
        dias = {r["data_entrada"] for r in rows if r.get("data_entrada")}
        span_days = len(dias) or 1
    media_diaria = round(total / span_days, 2) if span_days else 0.0

    top_origem = None
    if origem_ids:
        counts: dict[str, int] = {}
        for r in rows:
            if r.get("origem_id"):
                counts[r["origem_id"]] = counts.get(r["origem_id"], 0) + 1
        top_id = max(counts, key=lambda k: counts[k])
        source = refs["sources_by_id"].get(top_id)
        if source:
            top_origem = {
                "id": top_id,
                "label": source["label"],
                "total": counts[top_id],
                "share_pct": _round1(counts[top_id] / total * 100) if total else 0.0,
            }

    top_corretor = None
    if corretor_ids:
        counts2: dict[str, int] = {}
        for r in rows:
            if r.get("corretor_id"):
                counts2[r["corretor_id"]] = counts2.get(r["corretor_id"], 0) + 1
        top_id2 = max(counts2, key=lambda k: counts2[k])
        corretor = refs["corretores_by_id"].get(top_id2)
        if corretor:
            top_corretor = {"id": top_id2, "nome": corretor["nome"], "total": counts2[top_id2]}

    return {
        "total": total,
        "novos": novos,
        "retornos": retornos,
        "origens_ativas": len(origem_ids),
        "corretores_ativos": len(corretor_ids),
        "empreendimentos": len(empreendimentos),
        "needs_review": needs_review,
        "periodo": periodo,
        "comparativo": comparativo,
        "media_diaria": media_diaria,
        "top_origem": top_origem,
        "top_corretor": top_corretor,
    }


def _bucket_for(row: dict, grain: str) -> Optional[str]:
    data_entrada = row.get("data_entrada")
    ano, mes = row.get("ano"), row.get("mes")
    if grain == "dia":
        return data_entrada
    if grain == "ano":
        return f"{int(ano):04d}" if ano is not None else None
    if ano is None or mes is None:
        return None
    return f"{int(ano):04d}-{int(mes):02d}"


def _label_for(bucket: str, grain: str) -> str:
    if grain == "dia":
        y, m, d = bucket.split("-")
        return f"{d}/{m}"
    if grain == "ano":
        return bucket
    y, m = bucket.split("-")
    return f"{_MES_PT[int(m) - 1]}/{y[2:]}"


def _split_key_label_cor(row: dict, split: str, refs: dict) -> Optional[tuple[str, str, Optional[str]]]:
    if split == "origem":
        source = refs["sources_by_id"].get(row.get("origem_id"))
        if not source:
            return None
        return source["slug"], source["label"], source.get("cor")
    if split == "corretor":
        corretor = refs["corretores_by_id"].get(row.get("corretor_id"))
        if not corretor:
            return None
        return str(row["corretor_id"]), corretor["nome"], corretor.get("cor")
    if split == "tipo":
        val = row.get("tipo_lead") or "desconhecido"
        return val, _TIPO_LABEL.get(val, val), None
    if split == "tier":
        val = row.get("anuncio_tier")
        if not val:
            return None
        return val, _TIER_LABEL.get(val, val), None
    return None


def timeseries(
    client: Any,
    org_id: UUID,
    filters: LeadFilters,
    refs: dict,
    *,
    grain: str = "mes",
    split: Optional[str] = None,
) -> dict:
    grain = grain if grain in ("dia", "mes", "ano") else "mes"
    rows = fetch_filtered(client, org_id, filters)

    buckets: dict[str, dict[str, Any]] = {}
    series_meta_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = _bucket_for(row, grain)
        if bucket is None:
            continue
        entry = buckets.setdefault(bucket, {"total": 0, "series": {}})
        entry["total"] += 1
        if split:
            sk = _split_key_label_cor(row, split, refs)
            if sk is None:
                continue
            key, label, cor = sk
            entry["series"][key] = entry["series"].get(key, 0) + 1
            series_meta_map.setdefault(key, {"key": key, "label": label, "cor": cor})

    points = []
    for bucket in sorted(buckets):
        entry = buckets[bucket]
        point: dict[str, Any] = {
            "bucket": bucket,
            "label": _label_for(bucket, grain),
            "total": entry["total"],
        }
        if split:
            point["series"] = entry["series"]
        points.append(point)

    series_meta: list[dict[str, Any]] = []
    if split == "tipo":
        series_meta = [series_meta_map[k] for k in _TIPO_ORDER if k in series_meta_map]
    elif split == "tier":
        series_meta = [series_meta_map[k] for k in _TIER_ORDER if k in series_meta_map]
    elif split == "origem":
        ordered_ids = sorted(
            refs["sources_by_id"].values(), key=lambda s: (s.get("ordem") or 0, s.get("label") or "")
        )
        series_meta = [series_meta_map[s["slug"]] for s in ordered_ids if s["slug"] in series_meta_map]
    elif split == "corretor":
        ordered = sorted(refs["corretores_by_id"].values(), key=lambda c: c.get("nome") or "")
        series_meta = [
            series_meta_map[str(c["id"])] for c in ordered if str(c["id"]) in series_meta_map
        ]

    return {"grain": grain, "split": split, "series_meta": series_meta, "points": points}


def by_dimension(
    client: Any,
    org_id: UUID,
    filters: LeadFilters,
    refs: dict,
    *,
    dim: str,
    limit: int = 15,
) -> dict:
    rows = fetch_filtered(client, org_id, filters)
    prev_rows = _previous_window_rows(client, org_id, filters) or []

    def _agg(row_set: list[dict]) -> dict[str, dict[str, int]]:
        acc: dict[str, dict[str, int]] = {}
        for row in row_set:
            sk = _split_key_label_cor(row, dim, refs) if dim in ("origem", "corretor", "tipo", "tier") else None
            if sk is not None:
                key, label, cor = sk
            elif dim in ("empreendimento", "regiao"):
                val = row.get(dim)
                if not val:
                    continue
                key, label, cor = val, val, None
            else:
                continue
            bucket = acc.setdefault(key, {"total": 0, "novos": 0, "retornos": 0, "label": label, "cor": cor})
            bucket["total"] += 1
            if row.get("tipo_lead") == "novo":
                bucket["novos"] += 1
            elif row.get("tipo_lead") == "retorno":
                bucket["retornos"] += 1
        return acc

    current = _agg(rows)
    previous = _agg(prev_rows)
    total_all = sum(b["total"] for b in current.values())

    ordered_keys = sorted(current, key=lambda k: -current[k]["total"])
    top_keys = ordered_keys[:limit]
    rest_keys = ordered_keys[limit:]

    buckets: list[dict[str, Any]] = []
    for key in top_keys:
        b = current[key]
        prev_total = previous.get(key, {}).get("total", 0)
        variacao = _round1((b["total"] - prev_total) / prev_total * 100) if prev_total else None
        buckets.append(
            {
                "key": key,
                "label": b["label"],
                "cor": b["cor"],
                "total": b["total"],
                "share_pct": _round1(b["total"] / total_all * 100) if total_all else 0.0,
                "novos": b["novos"],
                "retornos": b["retornos"],
                "variacao_pct": variacao,
            }
        )

    if rest_keys:
        outros_total = sum(current[k]["total"] for k in rest_keys)
        outros_novos = sum(current[k]["novos"] for k in rest_keys)
        outros_retornos = sum(current[k]["retornos"] for k in rest_keys)
        outros_prev = sum(previous.get(k, {}).get("total", 0) for k in rest_keys)
        variacao = (
            _round1((outros_total - outros_prev) / outros_prev * 100) if outros_prev else None
        )
        buckets.append(
            {
                "key": "outros",
                "label": "Outros",
                "cor": None,
                "total": outros_total,
                "share_pct": _round1(outros_total / total_all * 100) if total_all else 0.0,
                "novos": outros_novos,
                "retornos": outros_retornos,
                "variacao_pct": variacao,
            }
        )

    return {"dim": dim, "total": total_all, "buckets": buckets}


def heatmap(client: Any, org_id: UUID, filters: LeadFilters) -> dict:
    rows = fetch_filtered(client, org_id, filters)
    grid: dict[int, list[Optional[int]]] = {}
    for row in rows:
        ano, mes = row.get("ano"), row.get("mes")
        if ano is None or mes is None:
            continue
        ano, mes = int(ano), int(mes)
        month_row = grid.setdefault(ano, [None] * 12)
        month_row[mes - 1] = (month_row[mes - 1] or 0) + 1

    anos = sorted(grid)
    cells = {str(ano): grid[ano] for ano in anos}
    max_val = 0
    for month_row in grid.values():
        for v in month_row:
            if v is not None and v > max_val:
                max_val = v
    return {"anos": anos, "cells": cells, "max": max_val}


__all__ = ["summary", "timeseries", "by_dimension", "heatmap"]
