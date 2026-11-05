"""Platform grant ledger migration (060, Julia-line CONTRACT D1): service-role only, one live grant per
(org, agent, product), no secret column."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "agent_product_grants")


def test_columns_follow_d1_and_hold_no_secret():
    body = SQL[SQL.index("CREATE TABLE IF NOT EXISTS agents.agent_product_grants"):]
    body = body[: body.index(");")]
    for col in ("org_id", "agent_id", "product", "status", "channel_token_id", "product_token_id", "expires_at",
                "created_by", "revoked_by", "revoked_at", "last_delivered_at", "last_error"):
        assert col in body
    assert "expires_at          TIMESTAMPTZ NULL" in body  # NULL = no expiry
    assert "'pendente', 'ativo', 'revogado', 'falhou'" in body
    assert "REFERENCES agents.api_tokens(id)" in body
    for forbidden in ("secret", "token_hash", "credential"):
        assert forbidden not in body.lower()


def test_one_live_grant_per_triple_is_a_partial_unique_index():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_product_grants_one_live" in SQL
    assert "(org_id, agent_id, product)" in SQL
    assert "WHERE status IN ('pendente', 'ativo')" in SQL


def test_service_role_only():
    assert "ALTER TABLE agents.agent_product_grants ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.agent_product_grants FROM anon, authenticated" in SQL
    assert "TO service_role USING (true) WITH CHECK (true)" in SQL
