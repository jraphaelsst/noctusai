"""Migration `julia_relatorios` (313): what the SQL promises is what the services write -- the destination modes, the report
types and delivery statuses, the idempotency key, the offered-listing columns -- and the new tables are backend-only."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.services import julia_relatorio_service as svc

SQL = migration_sql(Path(__file__).resolve().parents[2], "julia_relatorios")  # by NAME: a renumber is safe


def _valores(coluna: str) -> tuple[str, ...]:
    m = re.search(rf"{coluna}\s+text\s+(?:NOT NULL\s+)?(?:DEFAULT '[a-z]+'\s+)?CHECK \({coluna} IN \(([^)]*)\)\)", SQL)
    assert m, coluna
    return tuple(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_the_vocabularies_match_the_service():
    assert _valores("modo") == svc.MODOS_DESTINO
    assert _valores("tipo") == svc.TIPOS
    assert _valores("envio_status") == svc.STATUS_ENVIO


def test_the_destination_is_one_row_per_org_and_names_a_user_never_a_number():
    assert re.search(r"julia_relatorio_destino \(\s*org_id\s+uuid\s+PRIMARY KEY", SQL)
    assert "usuario_id" in SQL and "modo <> 'usuario' OR usuario_id IS NOT NULL" in SQL
    destino = SQL[SQL.index("julia_relatorio_destino ("):SQL.index("julia_relatorio_destino_auditoria (")]
    assert "numero" not in destino and "codigo" not in destino  # the phone is the user's own, in noc


def test_the_report_ledger_is_idempotent_per_org_and_erased_with_its_contato():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS julia_relatorios_org_chave_uk" in SQL and "(org_id, chave) WHERE chave IS NOT NULL" in SQL
    assert "REFERENCES social_wiring.julia_contatos (id) ON DELETE CASCADE" in SQL


def test_the_offered_listings_columns_exist_on_both_tables_as_not_null_arrays():
    for tabela in ("leads", "julia_contatos"):
        assert re.search(rf"ALTER TABLE social_wiring\.{tabela}\s+ADD COLUMN IF NOT EXISTS imoveis_oferecidos text\[\] NOT NULL DEFAULT '\{{\}}'", SQL), tabela


def test_it_is_idempotent_forward_only_and_backend_only():
    assert SQL.count("CREATE TABLE IF NOT EXISTS") == 3
    assert not re.search(r"\bDROP (TABLE|COLUMN)\b", SQL)
    for t in ("julia_relatorio_destino", "julia_relatorio_destino_auditoria", "julia_relatorios"):
        assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in SQL
        assert f"REVOKE ALL ON social_wiring.{t} FROM PUBLIC, anon, authenticated" in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL and "TO service_role" in SQL and "REVOKE ALL" in SQL
    assert not re.search(r"TO authenticated", SQL)
    assert "SECURITY DEFINER" not in SQL.replace("NO SECURITY DEFINER", "")


def test_every_destination_change_is_audited():
    assert "julia_relatorio_destino_auditoria" in SQL and "antes" in SQL and "depois" in SQL and "CHECK (evento IN ('alterado'))" in SQL


def test_whatsapp_origin_documents_are_unverified_by_flag():
    assert "ADD COLUMN IF NOT EXISTS verificado boolean NOT NULL DEFAULT true" in SQL
