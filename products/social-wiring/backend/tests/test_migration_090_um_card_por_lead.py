"""Structural tests for ``migrations/090_um_card_por_lead.sql``.

Parse-based, like `test_migration_041.py` — the trigger body is SQL and there
is no dev database, so these assert the DECLARED behaviour: that each side
looks for the other's card before inserting, and that the insert path still
carries both origin ids.

What they protect is the shape of the fix, not the SQL engine: a campaign
lead used to spawn TWO cards (migration 034 put the trigger on both `leads`
and `meta_ads_leads`, and `ingest_meta_lead` writes both rows) and a later
sweep merged them — 695 cards created only to be undone, each window showing
the same person twice on the board.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "090_um_card_por_lead.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"Migration file missing at {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_replaces_the_spawn_function_not_the_triggers(sql: str) -> None:
    """Both triggers keep firing — they simply cooperate now. Dropping one
    would leave the other as a single point of failure for card creation."""
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+social_wiring\.spawn_funil_card\s*\(",
        sql, re.IGNORECASE,
    ), "must CREATE OR REPLACE the shared spawn function"
    assert not re.search(r"DROP\s+TRIGGER", sql, re.IGNORECASE), (
        "neither spawn trigger may be dropped — both sides must still fire"
    )


def test_the_leads_side_looks_for_the_campaign_card_first(sql: str) -> None:
    """`leads` firing with a `meta_lead_id` must find a card already created
    by the campaign half and ATTACH to it instead of making a second."""
    assert re.search(r"meta_ads_lead_id\s*=\s*v_meta_lead_id", sql, re.IGNORECASE), (
        "the leads side must look up the existing card by meta_ads_lead_id"
    )
    assert re.search(
        r"UPDATE\s+social_wiring\.atendimentos\s+SET\s+lead_id\s*=\s*NEW\.id",
        sql, re.IGNORECASE,
    ), "the leads side must attach its id to the existing card"


def test_the_campaign_side_looks_for_the_lead_card_first(sql: str) -> None:
    """The reverse direction. The backfill route replays meta rows whose
    `leads` row already exists, so ordering is not a guarantee."""
    assert re.search(r"l\.meta_lead_id\s*=\s*NEW\.id::text", sql, re.IGNORECASE), (
        "the campaign side must join through leads.meta_lead_id"
    )
    assert re.search(
        r"UPDATE\s+social_wiring\.atendimentos\s+SET\s+meta_ads_lead_id\s*=\s*NEW\.id",
        sql, re.IGNORECASE,
    ), "the campaign side must attach its id to the existing card"


def test_both_attach_paths_return_without_inserting(sql: str) -> None:
    """The whole point: an attach must RETURN, never fall through to the
    INSERT. Falling through is the duplicate this migration removes."""
    # Two `RETURN NEW;` before the insert block, one per attach branch.
    antes_do_insert = sql.split("No card yet")[0]
    assert antes_do_insert.upper().count("RETURN NEW;") == 2, (
        "each attach branch must return before reaching the INSERT"
    )


def test_the_created_card_carries_both_origins_when_known(sql: str) -> None:
    """One card embedding both `lead` and `campanha` makes the union REAL
    instead of computed at read time by `attach_colapsadas`."""
    assert re.search(
        r"INSERT\s+INTO\s+social_wiring\.atendimentos\s*\(\s*org_id\s*,\s*lead_id\s*,"
        r"\s*meta_ads_lead_id\s*,",
        sql, re.IGNORECASE,
    ), "the leads-side insert must carry meta_ads_lead_id too"


def test_new_cards_still_land_on_top(sql: str) -> None:
    """Migration 087's rule must survive this rewrite: a fresh arrival takes
    a position above everything so the intake column reads newest-first."""
    assert re.search(
        r"COALESCE\s*\(\s*MIN\s*\(\s*kanban_pos\s*\)\s*,\s*1\s*\)\s*-\s*1",
        sql, re.IGNORECASE,
    ), "new cards must still take min(kanban_pos) - 1"


def test_does_not_rewrite_history(sql: str) -> None:
    """The 695 already-collapsed pairs keep their `substituida_por` linkage;
    the collapse stays as the backstop. A migration that also 'tidied' them
    would be undoing a correct historical record."""
    # The WORD appears in this migration's own header, explaining that the
    # collapse stays. What must not exist is a STATEMENT writing the column.
    codigo = "\n".join(
        linha for linha in sql.splitlines() if not linha.lstrip().startswith("--")
    )
    assert not re.search(
        r"(UPDATE|DELETE|SET)[^;]*substituida_por", codigo, re.IGNORECASE | re.DOTALL
    ), "migration 090 must not rewrite the historical collapse linkage"
