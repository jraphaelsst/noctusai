"""`event_inbox_table_sql` -- the DDL `RealSupabaseEventInbox` expects."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.payments import DEFAULT_EVENT_INBOX_TABLE, event_inbox_table_sql
from noctusai_lib.testing.migration_parser import parse_sql


def test_columns_match_what_the_real_inbox_inserts():
    cols = parse_sql(event_inbox_table_sql("shop"), source_label="inbox")
    # the Real inbox inserts exactly (gateway, event_id, claimed_at)
    assert cols["shop.payment_gateway_events"] == {"gateway", "event_id", "claimed_at"}
    assert DEFAULT_EVENT_INBOX_TABLE == "payment_gateway_events"


def test_primary_key_is_the_idempotency_guarantee():
    sql = event_inbox_table_sql("shop")
    assert "PRIMARY KEY (gateway, event_id)" in sql


def test_rls_on_and_authenticated_has_no_policy():
    sql = event_inbox_table_sql("shop")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert '"service_role_bypass"' in sql
    assert "TO authenticated" not in sql


def test_is_rerunnable():
    sql = event_inbox_table_sql("shop")
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert 'DROP POLICY IF EXISTS "service_role_bypass"' in sql


def test_custom_table_name_and_schema_validation():
    assert "shop.gw_events" in event_inbox_table_sql("shop", table="gw_events")
    with pytest.raises(ValueError):
        event_inbox_table_sql("  ")
