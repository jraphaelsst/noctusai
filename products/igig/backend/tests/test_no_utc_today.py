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
TESTS = Path(__file__).resolve().parent


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
        elif (  # naive `datetime.now()` — the container's local (UTC) wall clock
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "now"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
            and not node.args
            and not node.keywords
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


def test_tests_never_derive_a_business_date_from_the_utc_clock():
    """A test that builds 'today' in UTC disagrees with the service from 21:00
    BRT — CI went red every evening (a7ee824ec, 2026-09-28 automação prazo).
    Aware instants (`datetime.now(timezone.utc)`) are fine; calendar dates
    come from `quadro_comum.hoje_local()`."""
    achados = {
        str(p.relative_to(TESTS)): linhas
        for p in sorted(TESTS.rglob("*.py"))
        if p.name != Path(__file__).name
        and (linhas := _utc_today_calls(p.read_text(encoding="utf-8")))
    }
    assert achados == {}, f"use hoje_local() for business dates: {achados}"


def test_the_detector_catches_a_naive_now_but_not_an_aware_one():
    assert _utc_today_calls("from datetime import datetime\nx = datetime.now()\n") == [2]
    assert _utc_today_calls("x = datetime.now(timezone.utc)\n") == []
