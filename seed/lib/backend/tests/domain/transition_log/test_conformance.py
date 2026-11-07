"""Fake and Real run the SAME conformance suite (`conformance.py`); the Real on a live PGlite with the rendered SQL."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.transition_log import (
    FakeTransitionLog,
    SupabaseTransitionLog,
    make_transition_log,
    normalize_key,
    transition_log_migration,
)

from noctusai_lib.testing.pglite import PgliteClient, pglite_available
from .conformance import CASES, CONFIGS, SCHEMA, STATE_COLUMNS, STATE_DDL, STATE_DEFAULTS, Harness


@pytest.fixture(scope="module")
def pglite():
    if not pglite_available():
        pytest.skip("PGlite unavailable (needs `node` and mcp/noctusai/node/node_modules) -- the Real leg did not run")
    client = PgliteClient(SCHEMA)
    client.exec(STATE_DDL)
    for i, cfg in enumerate(CONFIGS.values()):
        client.exec(transition_log_migration(cfg, header=i == 0))
    yield client
    client.close()


def _fake(name: str) -> Harness:
    cfg = CONFIGS[name]
    log = make_transition_log("fake", cfg=cfg, state_columns=STATE_COLUMNS[name], state_defaults=STATE_DEFAULTS[name])
    assert isinstance(log, FakeTransitionLog)

    def state_of(org, key):
        row = log.state_row(org, key)
        return row[cfg.state_column] if row else None

    return Harness(name, cfg, log, lambda org, row: log.put_state_row(org, row), state_of)


def _real(name: str, client) -> Harness:
    cfg = CONFIGS[name]
    log = make_transition_log("supabase", cfg=cfg, client=client)
    assert isinstance(log, SupabaseTransitionLog)

    def lit(v):
        return "'" + str(v).replace("'", "''") + "'"

    def insert_state(org, row):
        full = {**row, cfg.state_org_column: org}
        cols = ", ".join(full)
        client.exec(f"INSERT INTO {SCHEMA}.{cfg.state_table} ({cols}) VALUES ({', '.join(lit(v) for v in full.values())})")

    def state_of(org, key):
        k = normalize_key(cfg, key)
        where = " AND ".join(f"{kc.state_column} = {lit(k[kc.name])}" for kc in cfg.key)
        rows = client.query(f"SELECT {cfg.state_column} AS s FROM {SCHEMA}.{cfg.state_table} WHERE {where} AND org_id = {lit(org)}")
        return rows[0]["s"] if rows else None

    return Harness(name, cfg, log, insert_state, state_of)


@pytest.mark.parametrize("config", sorted(CONFIGS))
@pytest.mark.parametrize("case", sorted(CASES))
def test_fake(case, config):
    CASES[case](_fake(config))


@pytest.mark.parametrize("config", sorted(CONFIGS))
@pytest.mark.parametrize("case", sorted(CASES))
def test_real_on_postgres(case, config, pglite):
    CASES[case](_real(config, pglite))
