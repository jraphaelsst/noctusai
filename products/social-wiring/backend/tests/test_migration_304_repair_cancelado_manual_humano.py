"""Structural pins for migration 304 (repair of human cells cancelled to erro)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.modules.certidoes.service import MSG_CANCELADO

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "repair_cancelado_manual_humano")
CODE = "\n".join(l for l in SQL.splitlines() if not l.strip().startswith("--"))


def test_scoped_where_matches_exactly_the_cancelled_manual_rows():
    assert f"r.erro_mensagem = '{MSG_CANCELADO}'" in CODE
    assert "r.status = 'erro'" in CODE and "c.origem = 'manual'" in CODE
    assert "c.excluida_em IS NULL" in CODE and "r.excluida_em IS NULL" in CODE
    assert "r.arquivo_url IS NOT NULL" in CODE and "r.confirmado_por IS NOT NULL" in CODE


def test_restores_pre_cancel_state_and_touches_nothing_else():
    assert "SET status = 'pendente'" in CODE and "erro_mensagem = NULL" in CODE
    assert "certidao_consultas SET" not in CODE
    assert CODE.count("UPDATE ") == 1
    for forbidden in ("DELETE", "DROP ", "ALTER ", "INSERT "):
        assert forbidden not in CODE


def test_idempotent_by_construction():
    # The WHERE requires status='erro' + the cancel text; the SET removes both.
    assert "r.status = 'erro'" in CODE and "SET status = 'pendente'" in CODE
