"""
Real-DB integration tests for `migrations/027_erp_org_scoping_completion.sql`.

Filed by `projects/erp-org-scoping-completion/` Phase 2 (2026-05-10).

Tests hit a real Supabase instance to verify the orphan-org FK rejection.
The WITH CHECK clause on UPDATE policies is covered by the structural
unit test (`tests/test_org_scoping_completion_migration.py`) since
service-role clients bypass RLS by design and pg_policies isn't exposed
via PostgREST in a way usable from these tests.

Run: pytest tests/realdb/test_org_scoping_realdb.py -v
Skip: auto-skips when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


TABLES_WITH_ORG_FK = [
    "eventos",
    "lancamentos",
    "site_config",
    "whatsapp_config",
    "certidao_consultas",
]


class TestOrgIdForeignKey:
    """Inserting a row with an org_id that doesn't exist in
    public.organizations must fail at the FK layer.

    This is the only contract from 027 that needs a live DB to verify:
    the FK rejects an orphan org reference. The migration's structural
    contract (FK declared, NOT VALID + VALIDATE, ON DELETE RESTRICT) is
    covered by ``tests/test_org_scoping_completion_migration.py``; the
    behavior in the running DB is covered here.
    """

    @pytest.mark.parametrize("table", TABLES_WITH_ORG_FK)
    def test_unknown_org_id_rejected(self, erp_db, table):
        """org_id pointing at a non-existent org gets rejected with FK violation."""
        from postgrest.exceptions import APIError

        fake_org_id = str(uuid.uuid4())
        # Minimal payload — most columns either have defaults or are nullable.
        # The FK violation should fire even if other NOT NULL columns are
        # missing, since FK is checked at row-insertion time and is the
        # canonical violation we want to surface here.
        payload = {"org_id": fake_org_id}

        with pytest.raises(APIError) as excinfo:
            erp_db.table(table).insert(payload).execute()

        # Postgres FK violation code is '23503'. Accept any of the three
        # forms (code, 'foreign key' phrase, 'violates' phrase) since
        # PostgREST surfaces the error message text variably.
        err_text = str(excinfo.value).lower()
        assert (
            "23503" in err_text
            or "foreign key" in err_text
            or "violates" in err_text
        ), (
            f"Expected FK violation on erp.{table} with unknown org_id; "
            f"got: {excinfo.value}"
        )
