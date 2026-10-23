"""Printed pt-BR dates — the ONE reader every document parser shares.

Pure, deterministic, import-light. Works on text already passed through
`matricula.normalize` (upper-case, accent-stripped, whitespace-collapsed), so
"março" is `MARCO` and "1º" is `1O`.

Two printed shapes, nothing else:

- numeric: `11/08/2026`, `11.08.2026`, `11-08-2026` (day first); the year
  may carry a thousands dot (`12/02/1.988`, old typed matrículas);
- por extenso: `11 DE AGOSTO DE 2026`, `1O DE MARCO DE 2026`.

A shape that names an impossible day (`31/02/2026`) is skipped, never
"repaired" — a date either is printed validly or it is not read.

🔴 WHY THIS EXISTS (recurrence rule, 2026-10): the month table and these two
patterns were hand-copied into `matricula_certidao`, `matricula_ato_detalhes`
and `serasa_crednet`; the CND reader (`cnd_imovel`) would have been the
fourth copy.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

MESES: dict[str, int] = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

#: Alternation of the month names, for callers composing a larger pattern
#: (e.g. a date followed by a time).
MES = "(?:" + "|".join(MESES) + ")"

#: Day, month, year as groups 1-3.
DATA_NUMERICA = re.compile(
    r"(?<![\d/.])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d\.\d{3}|\d{4})(?![\d/])"
)
#: Day, month NAME, year as groups 1-3.
DATA_EXTENSO = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:O|°)?\s+DE\s+(" + "|".join(MESES) + r")\s+DE\s+(\d\.\d{3}|\d{4})(?!\d)"
)


def _ano(bruto: str) -> int:
    """`1988` or the OCR/typed thousands-dotted `1.988` (older matrículas)."""
    return int(bruto.replace(".", ""))


def data_valida(ano: int, mes: int, dia: int) -> Optional[date]:
    """`date(ano, mes, dia)`, or `None` when the calendar has no such day."""
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def datas_no_texto(
    norm: str, desde: int = 0, ate: Optional[int] = None
) -> list[tuple[int, int, date]]:
    """Every valid printed date in `norm[desde:ate]`, both shapes, as
    `(start, end, date)` sorted by position."""
    ate = len(norm) if ate is None else ate
    saida: list[tuple[int, int, date]] = []
    for m in DATA_NUMERICA.finditer(norm, desde, ate):
        valor = data_valida(_ano(m.group(3)), int(m.group(2)), int(m.group(1)))
        if valor is not None:
            saida.append((m.start(), m.end(), valor))
    for m in DATA_EXTENSO.finditer(norm, desde, ate):
        valor = data_valida(_ano(m.group(3)), MESES[m.group(2)], int(m.group(1)))
        if valor is not None:
            saida.append((m.start(), m.end(), valor))
    saida.sort()
    return saida
