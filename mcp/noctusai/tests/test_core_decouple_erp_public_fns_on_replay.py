"""Core 110 (decouple_erp_public_fns) on the REAL core chain on PGlite.

Proves, by running it, that after 110 a new ``auth.users`` insert (and a licence grant,
and the nightly usage snapshot) no longer touch the ``erp`` schema:

1. A PRE-STATE fixture (inserted right before 110) recreates what prod had: ``erp.profiles``
   and ``erp.user_roles`` with TRIPWIRE triggers that raise on any write, the old
   ``handle_new_user`` / ``assign_default_corretor_role`` bodies and their two ``auth.users``
   triggers, and the old ``provision_erp``. A CONTROL step proves the tripwires bite: an
   ``auth.users`` insert BEFORE 110 must fail on the erp tripwire (so the green below is not
   vacuous).
2. With 110 applied, inserting users succeeds with zero erp writes, the corretor trigger and
   function and ``provision_erp`` are gone, no remaining function body mentions ``erp.``
   (``has_role`` is the documented S8 exception and still exists), granting a licence for the
   erp product no longer calls ``provision_erp`` and ``snapshot_product_usage()`` runs.
3. Dropping 110 from the chain makes the control-style insert fail again (the migration is the
   cause of the change).
"""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_path
from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_MIGRATIONS = Path(REPO_ROOT) / "products/core/backend/migrations"
_M110 = migration_path(_MIGRATIONS, "decouple_erp_public_fns")
_M110_REL = str(_M110.relative_to(REPO_ROOT))

_PRE = "core-110-prestate-fixture"
_CONTROL = "core-110-control-insert-trips-erp"
_POST = "core-110-post-assertions"

_PRE_SQL = """
CREATE SCHEMA IF NOT EXISTS erp;
DO $$ BEGIN
  CREATE TYPE erp.app_role AS ENUM ('admin', 'dev', 'corretor');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS erp.profiles (
  id uuid PRIMARY KEY, nome text, email text, telefone text, org_id uuid);
CREATE TABLE IF NOT EXISTS erp.user_roles (
  user_id uuid NOT NULL, role erp.app_role NOT NULL, UNIQUE (user_id, role));
CREATE OR REPLACE FUNCTION erp.tripwire() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'erp tripwire: write to %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME; END $$;
DROP TRIGGER IF EXISTS tripwire ON erp.profiles;
CREATE TRIGGER tripwire BEFORE INSERT OR UPDATE OR DELETE ON erp.profiles
  FOR EACH ROW EXECUTE FUNCTION erp.tripwire();
DROP TRIGGER IF EXISTS tripwire ON erp.user_roles;
CREATE TRIGGER tripwire BEFORE INSERT OR UPDATE OR DELETE ON erp.user_roles
  FOR EACH ROW EXECUTE FUNCTION erp.tripwire();

-- live prod definitions (2026-11-08), as they were before 110
CREATE OR REPLACE FUNCTION public.handle_new_user() RETURNS trigger LANGUAGE plpgsql
  SECURITY DEFINER SET search_path TO 'public' AS $f$
BEGIN
  INSERT INTO erp.profiles (id, nome, email, telefone, org_id)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email), NEW.email,
          COALESCE(NEW.raw_user_meta_data->>'telefone', ''),
          NULLIF(NEW.raw_user_meta_data->>'org_id', '')::uuid);
  RETURN NEW;
END; $f$;
CREATE OR REPLACE FUNCTION public.assign_default_corretor_role() RETURNS trigger LANGUAGE plpgsql
  SECURITY DEFINER SET search_path TO 'public' AS $f$
BEGIN
  INSERT INTO erp.user_roles (user_id, role) VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  RETURN NEW;
END; $f$;
CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role erp.app_role) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public' AS
  $f$ SELECT EXISTS (SELECT 1 FROM erp.user_roles WHERE user_id = _user_id AND role = _role); $f$;
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
DROP TRIGGER IF EXISTS on_auth_user_created_assign_role ON auth.users;
CREATE TRIGGER on_auth_user_created_assign_role AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.assign_default_corretor_role();
"""

#: BEFORE 110 an auth.users insert must hit the erp tripwire; the block swallows exactly that
#: error and fails on anything else (including "no error at all").
_CONTROL_SQL = """
DO $$
BEGIN
  BEGIN
    INSERT INTO auth.users (id, email) VALUES (gen_random_uuid(), 'control@probe.test');
    RAISE EXCEPTION 'CONTROL_NOT_TRIPPED: auth.users insert did not touch erp';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'CONTROL_NOT_TRIPPED%' OR SQLERRM NOT LIKE '%erp tripwire%' THEN
      RAISE;
    END IF;
  END;
END $$;
"""

_POST_SQL = """
DO $$
DECLARE
  v_u1 uuid := gen_random_uuid();
  v_u2 uuid := gen_random_uuid();
  v_org uuid := gen_random_uuid();
  v_pid uuid;
  v_bad text;
BEGIN
  -- a new signup (with and without metadata) no longer touches erp (tripwires are still armed)
  INSERT INTO auth.users (id, email) VALUES (v_u1, 'u1@probe.test');
  INSERT INTO auth.users (id, email, raw_user_meta_data)
    VALUES (v_u2, 'u2@probe.test', jsonb_build_object('nome', 'X', 'org_id', v_org));
  IF (SELECT count(*) FROM erp.profiles) <> 0 OR (SELECT count(*) FROM erp.user_roles) <> 0 THEN
    RAISE EXCEPTION 'erp rows were written';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created_assign_role'
             AND NOT tgisinternal) THEN
    RAISE EXCEPTION 'corretor trigger still present';
  END IF;
  IF to_regprocedure('public.assign_default_corretor_role()') IS NOT NULL THEN
    RAISE EXCEPTION 'assign_default_corretor_role still present';
  END IF;
  IF to_regprocedure('public.provision_erp(uuid)') IS NOT NULL THEN
    RAISE EXCEPTION 'provision_erp still present';
  END IF;
  IF to_regprocedure('public.handle_new_user()') IS NULL THEN
    RAISE EXCEPTION 'handle_new_user must be kept (no-op) until S8';
  END IF;

  -- no public function other than the documented S8 exception (has_role) mentions erp.
  SELECT string_agg(p.oid::regprocedure::text, ', ') INTO v_bad
    FROM pg_proc p
   WHERE p.pronamespace = 'public'::regnamespace
     AND p.proname <> 'has_role' AND p.prosrc ~* '\\merp\\.';
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'public functions still reference erp: %', v_bad;
  END IF;
  IF to_regprocedure('public.has_role(uuid,erp.app_role)') IS NULL THEN
    RAISE EXCEPTION 'has_role must still exist (S8 contract step)';
  END IF;

  -- a licence grant for the erp product: trigger runs, no provision_erp, no erp write
  SELECT id INTO v_pid FROM public.products WHERE slug = 'erp-imobiliario';
  IF v_pid IS NULL THEN
    SELECT id INTO v_pid FROM public.products ORDER BY slug LIMIT 1;
    UPDATE public.products SET slug = 'erp-imobiliario' WHERE id = v_pid;
  END IF;
  INSERT INTO public.organizations (id, nome, slug) VALUES (v_org, 'Probe', 'noc-110-probe');
  INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_org, v_pid, 'active');
  PERFORM public.snapshot_product_usage();
END $$;
"""


def _run(overrides: dict[str, str], steps_tail: list[tuple[str, str]]) -> dict[str, list]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", overrides)
    idx = next(i for i, s in enumerate(steps) if s["file"] == _M110.name)
    steps.insert(idx, {"product": "core", "file": _PRE, "sql": _PRE_SQL, "mode": "file", "twice": False})
    steps.insert(idx + 1, {"product": "core", "file": _CONTROL, "sql": _CONTROL_SQL,
                           "mode": "file", "twice": False})
    for name, sql in steps_tail:
        steps.append({"product": "core", "file": name, "sql": sql, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    return {st["file"]: st["failures"] for st in res["steps"]}


def test_migration_110_is_the_only_one_with_its_name():
    assert [p.name for p in _MIGRATIONS.glob("*_decouple_erp_public_fns.sql")] == [_M110.name]


def test_after_110_new_users_licences_and_snapshot_never_touch_erp(pglite):
    out = _run({}, [(_POST, _POST_SQL)])
    assert out[_PRE] == [], out[_PRE]
    assert out[_CONTROL] == [], f"control: the tripwire did not fire before 110: {out[_CONTROL]}"
    assert out[_M110.name] == [], out[_M110.name]
    assert out[_POST] == [], out[_POST]


def test_110_is_idempotent_applied_twice(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "core", {_M110_REL}, "worktree", {})
    idx = next(i for i, s in enumerate(steps) if s["file"] == _M110.name)
    steps.insert(idx, {"product": "core", "file": _PRE, "sql": _PRE_SQL, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    st = next(s for s in res["steps"] if s["file"] == _M110.name)
    assert st["failures"] == [], st["failures"]


def test_without_110_the_post_assertions_fail(pglite):
    out = _run({_M110_REL: "SELECT 1;\n"}, [(_POST, _POST_SQL)])
    assert out[_POST], "the post-assertions passed without 110: the test is vacuous"
