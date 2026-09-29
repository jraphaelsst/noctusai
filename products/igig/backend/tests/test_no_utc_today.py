"""No `date.today()` in igig app code — the ONE business clock is São Paulo.

The container runs in UTC, so `date.today()` is a day AHEAD of the agency
from 21:00 BRT to midnight: validity checks refused valid orçamentos,
automation due dates and report "hoje" slipped a day, and the dev CI went
red every evening (a7ee824ec). Every business date goes through
`app.services.quadro_comum.hoje_local()`.

AST, not grep: a comment or docstring naming the anti-pattern is fine; a
call is not.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _utc_today_calls(source: str) -> list[int]:
    linhas = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "today"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "date"
        ):
            linhas.append(node.lineno)
    return linhas


def test_app_code_never_calls_date_today():
    achados = {
        str(p.relative_to(APP)): linhas
        for p in sorted(APP.rglob("*.py"))
        if (linhas := _utc_today_calls(p.read_text(encoding="utf-8")))
    }
    assert achados == {}, (
        "date.today() is the container's UTC date — use "
        f"app.services.quadro_comum.hoje_local(): {achados}"
    )


def test_the_detector_catches_a_call():
    assert _utc_today_calls("from datetime import date\nx = date.today()\n") == [2]
    assert _utc_today_calls('"""date.today() in prose"""\n') == []
