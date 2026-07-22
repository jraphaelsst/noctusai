"""Reads one monthly sheet of the CONTROLE LEADS workbook into structured,
org-agnostic parsed rows (no DB access, no alias resolution — that's
``import_service``'s job, since it needs the org's live alias map).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.modules.leads.importer import shape_detector
from app.modules.leads.importer.parsers import (
    looks_like_date_value,
    parse_codigo,
    parse_contato,
    parse_date_cell,
    strip_retorno_prefix,
)

# The 5 non-monthly sheets — explicitly excluded (RESUMO/METRICAS/
# CORRETORES-rollup/FECHAMENTO/RELATORIO are aggregates over the monthly
# sheets, not raw lead rows; two carry a trailing space in their real
# sheet name).
SKIP_SHEETS = frozenset(
    {
        "RESUMO LEADS",
        "METRICAS ",
        "LEADS CORRETORES",
        "FECHAMENTO ",
        "RELATORIO DE VENDAS ",
    }
)

_SAMPLE_SIZE = 100


@dataclass
class ParsedRow:
    source_row: int
    data_entrada: Any  # datetime.date
    codigo_raw: Optional[str]
    codigo_imovel: Optional[str]
    empreendimento: Optional[str]
    regiao: Optional[str]
    origem_raw: Optional[str]
    tipo_lead: str
    cliente_nome: Optional[str]
    contato: Optional[str]
    contato_tipo: str
    contato_norm: Optional[str]
    corretor_raw: Optional[str]
    anuncio_tier: Optional[str]
    observacoes: Optional[str]
    follow_up_data: Optional[Any]
    follow_up_nota: Optional[str]


@dataclass
class SheetParseResult:
    sheet_name: str
    rows: list[ParsedRow]
    rows_read: int
    rows_skipped: int
    warnings: list[str]


_TIER_NORMALIZE = {
    "SIMPLES": "simples",
    "DESTAQUE": "destaque",
    "SUPER DESTAQUE": "super_destaque",
    # Real-data variants observed but not part of the canonical 3-value
    # CHECK constraint — fold "triplo destaque" into the closest existing
    # tier rather than widening the schema for a handful of rows.
    "TRIPLO DESTAQUE": "super_destaque",
    "DESTAQUE TRIPLO": "super_destaque",
}


def _normalize_tier(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _TIER_NORMALIZE.get(raw.strip().upper())


def _extra_columns(row: tuple, start: int) -> tuple[Optional[Any], Optional[Any], list[str]]:
    """Classify everything after the tier/contato slot: a leading
    date-like value + following text -> (follow_up_data, follow_up_nota);
    anything else non-blank -> folded into an ``obs_parts`` catch-all so
    a stray extra value is NEVER silently dropped (e.g. the rare
    second-lead-crammed-into-one-row anomaly seen in ``ABRIL_24``)."""
    follow_up_data = None
    follow_up_nota = None
    obs_parts: list[str] = []
    idx = start
    first = True
    while idx < len(row):
        val = row[idx]
        if val not in (None, "") and str(val).strip():
            if first and looks_like_date_value(val):
                follow_up_data = parse_date_cell(val)
                if idx + 1 < len(row) and row[idx + 1] not in (None, ""):
                    follow_up_nota = str(row[idx + 1]).strip()
                    idx += 1
                first = False
            else:
                obs_parts.append(str(val).strip())
                first = False
        idx += 1
    return follow_up_data, follow_up_nota, obs_parts


def parse_sheet(worksheet: Any, sheet_name: str) -> SheetParseResult:
    warnings: list[str] = []
    candidates: list[tuple[int, tuple]] = []
    rows_read = 0
    rows_skipped = 0

    for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
        if shape_detector.is_blank(row) or shape_detector.is_header_like(row):
            continue
        rows_read += 1
        if not looks_like_date_value(row[0]):
            rows_skipped += 1
            warnings.append(f"{sheet_name}:{row_number} — data ilegível: {row[0]!r}")
            continue
        candidates.append((row_number, row))

    if not candidates:
        return SheetParseResult(sheet_name, [], rows_read, rows_skipped, warnings)

    sample = [row for _, row in candidates[:_SAMPLE_SIZE]]
    shape = shape_detector.detect_shape(sample)

    parsed: list[ParsedRow] = []
    for row_number, row in candidates:
        data_entrada = parse_date_cell(row[0])
        if data_entrada is None:
            # Row passed the structural date-like check but the value
            # didn't parse cleanly (e.g. an invalid dd.mm.yy) — skip +
            # count, per the contract ("unparseable date -> skip and
            # count it").
            rows_skipped += 1
            warnings.append(f"{sheet_name}:{row_number} — data ilegível: {row[0]!r}")
            continue

        codigo_raw = row[1] if len(row) > 1 and row[1] not in (None, "") else None
        codigo_raw = str(codigo_raw).strip() if codigo_raw else None
        codigo_imovel, empreendimento, regiao = parse_codigo(codigo_raw)

        origem_raw = row[shape_detector.ORIGEM_COL] if len(row) > shape_detector.ORIGEM_COL else None
        origem_raw = str(origem_raw).strip() if origem_raw not in (None, "") else None

        tipo_lead = "desconhecido"
        if shape.novo_retorno_idx is not None and len(row) > shape.novo_retorno_idx:
            nr_val = row[shape.novo_retorno_idx]
            if nr_val:
                nr_norm = str(nr_val).strip().upper()
                if nr_norm == "NOVO":
                    tipo_lead = "novo"
                elif nr_norm == "RETORNO":
                    tipo_lead = "retorno"

        cliente_raw = row[shape.cliente_idx] if len(row) > shape.cliente_idx else None
        cliente_raw = str(cliente_raw).strip() if cliente_raw not in (None, "") else None
        cliente_nome, is_retorno_prefix = strip_retorno_prefix(cliente_raw)
        if tipo_lead == "desconhecido" and is_retorno_prefix:
            tipo_lead = "retorno"

        contato_raw = row[shape.contato_idx] if len(row) > shape.contato_idx else None
        contato_raw = str(contato_raw).strip() if contato_raw not in (None, "") else None
        contato_norm, contato_tipo = parse_contato(contato_raw)

        corretor_raw = row[shape.corretor_idx] if len(row) > shape.corretor_idx else None
        corretor_raw = str(corretor_raw).strip() if corretor_raw not in (None, "") else None

        anuncio_tier = None
        extra_start = shape.corretor_idx + 1
        if shape.tier_idx is not None:
            tier_raw = row[shape.tier_idx] if len(row) > shape.tier_idx else None
            anuncio_tier = _normalize_tier(str(tier_raw)) if tier_raw else None
            extra_start = shape.tier_idx + 1

        follow_up_data, follow_up_nota, obs_parts = _extra_columns(row, extra_start)
        observacoes = " | ".join(obs_parts) if obs_parts else None

        parsed.append(
            ParsedRow(
                source_row=row_number,
                data_entrada=data_entrada,
                codigo_raw=codigo_raw,
                codigo_imovel=codigo_imovel,
                empreendimento=empreendimento,
                regiao=regiao,
                origem_raw=origem_raw,
                tipo_lead=tipo_lead,
                cliente_nome=cliente_nome,
                contato=contato_raw,
                contato_tipo=contato_tipo,
                contato_norm=contato_norm,
                corretor_raw=corretor_raw,
                anuncio_tier=anuncio_tier,
                observacoes=observacoes,
                follow_up_data=follow_up_data,
                follow_up_nota=follow_up_nota,
            )
        )

    return SheetParseResult(sheet_name, parsed, rows_read, rows_skipped, warnings)


__all__ = ["SKIP_SHEETS", "ParsedRow", "SheetParseResult", "parse_sheet"]
