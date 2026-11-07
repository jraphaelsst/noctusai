"""`private_org_bucket_sql` -- default mode is unchanged; service-only mode emits no authenticated policy."""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import private_org_bucket_sql


def test_default_mode_keeps_the_four_authenticated_policies():
    sql = private_org_bucket_sql("b")
    assert sql.count("TO authenticated") == 4
    assert "UPDATE storage.buckets" not in sql


def test_service_only_drops_authenticated_policies_and_sets_limits():
    sql = private_org_bucket_sql("b", service_only=True, file_size_limit=5, allowed_mime_types=("image/png",))
    assert "TO authenticated" not in sql
    assert 'DROP POLICY IF EXISTS "b_storage_select" ON storage.objects;' in sql
    assert "file_size_limit = 5" in sql and "ARRAY['image/png']" in sql
    assert 'CREATE POLICY "b_storage_service"' in sql
