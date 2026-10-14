"""Structural tests for migration 263 (`atendimentos.motivo_perda_categoria`).

The closed set here MUST equal `MotivoPerdaCategoria` in the pipeline router —
the API and the CHECK are two halves of one contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from noctusai_lib.testing.migrations import migration_path

from app.modules.pipeline.routers.boards import MotivoPerdaCategoria

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "atendimento_motivo_perda_categoria")


@pytest.fixture(scope="module")
def code() -> str:
    return "\n".join(
        ln for ln in MIGRATION.read_text().splitlines() if not ln.strip().startswith("--")
    )


def test_column_added_idempotently(code: str):
    assert "ADD COLUMN IF NOT EXISTS motivo_perda_categoria TEXT" in code
    # independent of 262's release order
    assert "ADD COLUMN IF NOT EXISTS motivo_perda TEXT" in code


def test_check_set_matches_the_api_literal(code: str):
    m = re.search(r"motivo_perda_categoria IN \((.*?)\)\)", code, re.S)
    assert m, "CHECK constraint not found"
    in_db = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert in_db == set(get_args(MotivoPerdaCategoria))


def test_check_is_guarded_for_reruns(code: str):
    assert "atendimentos_motivo_perda_categoria_check" in code
    assert "IF NOT EXISTS" in code
