"""Organ guard probes -- declared once per organ, derived for every rendering product.

Pins the gate<->methodology contract (KB methodology-execution-discipline § 8): an organ generator
cannot ship a UNIQUE / CHECK / trigger guard without a behaviour probe, every declared probe really
makes its guard refuse on PGlite (real PG16) with the organ's own DDL applied, a probe against a
database where the migration is not applied reports `pending`, and `verify_db_guards` derives the
probes for every product that rendered an organ migration.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[3]
for sub in ("seed/lib/backend", "seed/framework/backend"):
    sys.path.insert(0, str(REPO_ROOT / sub))

import pytest  # noqa: E402

from noctusai_seed.organs import ORGAN_REGISTRY, organ_guard_probes, organ_migration_sql  # noqa: E402
from tools.noctus.dev import migration_replay as mr  # noqa: E402
from tools.noctus.dev import verify_db_guards as vdg  # noqa: E402
from tools.noctus.dev.compliance import _detect_guard_objects  # noqa: E402

SCHEMA = "probe_s"
_SENT = re.compile(r"NOC_PROBE:(\w+):")
_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+\w+\.(\w+)", re.IGNORECASE)

#: Install order on a fresh schema (organs depend on parties/items/inventory/commerce base).
_INSTALL_ORDER = ["commerce_money", "commerce_fiscal", "jobs", "parties", "items", "inventory", "finance", "quotes", "purchasing", "contracts"]


def _commerce_base_sql() -> str:
    from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration

    return commerce_migration(CommerceConfig(schema=SCHEMA), SCHEMA)


def _declared(organ: str):
    return organ_guard_probes(organ, SCHEMA)


# -- completeness: a generator cannot add a guard without a probe ------------------------------------------------


@pytest.mark.parametrize("organ", sorted(ORGAN_REGISTRY))
def test_every_guard_a_generator_emits_has_a_declared_probe(organ):
    emitted = {g["guard_name"] for g in _detect_guard_objects(organ_migration_sql(organ, SCHEMA))}
    declared = {p.guard_name for p in _declared(organ)}
    assert ORGAN_REGISTRY[organ].guard_probes is not None, f"organ {organ!r} declares no guard_probes"
    assert emitted - declared == set(), f"{organ}: generator guards with NO behaviour probe: {sorted(emitted - declared)}"
    assert declared - emitted == set(), f"{organ}: probes for guards the generator no longer emits: {sorted(declared - emitted)}"


def test_probes_require_only_tables_some_migration_creates():
    created = set(_TABLE_RE.findall(_commerce_base_sql()))
    for organ in ORGAN_REGISTRY:
        created |= set(_TABLE_RE.findall(organ_migration_sql(organ, SCHEMA)))
    for organ in ORGAN_REGISTRY:
        for p in _declared(organ):
            assert set(p.requires) <= created, f"{organ}/{p.probe_key} requires unknown tables {set(p.requires) - created}"


def test_probe_keys_are_unique_per_organ():
    for organ in ORGAN_REGISTRY:
        keys = [p.probe_key for p in _declared(organ)]
        assert len(keys) == len(set(keys)), organ


def test_every_probe_sql_is_a_wrappable_single_statement():
    for organ in ORGAN_REGISTRY:
        for p in _declared(organ):
            sql = vdg._organ_probe_sql(SCHEMA, p)
            assert vdg.wrap_rollback_only(sql).startswith("BEGIN;")


# -- derivation: every product that rendered an organ migration gets the organ's probes ---------------------------


def _product(root: Path, slug: str, schema: str, organs: dict[str, str]) -> None:
    app = root / slug / "backend" / "app"
    mig = root / slug / "backend" / "migrations"
    app.mkdir(parents=True)
    mig.mkdir(parents=True)
    (app / "main.py").write_text(f'app = create_product_app(slug="{slug}", schema="{schema}")\n')
    (mig / "001_base.sql").write_text("-- hand written\nSELECT 1;\n")
    for filename, organ in organs.items():
        (mig / filename).write_text(organ_migration_sql(organ, schema))


def test_probes_are_derived_per_rendering_product_and_schema(tmp_path):
    _product(tmp_path, "alpha", "alpha_s", {"002_parties.sql": "parties", "003_items.sql": "items"})
    _product(tmp_path, "beta", "beta_s", {"010_parties.sql": "parties", "011_parties_rev2.sql": "parties"})
    _product(tmp_path, "gamma", "gamma_s", {})
    probes = vdg.derive_organ_probes(products_dir=tmp_path)
    by_product: dict[str, list] = {}
    for p in probes:
        by_product.setdefault(p.product, []).append(p)
    assert set(by_product) == {"alpha", "beta"}  # a product with no rendered organ gets none
    assert {p.guard_name for p in by_product["alpha"]} == {p.guard_name for p in _declared("parties")} | {p.guard_name for p in _declared("items")}
    assert all(p.schema == "alpha_s" and SCHEMA not in p.sql for p in by_product["alpha"])
    assert all("alpha_s." in p.sql for p in by_product["alpha"])
    # the LATEST revision file gates the probe (pending until it is applied)
    assert {p.migrations for p in by_product["beta"]} == {("011_parties_rev2.sql",)}
    assert len({p.id for p in probes}) == len(probes)


def test_unresolvable_schema_and_undeclared_organ_are_failing_probes_not_silence(tmp_path):
    _product(tmp_path, "alpha", "alpha_s", {"002_parties.sql": "parties"})
    (tmp_path / "alpha" / "backend" / "app" / "main.py").write_text("app = None\n")  # schema not declared
    probes = vdg.derive_organ_probes(products_dir=tmp_path)
    assert [p.id for p in probes] == ["organ.parties.alpha.schema"]

    class _Spec:
        migration_header = "-- Fake organ"
        guard_probes = None

    (tmp_path / "alpha" / "backend" / "migrations" / "003_fake.sql").write_text("-- Fake organ\nSELECT 1;\n")
    probes = vdg.derive_organ_probes(products_dir=tmp_path, registry={"fake": _Spec()})
    assert [p.id for p in probes] == ["organ.fake.alpha.undeclared"]


# -- pending: a probe whose table is not in the DB yet is neither pass nor fail ----------------------------------


class _FakeExecutor:
    def __init__(self, error: str):
        self.error = error
        self.sql: list[str] = []

    def execute(self, sql):
        self.sql.append(sql)
        return {"ok": False, "error": self.error}


def test_pending_sentinel_is_pending_migration_not_failure_or_pass():
    gp = vdg.GuardProbe(id="x", product="p", schema=SCHEMA, guard_name="g", kind="write_refusal", sql=vdg._do_block("BEGIN NULL; END;"), rationale="r")
    r = vdg.run_probe(gp, _FakeExecutor("ERROR: NOC_PROBE:pending: probe_s.pty_parties does not exist (organ migration not applied)"))
    assert r["status"] == "pending_migration" and r["outcome"] == "pending"
    result = vdg.verify_db_guards(
        executor=_FakeExecutor("NOC_PROBE:pending: probe_s.pty_parties does not exist"), registry=(gp,),
        ledger_lookup=lambda product: None,
    )
    assert result["status"] == "clean"  # nothing failed, nothing found -- but it is not "checked"
    assert result["checked"] == 0 and [p["probe_id"] for p in result["pending"]] == ["x"]
    assert result["findings"] == [] and result["failures"] == []


# -- behaviour: every declared probe really makes its guard refuse (PGlite, real PG16) ---------------------------


def _probe_steps(prefix: str) -> list[dict]:
    steps = []
    for organ in _INSTALL_ORDER:
        for p in _declared(organ):
            steps.append({
                "product": "organ-probes", "file": f"{prefix}:{organ}:{p.probe_key}",
                "sql": vdg.wrap_rollback_only(vdg._organ_probe_sql(SCHEMA, p)), "mode": "file", "twice": False,
            })
    return steps


def _outcomes(res: dict, prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"].startswith(prefix + ":"):
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"][len(prefix) + 1:]] = m.group(1) if m else f"UNCLASSIFIED: {err or 'no error'}"
    return out


def _step(name: str, sql: str) -> dict:
    return {"product": "organ-probes", "file": name, "sql": sql, "mode": "file", "twice": False}


def test_every_organ_probe_refuses_on_pglite_and_flags_a_missing_guard(pglite):
    stubs = (
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};"
        "CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;"
        "CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;"
    )
    steps = _probe_steps("pending")  # BEFORE any organ table exists
    steps.insert(0, _step("setup", stubs))
    steps.append(_step("install:commerce", _commerce_base_sql()))
    for organ in _INSTALL_ORDER:
        steps.append(_step(f"install:{organ}", organ_migration_sql(organ, SCHEMA)))
    steps += _probe_steps("live")
    # a guard that does not exist must be FLAGGED, not passed: drop two and re-probe them
    steps.append(_step("drop-guards", f"DROP INDEX {SCHEMA}.uq_pty_parties_doc; ALTER TABLE {SCHEMA}.fin_entries DROP CONSTRAINT fin_entries_source_check;"))
    steps += [s for s in _probe_steps("dropped") if s["file"].endswith((":uq_pty_parties_doc", ":fin_entries_source_check"))]

    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    for st in res["steps"]:
        if st["file"] == "setup" or st["file"].startswith("install:"):
            assert not st["failures"], (st["file"], st["failures"])

    expected = {f"{organ}:{p.probe_key}" for organ in _INSTALL_ORDER for p in _declared(organ)}
    pending = _outcomes(res, "pending")
    assert set(pending) == expected and set(pending.values()) == {"pending"}, pending
    live = _outcomes(res, "live")
    assert set(live) == expected
    assert {k: v for k, v in live.items() if v != "refused"} == {}, "probes that did not report `refused`"
    dropped = _outcomes(res, "dropped")
    assert dropped == {"parties:uq_pty_parties_doc": "permitted", "finance:fin_entries_source_check": "permitted"}


# -- keeper: an organ-rendered guard is covered iff the organ declares a probe for it ----------------------------


def _write_mig(root: Path, product: str, filename: str, sql: str) -> str:
    d = root / "products" / product / "backend" / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(sql, encoding="utf-8")
    return f"products/{product}/backend/migrations/{filename}"


def test_keeper_accepts_every_organ_rendering_with_no_allowlist_entry(tmp_path):
    from tools.noctus.dev import compliance as C

    paths = [_write_mig(tmp_path, "demo", f"{i + 2:03d}_{organ}.sql", organ_migration_sql(organ, "demo_s")) for i, organ in enumerate(sorted(ORGAN_REGISTRY))]
    assert C.check_migration_guard_has_probe(repo_root=tmp_path, paths=paths) == []
    assert not [e for e in C._GUARD_PROBE_ALLOWLIST if "/commerce/" in e[0]]  # the old hand-written entries are gone


def test_keeper_flags_an_organ_guard_the_organ_declares_no_probe_for(tmp_path):
    from tools.noctus.dev import compliance as C

    sql = organ_migration_sql("parties", "demo_s") + "\nALTER TABLE demo_s.pty_parties ADD CONSTRAINT pty_parties_zz_new_guard CHECK (kind IS NOT NULL);\n"
    rel = _write_mig(tmp_path, "demo", "002_parties.sql", sql)
    findings = C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel])
    assert len(findings) == 1 and "pty_parties_zz_new_guard" in findings[0]["issue"] and "parties" in findings[0]["issue"]


def test_keeper_does_not_let_an_unrelated_registered_name_cover_an_organ_guard(tmp_path):
    """`ux_jobs_dedupe_key` is registered for CORE's hand-written jobs table; a rendered organ file is judged
    by the organ's own declaration only (and `jobs` declares it, so this must still pass)."""
    from tools.noctus.dev import compliance as C

    sql = organ_migration_sql("parties", "demo_s") + "\nCREATE UNIQUE INDEX ux_jobs_dedupe_key ON demo_s.pty_parties (org_id, legal_name);\n"
    rel = _write_mig(tmp_path, "demo", "002_parties.sql", sql)
    assert [f["issue"] for f in C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel])] != []


def test_keeper_passes_the_real_commerce_organ_migrations():
    from tools.noctus.dev import compliance as C

    paths = sorted(p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "products" / "commerce" / "backend" / "migrations").glob("*.sql"))
    assert C.check_migration_guard_has_probe(repo_root=REPO_ROOT, paths=paths) == []
