"""Structural tests for `064_registry_sweep_guard.sql`.

Born from a real incident (2026-08-21): a hand-run sweep delisted 484 live
imóveis and stamped snapshots over them, then reported success. The call
passed `max(sincronizado_em)` as `p_run_at`, which excluded 443 rows the
same run had written 83 ms earlier.

Three things are pinned here, and the third is the one that would have
taken production down tonight:

  1. The circuit breaker exists and runs BEFORE any write.
  2. Reactivation clears the snapshot — a row may not be simultaneously
     active and carrying a last-known-state.
  3. The 2-argument signature is DROPPED. `CREATE OR REPLACE` matches the
     full argument list, so adding defaulted parameters creates a SECOND
     function; the app's 2-arg RPC would then hit
     `ERROR 42725: function ... is not unique`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "064_registry_sweep_guard.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


class TestOverloadIsDropped:
    def test_two_arg_signature_is_dropped_first(self, code: str):
        drop = code.index(
            "DROP FUNCTION IF EXISTS social_wiring.sweep_imovel_registry(UUID, TIMESTAMPTZ)"
        )
        create = code.index("CREATE OR REPLACE FUNCTION social_wiring.sweep_imovel_registry")
        assert drop < create, "DROP must precede CREATE or both overloads survive"


class TestCircuitBreaker:
    def test_guard_raises_rather_than_silently_skipping(self, code: str):
        """A silent no-op would be indistinguishable from a clean run."""
        assert "RAISE EXCEPTION" in code

    def test_guard_uses_both_a_percentage_and_an_absolute_floor(self, code: str):
        """Percentage alone blocks a legitimate 3-imóvel org; absolute alone
        waves through 443/1943."""
        assert "v_a_delistar > p_min_delist_abs AND v_pct > p_max_delist_pct" in code

    def test_guard_runs_before_any_update(self, code: str):
        guard = code.index("RAISE EXCEPTION")
        first_update = code.index("UPDATE social_wiring.imovel_registry")
        assert guard < first_update, "breaker must fire before the first write"

    def test_raise_message_avoids_the_ambiguous_percent_literal(self, code: str):
        """`%%%` lexes as literal-% then placeholder, putting the sign on the
        wrong side of the number. `%.1f` is not PL/pgSQL at all."""
        assert "%.1f" not in code
        assert "%%%" not in code

    def test_percentages_are_rounded_before_interpolation(self, code: str):
        assert "round(v_pct, 1)" in code

    def test_defaults_are_declared(self, code: str):
        assert "p_max_delist_pct NUMERIC DEFAULT 20.0" in code
        assert "p_min_delist_abs INTEGER DEFAULT 50" in code


class TestSnapshotInvariant:
    def test_reactivation_clears_every_snapshot_column(self, code: str):
        """Snapshot present IFF delisted. 063 left them set on reactivation."""
        reactivate = code.index("SET ativo_no_vista = TRUE")
        delist = code.index("SET ativo_no_vista = FALSE")
        block = code[reactivate:delist]
        for col in (
            "snap_titulo", "snap_categoria", "snap_status", "snap_bairro",
            "snap_cidade", "snap_uf", "snap_valor_venda", "snap_valor_locacao",
            "snap_dormitorios", "snap_area_total", "snap_foto_destaque", "snap_em",
        ):
            assert f"{col} = NULL" in block, f"{col} not cleared on reactivation"

    def test_delist_still_writes_the_snapshot(self, code: str):
        delist = code.index("SET ativo_no_vista = FALSE")
        block = code[delist:]
        assert "snap_titulo        = i.titulo" in block
        assert "snap_em            = p_run_at" in block

    def test_repair_statement_only_touches_active_rows(self, code: str):
        """The incident repair must not wipe a legitimately delisted row's
        snapshot."""
        assert "WHERE ativo_no_vista AND snap_em IS NOT NULL" in code
