"""CSV statement import -- the caller says which columns mean what (`CsvColumnMap`).

Banks and fintechs export wildly different CSVs, so the mapping travels WITH the request
instead of living in per-bank code: a column is a header NAME or a 0-based INDEX; the
amount is one signed column, or a `debit` + `credit` pair.

`fitid` (contract §3.2) = sha256(account, date, amount, description, LINE POSITION): the
position is what keeps two genuinely identical same-day lines (two coffees at the same
price) from collapsing into one on re-import.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import FinanceError
from .ofx import (
    EXTRATO_INVALIDO,
    MAX_DESCRIPTION_CHARS,
    ParsedLine,
    ParsedStatement,
    clean_text,
    derived_fitid,
    parse_amount_cents,
)

DATE_FORMATS = {"dmy": "%d/%m/%Y", "ymd": "%Y-%m-%d", "dmy-dash": "%d-%m-%Y", "dmy2": "%d/%m/%y"}
DELIMITERS = {",": ",", ";": ";", "tab": "\t"}

Column = Union[int, str]


class CsvColumnMap(BaseModel):
    """Strict (`extra="forbid"`): a misspelt key is a 422, never a silently ignored mapping."""

    model_config = ConfigDict(extra="forbid")

    date: Column
    description: Column
    amount: Optional[Column] = None
    debit: Optional[Column] = None
    credit: Optional[Column] = None
    date_format: Literal["dmy", "ymd", "dmy-dash", "dmy2"] = "dmy"
    delimiter: Literal[",", ";", "tab"] = ";"
    has_header: bool = True
    #: how numbers are written: `1.234,56` (comma) or `1234.56` (dot)
    decimal: Literal["comma", "dot"] = "comma"
    #: preamble lines to drop before the header (some banks print the account above the table)
    skip_rows: int = Field(0, ge=0, le=100)

    @model_validator(mode="after")
    def _amount_shape(self) -> "CsvColumnMap":
        has_pair = self.debit is not None and self.credit is not None
        if self.amount is None and not has_pair:
            raise ValueError("informe a coluna `amount` ou as colunas `debit` e `credit`")
        if self.amount is not None and (self.debit is not None or self.credit is not None):
            raise ValueError("use `amount` OU `debit`/`credit`, não os dois")
        for name in ("date", "description", "amount", "debit", "credit"):
            value = getattr(self, name)
            if isinstance(value, int) and value < 0:
                raise ValueError(f"`{name}`: o índice da coluna não pode ser negativo")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"`{name}`: nome de coluna vazio")
        return self


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _cell(row: list[str], key: Column, header: Optional[dict[str, int]]) -> str:
    if isinstance(key, int):
        idx = key
    else:
        if header is None or key.strip().lower() not in header:
            raise FinanceError(EXTRATO_INVALIDO, f"Coluna '{key}' não encontrada no cabeçalho do CSV.", 422)
        idx = header[key.strip().lower()]
    return row[idx].strip() if idx < len(row) else ""


def _number(raw: str, decimal: str) -> int:
    text = raw.strip().replace(" ", "").replace("R$", "")
    if decimal == "comma":
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    return parse_amount_cents(text)


def parse_csv(data: bytes, column_map: CsvColumnMap, *, account_id: str) -> ParsedStatement:
    rows_iter = csv.reader(io.StringIO(_decode(data), newline=""), delimiter=DELIMITERS[column_map.delimiter])
    fmt = DATE_FORMATS[column_map.date_format]
    header: Optional[dict[str, int]] = None
    lines: list[ParsedLine] = []
    skipped = 0
    try:
        rows = list(rows_iter)
    except csv.Error:
        raise FinanceError(EXTRATO_INVALIDO, "O CSV está malformado.", 422) from None
    rows = rows[column_map.skip_rows:]
    if column_map.has_header:
        if not rows:
            raise FinanceError(EXTRATO_INVALIDO, "O CSV está vazio.", 422)
        header = {c.strip().lower(): i for i, c in reversed(list(enumerate(rows[0])))}
        rows = rows[1:]
    for position, row in enumerate(rows, start=1):
        if not any(c.strip() for c in row):
            continue  # blank line: not a statement line, but it still occupied a position
        raw_date = _cell(row, column_map.date, header)
        try:
            posted: date = datetime.strptime(raw_date, fmt).date()
        except ValueError:
            raise FinanceError(EXTRATO_INVALIDO, f"Data inválida na linha {position} do CSV.", 422) from None
        if column_map.amount is not None:
            amount = _number(_cell(row, column_map.amount, header), column_map.decimal)
        else:
            debit = _cell(row, column_map.debit, header)  # type: ignore[arg-type]
            credit = _cell(row, column_map.credit, header)  # type: ignore[arg-type]
            amount = (_number(credit, column_map.decimal) if credit else 0) - (
                abs(_number(debit, column_map.decimal)) if debit else 0
            )
        if amount == 0:
            skipped += 1
            continue
        description = clean_text(_cell(row, column_map.description, header)) or "Lançamento"
        lines.append(
            ParsedLine(
                posted_on=posted,
                amount_cents=amount,
                description=description[:MAX_DESCRIPTION_CHARS],
                fitid=derived_fitid(account_id, posted.isoformat(), amount, description, position),
            )
        )
    if not lines and not skipped:
        raise FinanceError(EXTRATO_INVALIDO, "Nenhum lançamento encontrado no CSV.", 422)
    period_start = min((l.posted_on for l in lines), default=None)
    period_end = max((l.posted_on for l in lines), default=None)
    return ParsedStatement(lines=lines, period_start=period_start, period_end=period_end, skipped_zero=skipped)


__all__ = ["CsvColumnMap", "DATE_FORMATS", "parse_csv"]
