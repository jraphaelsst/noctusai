"""A 409 a person reads is pt-BR text per ``code`` — never the DB text (constraint/index names) nor internal prose.

Regression: the Studio "Rodar suíte de mecanismo" button rendered
``duplicate key value violates unique constraint "uq_eval_mecanismo_runs_um_em_execucao"`` because the 23505 mapping
carried the Postgres message and the routers rendered ``str(exc)``.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.stores._db_errors import (
    MENSAGEM_CONFLITO_GENERICA,
    MENSAGENS_CONFLITO,
    StudioConflict,
    erro_de_item,
    map_db_error,
    mensagem_conflito,
)

_APP = Path(__file__).resolve().parents[2] / "app"
_DB_TEXT = 'duplicate key value violates unique constraint "uq_eval_mecanismo_runs_um_em_execucao"'


class _APIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def test_a_unique_violation_maps_to_the_code_without_the_db_text():
    exc = map_db_error(_APIError("23505", _DB_TEXT), unique_code="run_in_progress")
    assert isinstance(exc, StudioConflict) and exc.code == "run_in_progress"
    assert "uq_" not in str(exc) and "duplicate" not in str(exc)


def test_a_fk_violation_maps_to_the_code_without_the_db_text():
    exc = map_db_error(_APIError("23503", 'violates foreign key constraint "fk_x"'), fk_code="case_in_use")
    assert isinstance(exc, StudioConflict) and exc.code == "case_in_use" and "fk_x" not in str(exc)


def test_the_person_reads_the_catalog_text_never_the_exception_message():
    exc = StudioConflict("run_in_progress", "a mechanism run is already executing for this version")
    assert mensagem_conflito(exc) == MENSAGENS_CONFLITO["run_in_progress"]
    assert mensagem_conflito(StudioConflict("codigo_sem_texto", _DB_TEXT)) == MENSAGEM_CONFLITO_GENERICA


def test_a_batch_item_error_uses_the_catalog_for_conflicts_and_keeps_value_errors():
    assert erro_de_item(StudioConflict("skill_exists", "skill 'x' already exists")) == MENSAGENS_CONFLITO["skill_exists"]
    assert erro_de_item(ValueError("conteudo excede 200 KB")) == "conteudo excede 200 KB"


def _conflict_codes_in_app() -> set[str]:
    codes: set[str] = set()
    for path in _APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in ("StudioConflict", "_conflict") and node.args and isinstance(node.args[0], ast.Constant):
                codes.add(node.args[0].value)
            for kw in node.keywords:
                if kw.arg in ("unique_code", "fk_code") and isinstance(kw.value, ast.Constant):
                    codes.add(kw.value.value)
    return codes


def test_every_conflict_code_raised_in_the_app_has_pt_br_text():
    """A new 409 code ships WITH its text — else the person reads the generic fallback."""
    faltando = sorted(c for c in _conflict_codes_in_app() if isinstance(c, str) and c not in MENSAGENS_CONFLITO)
    assert faltando == []


def test_no_router_renders_a_conflict_as_str_exc():
    """Routers render ``mensagem_conflito(exc)`` / ``erro_de_item(exc)``; ``str(exc)`` of a conflict is internal."""
    ofensores = []
    for path in (_APP / "routers").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for linha, texto in enumerate(src.splitlines(), 1):
            if "exc.code, str(exc)" in texto:
                ofensores.append(f"{path.name}:{linha}")
    assert ofensores == []
