"""Unit tests for noctusai_lib.notifications field mapping.

Pure functions; no DB, no network. The mapper is the boundary between
core's English notification schema and every product's Portuguese API.
"""
from noctusai_lib.domain.notifications import (
    map_notification_to_pt,
    map_notification_from_pt,
)


class TestMapNotificationToPt:
    def test_renames_english_keys_to_portuguese(self):
        record = {"type": "invite", "title": "Hello", "message": "Hi", "read": False}
        out = map_notification_to_pt(record)
        assert out["tipo"] == "invite"
        assert out["titulo"] == "Hello"
        assert out["mensagem"] == "Hi"
        assert out["is_read"] is False

    def test_passes_through_unknown_keys(self):
        record = {"id": "abc", "created_at": "2026-04-21", "custom": 42}
        out = map_notification_to_pt(record)
        assert out["id"] == "abc"
        assert out["created_at"] == "2026-04-21"
        assert out["custom"] == 42

    def test_extracts_link_from_metadata_dict(self):
        out = map_notification_to_pt({"metadata": {"link": "/inbox/1"}})
        assert out["link"] == "/inbox/1"

    def test_link_is_none_when_metadata_missing(self):
        out = map_notification_to_pt({"id": "x"})
        assert out["link"] is None

    def test_link_is_none_when_metadata_is_not_a_dict(self):
        out = map_notification_to_pt({"metadata": "not-a-dict"})
        assert out["link"] is None

    def test_link_is_none_when_metadata_dict_has_no_link_key(self):
        out = map_notification_to_pt({"metadata": {"other": "value"}})
        assert out["link"] is None

    def test_empty_record_still_sets_link_key(self):
        out = map_notification_to_pt({})
        assert "link" in out
        assert out["link"] is None


class TestMapNotificationFromPt:
    def test_renames_portuguese_keys_to_english(self):
        data = {"tipo": "invite", "titulo": "Hi", "mensagem": "M", "is_read": True}
        out = map_notification_from_pt(data)
        assert out["type"] == "invite"
        assert out["title"] == "Hi"
        assert out["message"] == "M"
        assert out["read"] is True

    def test_passes_through_unknown_keys(self):
        out = map_notification_from_pt({"user_id": "u-1", "extra": 9})
        assert out["user_id"] == "u-1"
        assert out["extra"] == 9

    def test_round_trip_preserves_known_fields(self):
        original = {"type": "t", "title": "ti", "message": "msg", "read": False}
        pt = map_notification_to_pt(original)
        pt.pop("link", None)  # round-trip doesn't re-synthesize metadata
        back = map_notification_from_pt(pt)
        assert back == original


# ── write_in_app — the one product writer (2026-10-10) ───────────────────────
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from noctusai_lib.domain.notifications import (  # noqa: E402
    PRODUCT_NOTIFICATION_TYPE,
    in_app_rows,
    write_in_app,
)
from noctusai_lib.testing import MockSupabaseClient  # noqa: E402
from noctusai_lib.testing.migration_parser import parse_check_files  # noqa: E402
from noctusai_lib.testing.sql_check import compile_check  # noqa: E402

_CORE_MIGRATIONS = Path(__file__).resolve().parents[4] / "products" / "core" / "backend" / "migrations"


class TestWriteInApp:
    def test_rows_carry_core_type_and_the_product_kind_in_metadata(self):
        rows = in_app_rows(user_ids=["u2", "u1", "u1", None], kind="lembrete_cliente",
                           title="T", message="M", metadata={"link": "/x"}, org_id="o1")

        assert [r["user_id"] for r in rows] == ["u1", "u2"]
        assert all(r["type"] == PRODUCT_NOTIFICATION_TYPE == "system" for r in rows)
        assert rows[0]["metadata"] == {"link": "/x", "tipo": "lembrete_cliente"}
        assert rows[0]["org_id"] == "o1"

    def test_a_platform_alert_has_no_org(self):
        [row] = in_app_rows(user_ids=["admin"], kind="agents.credential_expiry", title="T", message="M")

        assert "org_id" not in row

    def test_every_row_satisfies_cores_real_type_check(self):
        """The CHECK compiled from core's own migrations — the one igig's
        own `type` values violated in production."""
        body = next(
            checks["notifications_type_check"]
            for table, checks in parse_check_files(sorted(_CORE_MIGRATIONS.glob("*.sql"))).items()
            if table.endswith(".notifications") and "notifications_type_check" in checks
        )
        check = compile_check(body)
        for kind in ("automacao", "sla_estourado", "lembrete_cliente", "edicao_fotos.lote_pronto"):
            [row] = in_app_rows(user_ids=["u"], kind=kind, title="T", message="M")
            assert check.verdict(row) is True, kind

    def test_write_inserts_one_row_per_recipient_and_returns_the_count(self):
        db = MockSupabaseClient(validate_schema=False)

        assert write_in_app(db, user_ids=["u1", "u2"], kind="k", title="T", message="M") == 2
        assert len(db.table("notifications").inserted_payloads) == 2

    def test_zero_recipients_writes_nothing(self):
        db = MockSupabaseClient(validate_schema=False)

        assert write_in_app(db, user_ids=[], kind="k", title="T", message="M") == 0
        assert db.table("notifications").inserted_payloads == []

    def test_a_kind_is_required(self):
        with pytest.raises(ValueError):
            in_app_rows(user_ids=["u"], kind="", title="T", message="M")
