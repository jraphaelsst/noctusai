"""Structural tests for `187_identificadores_canonicos.sql`.

Parse-based like the sibling migration tests: the file is a FILE, not an
applied change. 🔴 NO Postgres is available to the test suite, so what is
pinned here is what CAN be pinned without one: the SQL parses (including every
plpgsql body), the plpgsql twin is BYTE-IDENTICAL to the seed's (whose
`DO $parity$` block RAISEs at apply time if the SQL drifts from the shared case
table), the trigger / index / policy wiring is the one the app relies on, and
the Python twins of the SQL helpers agree with the SQL's own regexes on a
case table. The first real execution is the tech-lead's dry run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import identificadores as idf

HERE = Path(__file__).resolve()
MIGRATION = HERE.parents[1] / "migrations" / "187_identificadores_canonicos.sql"
SEED_TWIN = HERE.parents[4] / "seed" / "lib" / "sql" / "identificador.sql"
CASES = HERE.parents[4] / "seed" / "lib" / "shared" / "identificador.cases.json"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_migration_parses_including_every_plpgsql_body(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 20
    bodies = 0
    for stmt in statements:
        node = stmt.stmt
        if type(node).__name__ != "CreateFunctionStmt":
            continue
        opts = {o.defname: o for o in node.options}
        lang = opts["language"].arg.sval
        if lang != "plpgsql":
            continue
        body = opts["as"].arg[0].sval
        retorno = node.returnType.names[-1].sval
        # The C parser's verdict is the syntax check (`parse_plpgsql`'s Python
        # JSON decode of the tree trips on some bodies — not a syntax matter).
        pglast.parser.parse_plpgsql_json(f"CREATE FUNCTION _t() RETURNS {retorno} LANGUAGE plpgsql AS $x${body}$x$;")
        bodies += 1
    # twin: cpf-dv, cnpj-dv, rg-dv, canonizar (4) + the two trigger functions
    assert bodies == 6


def test_the_plpgsql_twin_is_byte_identical_to_the_seeds(sql: str):
    """Drift guard: adopting the twin means COPYING it. A product that edits
    its copy has forked the contract three runtimes assert against ONE case
    table (`seed/lib/shared/identificador.cases.json`)."""
    seed = SEED_TWIN.read_text(encoding="utf-8")
    inicio = seed.index("CREATE OR REPLACE FUNCTION identificador_cpf_dv_ok")
    assert seed[inicio:].strip() in sql


def test_the_migration_carries_the_parity_block_that_raises_on_drift(sql: str):
    """The block between BEGIN-CASES / END-CASES is GENERATED from the shared
    case table (the seed's own test pins that it is in sync); the migration
    carries it verbatim (byte-identity above), RAISE included — so applying a
    drifted twin fails loudly instead of canonicalising wrongly."""
    assert "DO $parity$" in sql and "RAISE EXCEPTION 'identificador SQL twin drifted" in sql
    assert "-- BEGIN-CASES" in sql and "-- END-CASES" in sql
    rows = len(re.findall(r"^\s*\('(canon|chave)',", sql, re.M))
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    com_sql = sum(1 for c in cases["ler"] if c.get("sql")) + sum(
        1 for c in cases.get("chave_busca", []) if c.get("sql")
    )
    assert rows >= com_sql > 0


def test_the_twin_is_created_in_the_products_own_schema(sql: str):
    assert "SET search_path = social_wiring, public;" in sql
    # the twin's functions are unqualified → created in the FIRST schema of the path
    assert "CREATE OR REPLACE FUNCTION canonizar_identificador(" in sql


def test_search_key_wrapper_pins_the_search_path_so_the_index_expression_is_safe(flat: str):
    assert (
        "CREATE OR REPLACE FUNCTION social_wiring.chave_busca_documento(tipo text, valor text) "
        "RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = social_wiring, public"
    ) in flat
    assert "idx_sw_clientes_cpf_chave" in flat
    assert "(social_wiring.chave_busca_documento('cpf', cpf))" in flat


def test_canonicalising_trigger_fires_on_the_write_columns_only(flat: str):
    for tabela, colunas, args in (
        ("clientes", "cpf, rg, endereco_cep", "'cpf:cpf', 'rg:rg', 'endereco_cep:cep'"),
        (
            "imovel_dados", "numero_matricula, prefeitura_cadastro_imobiliario",
            "'numero_matricula:matricula_imovel', 'prefeitura_cadastro_imobiliario:inscricao_municipal'",
        ),
        ("certidao_consultas", "documento", "'documento:@tipo_documento'"),
    ):
        assert (
            f"CREATE TRIGGER trg_a_identificadores_canonizar BEFORE INSERT OR UPDATE OF {colunas} "
            f"ON social_wiring.{tabela} FOR EACH ROW EXECUTE FUNCTION "
            f"social_wiring.canonizar_campos_identificadores( {args})"
        ) in flat, tabela


def test_chave_trigger_sorts_after_the_canonicalising_one(sql: str):
    """Triggers of one event fire in NAME order — the key must be computed over
    the already-canonical value."""
    assert "trg_a_identificadores_canonizar" < "trg_b_documentos_chave"
    assert "CREATE TRIGGER trg_b_documentos_chave" in sql


def test_a_value_is_only_rewritten_when_it_fits_and_the_raw_is_kept(flat: str):
    # NULL canonical (does not fit) → CONTINUE: the stored value is untouched.
    assert "IF canon IS NULL OR canon = bruto THEN CONTINUE; END IF;" in flat
    # …and an unchanged column of an UPDATE is never re-canonicalised.
    assert "IF TG_OP = 'UPDATE' AND (o ->> campo) IS NOT DISTINCT FROM bruto THEN CONTINUE; END IF;" in flat
    assert "INSERT INTO social_wiring.identificador_canonizacoes" in flat


def test_the_raw_log_is_org_scoped_rls_and_append_only(flat: str):
    assert "ALTER TABLE social_wiring.identificador_canonizacoes ENABLE ROW LEVEL SECURITY" in flat
    assert "FOR SELECT TO authenticated USING (org_id = public.current_org_id())" in flat
    assert "FOR ALL TO service_role USING (true) WITH CHECK (true)" in flat
    assert "origem IN ('trigger', 'backfill')" in flat


def test_it_never_rewrites_existing_rows_or_the_empresas_key(flat: str):
    """Existing rows are the BACKFILL's (dry-run first); `empresas.cnpj` is the
    identity key and stays digits-only."""
    assert not re.search(r"\bUPDATE social_wiring\.", flat)
    assert "DELETE FROM" not in flat and "DROP TABLE" not in flat
    assert "ON social_wiring.empresas" not in flat


def test_clientes_por_cpf_keeps_its_contract_and_moves_to_the_canonical_key(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.clientes_por_cpf( p_org_id UUID, p_cpfs TEXT[] )" in flat
    assert "RETURNS SETOF social_wiring.clientes" in flat
    assert "SECURITY INVOKER" in flat and "SECURITY DEFINER" not in flat
    assert "social_wiring.chave_busca_documento('cpf', c.cpf) IN" in flat
    assert "SELECT social_wiring.chave_busca_documento('cpf', k) FROM unnest(p_cpfs)" in flat
    assert "GRANT EXECUTE ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) TO service_role" in flat
    assert "REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM PUBLIC" in flat


def test_non_conforming_view_is_invoker_and_names_both_situations(flat: str):
    assert "CREATE OR REPLACE VIEW social_wiring.vw_identificadores_nao_conformes WITH (security_invoker = true)" in flat
    assert "'nao_cabe'" in flat and "'canonizavel'" in flat


# ─── the SQL helpers' Python twins agree with the SQL's own regex ───────────

_UF_SQL = re.compile(r"[/.\- ]([A-Z]{2})\s*$")
_UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def _uf_do_orgao_sql_model(orgao):
    """Line-for-line model of `identificador_uf_do_orgao` (187)."""
    if orgao is None or not orgao.strip():
        return None
    up = orgao.strip().upper()
    if up.startswith("IIRGD"):
        return "SP"
    m = _UF_SQL.search(up)
    return m.group(1) if m and m.group(1) in _UFS else None


@pytest.mark.parametrize(
    "orgao",
    ["SSP/SP", "SSP-SP", "SSP SP", "IIRGD", "IIRGD/SP", "SSP", "DETRAN/RJ", "IFP RJ",
     "SSP-DE", "Polícia Civil de São Paulo", "", None, "DPF"],
)
def test_uf_do_orgao_sql_model_matches_the_python_twin(orgao):
    assert _uf_do_orgao_sql_model(orgao) == idf.uf_do_orgao(orgao)
