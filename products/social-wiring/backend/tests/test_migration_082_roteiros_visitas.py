"""Structural tests for `082_roteiros_visitas.sql`.

The migration is a FILE, not an applied change — it needs tech-lead consent to
run against any database. So these assert its *structure* by parsing it, which
is the only honest verification available before it is applied. Same convention
as `test_migration_040_imoveis.py` and `test_migration_062_codigo_canonical.py`.

🔴 THE LOAD-BEARING CLASS IS `TestFKTargetsTheRegistry`.

The user asked for foreign keys so that per-imóvel statistics and a cliente
history readable in 2028 both survive. Pointing those keys at
`social_wiring.imoveis` would have defeated the requirement rather than served
it: the mirror only holds ACTIVE Vista listings, an imóvel leaves it when it is
SOLD, and 35% of registered imóveis (1062 of 3017, prod 2026-08-25) are already
gone from it. A FK there rejects a third of the catalog at INSERT and then
deletes our visit history on delist.

Migration 063 ruled it once ("everything of ours joins HERE, never to the
mirror") and 076 had to re-rule it after 075 got it wrong. This class is that
ruling made executable, so the next person cannot get it wrong a third time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "082_roteiros_visitas.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped, so prose never satisfies a check."""
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


class TestFKTargetsTheRegistry:
    def test_visitas_fk_points_at_imovel_registry(self, code: str):
        """🔴 The whole decision, in one assertion."""
        assert re.search(
            r"FOREIGN\s+KEY\s*\(\s*org_id\s*,\s*codigo\s*\)\s*"
            r"REFERENCES\s+social_wiring\.imovel_registry\s*\(\s*org_id\s*,\s*"
            r"codigo_canonical\s*\)",
            code,
            re.I | re.S,
        ), "visitas must FK to imovel_registry (org_id, codigo_canonical)"

    def test_nothing_in_this_migration_references_the_imoveis_mirror(self, code: str):
        """A FK to the mirror rejects 35% of the catalog and deletes history on
        delist. If this ever fails, read migration 076's header before
        'fixing' the test."""
        assert not re.search(
            r"REFERENCES\s+social_wiring\.imoveis\b", code, re.I
        ), "no table here may reference the disposable Vista mirror"

    def test_the_registry_fk_cascades(self, code: str):
        """Copied from `imovel_dados_registry_fk` (076). The registry is
        append-only, so this is a statement about referential integrity rather
        than a live deletion path."""
        bloco = code[code.index("visitas_registry_fk"):]
        assert re.search(r"ON\s+DELETE\s+CASCADE", bloco[:400], re.I)


class TestRoteiros:
    def test_belongs_to_an_atendimento_not_a_cliente(self, code: str):
        """Migration 061's ruling: a route walked for a 2024 purchase must not
        pile onto a live negotiation's list."""
        assert re.search(
            r"atendimento_id\s+UUID\s+NOT\s+NULL\s*"
            r"REFERENCES\s+social_wiring\.atendimentos\(id\)\s*ON\s+DELETE\s+CASCADE",
            code,
            re.I | re.S,
        )
        bloco = _table_block(code, "roteiros")
        assert "cliente_id" not in bloco, (
            "a roteiro hangs off the atendimento; a cliente_id here would give "
            "the card two ownership models for two adjacent tabs"
        )

    def test_is_soft_deleted(self, code: str):
        assert re.search(r"deleted_at\s+TIMESTAMPTZ", _table_block(code, "roteiros"), re.I)

    def test_carries_no_status_column(self, code: str):
        """A roteiro's state is DERIVABLE from its visitas. A second,
        hand-maintained copy is how the two drift — 061's precedent."""
        assert not re.search(r"^\s*status\s+TEXT", _table_block(code, "roteiros"), re.I | re.M)


class TestVisitas:
    def test_status_has_three_values(self, code: str):
        """🔴 Not a boolean. "Hasn't happened yet" and "didn't happen" are
        different facts, and merging them files every future visit under
        "did not" in the count this feature exists to produce."""
        m = re.search(r"visitas_status_valido\s*\n?\s*CHECK\s*\((.*?)\)\s*,", code, re.S | re.I)
        assert m, "visitas.status must carry a CHECK"
        for valor in ("pendente", "realizada", "nao_realizada"):
            assert valor in m.group(1)

    def test_ordem_is_not_unique(self, code: str):
        """A UNIQUE would force a DEFERRABLE constraint or a two-phase rewrite
        on every single drag — same reasoning as `checklists.posicao`."""
        bloco = _table_block(code, "visitas")
        assert not re.search(r"UNIQUE\s*\([^)]*ordem", bloco, re.I)

    def test_has_feedback_em_for_the_timeline(self, code: str):
        assert re.search(r"feedback_em\s+TIMESTAMPTZ", _table_block(code, "visitas"), re.I)

    def test_carries_no_proprietario_column(self, code: str):
        """D1, user-ratified 2026-08-25. Vista exposes no owner data, so a
        column nothing can write would be a placeholder side. The destination
        when a source exists is `imovel_dados` (075), not this table."""
        assert "proprietario" not in _table_block(code, "visitas").lower()


class TestRLS:
    @pytest.mark.parametrize("tabela", ["roteiros", "visitas"])
    def test_rls_enabled_and_org_scoped(self, code: str, tabela: str):
        assert re.search(
            rf"ALTER\s+TABLE\s+social_wiring\.{tabela}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            code,
            re.I,
        )
        assert re.search(
            rf'CREATE\s+POLICY\s+"{tabela}_select_own_org".*?'
            r"USING\s*\(\s*org_id\s*=\s*public\.current_org_id\(\)\s*\)",
            code,
            re.I | re.S,
        )

    def test_never_reads_the_jwt_directly(self, code: str):
        """`auth.jwt()` top-level and `user_metadata` are respectively
        always-null and user-editable — the house rule both RLS halves follow."""
        assert "auth.jwt()" not in code
        assert "user_metadata" not in code


class TestEstatisticas:
    def test_view_exists_with_security_invoker(self, code: str):
        """`security_invoker = true` — the house default (071, 080). A
        definer-rights view over an RLS'd table is a quiet way to read another
        org's counts."""
        assert re.search(
            r"CREATE\s+OR\s+REPLACE\s+VIEW\s+social_wiring\.vw_imovel_visita_contagem"
            r"\s*\n?\s*WITH\s*\(\s*security_invoker\s*=\s*true\s*\)",
            code,
            re.I,
        )

    def test_counts_the_three_buckets(self, code: str):
        vista = code[code.index("vw_imovel_visita_contagem"):]
        for bucket in ("realizadas", "nao_realizadas", "pendentes"):
            assert bucket in vista

    def test_excludes_soft_deleted_on_both_sides(self, code: str):
        """A route someone removed did not happen; counting its visitas would
        inflate exactly the number this view exists to report honestly."""
        vista = code[code.index("vw_imovel_visita_contagem"):]
        assert re.search(r"v\.deleted_at\s+IS\s+NULL", vista, re.I)
        assert re.search(r"r\.deleted_at\s+IS\s+NULL", vista, re.I)

    def test_groups_on_the_registry_codigo(self, code: str):
        """Grouped on `codigo`, so a sold imóvel keeps its counts forever.
        That is the entire point of the FK."""
        vista = code[code.index("vw_imovel_visita_contagem"):]
        assert re.search(r"GROUP\s+BY\s+v\.org_id\s*,\s*v\.codigo", vista, re.I)


class TestPostura:
    def test_is_forward_only_and_idempotent(self, code: str):
        assert code.count("CREATE TABLE IF NOT EXISTS") == 2
        assert "DROP TABLE" not in code.upper()

    def test_does_not_narrow_the_agendamento_tipo_check(self, code: str):
        """The Agendar button stops OFFERING 'visita'; the CHECK is untouched.
        Live rows carry that value, and a migration that rejects data which
        already exists is not a cutover, it is a break."""
        assert "atendimento_agendamentos" not in code

    def test_carries_the_file_only_banner(self, sql: str):
        assert "MIGRATION FILE ONLY" in sql


def _table_block(code: str, tabela: str) -> str:
    """The CREATE TABLE body for `tabela`, so a per-column assertion cannot be
    satisfied by a column of the OTHER table in this same file."""
    inicio = code.index(f"CREATE TABLE IF NOT EXISTS social_wiring.{tabela}")
    return code[inicio : code.index(");", inicio)]
