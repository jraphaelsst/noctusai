"""MockSupabaseClient resolves PostgREST embedded resources (`select("a, rel(b)")`) through the
migration-declared foreign keys, the way the real server does -- so a read that folds a lookup
into its parent query (one round trip, not two) is testable at all.

Pins: many-to-one -> object | None; one-to-many -> list; projection + alias; the shared table
rows are never mutated; a hand-seeded nested key is kept; unlinked / hinted embeds stay as
before (key absent); the FK parser reads every declaration shape the migrations use.
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient
from noctusai_lib.testing.migration_parser import parse_foreign_key_sql

ORG = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000b"
USER = "bbbbbbbb-0000-0000-0000-000000000001"


def _db():
    db = MockSupabaseClient()
    db.set_table_data("organizations", [
        {"id": ORG, "nome": "Alpha", "is_platform": True},
        {"id": OTHER, "nome": "Beta", "is_platform": False},
    ])
    db.set_table_data("noctus_users", [{"id": USER, "org_id": ORG, "org_role": "owner", "role": "admin"}])
    db.set_table_data("org_memberships", [
        {"user_id": USER, "org_id": ORG, "org_role": "owner", "status": "active"},
        {"user_id": USER, "org_id": OTHER, "org_role": "admin", "status": "active"},
    ])
    return db


class TestManyToOne:
    def test_embed_is_the_referenced_row_projected(self):
        rows = _db().table("noctus_users").select("org_id, role, organizations(is_platform, nome)").execute().data
        assert rows[0]["organizations"] == {"is_platform": True, "nome": "Alpha"}

    def test_alias_and_column_alias(self):
        rows = _db().table("org_memberships").select("org_id, org:organizations(name:nome)") \
            .eq("org_id", OTHER).execute().data
        assert rows[0]["org"] == {"name": "Beta"}

    def test_missing_referenced_row_is_null(self):
        db = _db()
        db.set_table_data("organizations", [])
        assert db.table("noctus_users").select("organizations(nome)").execute().data[0]["organizations"] is None

    def test_star_embed_is_the_whole_row_and_single_works(self):
        row = _db().table("noctus_users").select("*, organizations(*)").eq("id", USER).single().execute().data
        assert row["organizations"]["nome"] == "Alpha" and row["role"] == "admin"


class TestOneToMany:
    def test_reverse_embed_is_a_list(self):
        rows = _db().table("organizations").select("id, org_memberships(org_role)").eq("id", OTHER).execute().data
        assert rows[0]["org_memberships"] == [{"org_role": "admin"}]


class TestUnchangedShapes:
    def test_shared_rows_are_not_mutated(self):
        db = _db()
        db.table("noctus_users").select("organizations(nome)").execute()
        assert "organizations" not in db.table("noctus_users").select("*").execute().data[0]

    def test_hand_seeded_nested_key_is_kept(self):
        db = _db()
        db.set_table_data("noctus_users", [{"id": USER, "org_id": ORG, "organizations": {"nome": "Seeded"}}])
        assert db.table("noctus_users").select("organizations(nome)").execute().data[0]["organizations"] == {
            "nome": "Seeded"}

    def test_hinted_or_unlinked_embeds_are_left_absent(self):
        db = _db()
        hinted = db.table("noctus_users").select("organizations!inner(nome)").execute().data[0]
        unlinked = db.table("noctus_users").select("org_id, not_a_table(x)").execute().data[0]
        assert "organizations" not in hinted and "not_a_table" not in unlinked


class TestForeignKeyParser:
    def test_every_declaration_shape(self):
        fks = parse_foreign_key_sql("""
            CREATE TABLE a (id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id),
                            owner uuid REFERENCES auth.users, x int,
                            CONSTRAINT fk_b FOREIGN KEY (b_id) REFERENCES public.b (key));
            ALTER TABLE a ADD COLUMN c_id uuid REFERENCES c(id) ON DELETE SET NULL;
            ALTER TABLE public.a ADD CONSTRAINT fk_d FOREIGN KEY (d_id) REFERENCES d(id);
            CREATE TABLE gone (id uuid, a_id uuid REFERENCES a(id));
            DROP TABLE gone;
        """)
        assert fks == {"public.a": {
            "org_id": ("public.organizations", "id"),
            "owner": ("auth.users", "id"),
            "b_id": ("public.b", "key"),
            "c_id": ("public.c", "id"),
            "d_id": ("public.d", "id"),
        }}
