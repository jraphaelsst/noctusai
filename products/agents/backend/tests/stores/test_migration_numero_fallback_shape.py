"""074: the hand-off fallback number is a platform runtime setting -- the key is accepted and its value must be E.164."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.primitives.phone import normalize_phone
from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[2] / "migrations", "numero_fallback_atendimento")


def test_the_key_is_accepted_by_the_closed_key_check():
    check = re.search(r"CHECK \(key IN \(([^)]*)\)\)", SQL)
    assert check and "'numero_fallback_atendimento'" in check.group(1)


def test_no_number_is_seeded_the_owner_types_it():
    assert "INSERT INTO" not in SQL.upper()


@pytest.mark.parametrize("bruto", ["(11) 99457-3387", "+5511994573387", "1132165498"])
def test_every_number_the_app_stores_passes_the_db_backstop(bruto):
    padrao = re.search(r"~ '([^']+)'", SQL).group(1)
    assert re.fullmatch(padrao, normalize_phone(bruto))
