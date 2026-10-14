"""Structural tests for the `imovel_preco_historico` migration.

Behavioural coverage (a price change inserts exactly one row, an unchanged
price none, cross-org isolation) is the PGlite replay + the verify_db_guards
probes; these pin the contract the replay cannot read: which events fire the
trigger, the key, and the security posture.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "imovel_preco_historico")


@pytest.fixture(scope="module")
def code() -> str:
    return "\n".join(
        ln for ln in MIGRATION.read_text().splitlines() if not ln.strip().startswith("--")
    )


class TestTriggerFiresOnlyOnRealPriceChange:
    @pytest.mark.parametrize("table", ["imoveis", "imovel_captacao"])
    def test_update_trigger_is_column_scoped_and_guarded(self, code: str, table: str):
        m = re.search(
            rf"AFTER UPDATE OF valor_venda, valor_locacao ON social_wiring\.{table}\s+"
            r"FOR EACH ROW\s+WHEN \((.*?)\)\s+EXECUTE",
            code,
            re.S,
        )
        assert m, f"{table}: UPDATE trigger must be column-scoped with a WHEN clause"
        when = m.group(1)
        assert "OLD.valor_venda   IS DISTINCT FROM NEW.valor_venda" in when
        assert "OLD.valor_locacao IS DISTINCT FROM NEW.valor_locacao" in when

    @pytest.mark.parametrize("table", ["imoveis", "imovel_captacao"])
    def test_first_seen_recorded_on_insert(self, code: str, table: str):
        assert re.search(rf"AFTER INSERT ON social_wiring\.{table}", code)

    def test_insert_with_no_price_writes_nothing(self, code: str):
        assert code.count("NEW.valor_venda IS NULL AND NEW.valor_locacao IS NULL") == 2


class TestKeyAndSources:
    def test_keyed_on_the_registry_join_column(self, code: str):
        assert "NEW.codigo_norm" in code  # mirror: generated canonical column
        assert "NEW.codigo_canonical" in code  # manual captação
        assert "NEW.codigo," not in code, "raw (case-unstable) codigo must not be the key"

    def test_fontes(self, code: str):
        for fonte in ("'vista_sync'", "'manual'", "'baseline'"):
            assert fonte in code


class TestSecurity:
    def test_rls_enabled_with_org_scoped_select_and_no_authenticated_write(self, code: str):
        assert "imovel_preco_historico ENABLE ROW LEVEL SECURITY" in code
        assert "FOR SELECT TO authenticated" in code
        assert "current_org_id_for('social_wiring')" in code
        assert not re.search(r"FOR (INSERT|UPDATE|DELETE|ALL) TO authenticated", code)

    @pytest.mark.parametrize("fn", ["registrar_preco_historico_imoveis", "registrar_preco_historico_captacao"])
    def test_security_definer_revokes_execute(self, code: str, fn: str):
        assert re.search(rf"FUNCTION social_wiring\.{fn}\(\)\s+RETURNS TRIGGER\s+LANGUAGE plpgsql\s+SECURITY DEFINER\s+SET search_path", code)
        assert re.search(
            rf"REVOKE EXECUTE ON FUNCTION social_wiring\.{fn}\(\) FROM PUBLIC, anon, authenticated", code
        )


class TestBackfillAndMotivo:
    def test_baseline_backfill_is_idempotent(self, code: str):
        assert code.count("'baseline'") == 2
        assert code.count("AND NOT EXISTS (") == 2

    def test_motivo_perda_column(self, code: str):
        assert "ADD COLUMN IF NOT EXISTS motivo_perda TEXT" in code
