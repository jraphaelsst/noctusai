"""``check_card_hub_service_only``: a seed card-hub table must not stay reachable by authenticated/anon (security triage 2026-11-07)."""
import tempfile
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev.compliance import check_card_hub_service_only

_TABLES = ("notas", "documentos", "documento_acessos", "tags")
_CREATE = "\n".join(f"CREATE TABLE IF NOT EXISTS crm.lead_{t} (id uuid);" for t in _TABLES)


def _repo(**files: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="card_hub_gate_"))
    mig = tmp / "products" / "p" / "backend" / "migrations"
    mig.mkdir(parents=True)
    for name, sql in files.items():
        (mig / f"{name}.sql").write_text(sql)
    return tmp


def _bad(issues):
    return sorted(i["issue"].split("`")[1] for i in issues)


def test_hub_table_with_no_revoke_is_flagged():
    assert _bad(check_card_hub_service_only(_repo(**{"001_hub": _CREATE}))) == [
        "crm.lead_documento_acessos", "crm.lead_documentos", "crm.lead_notas", "crm.lead_tags"]


def test_explicit_revoke_clears_it():
    revoke = "\n".join(f"REVOKE ALL ON TABLE crm.lead_{t} FROM PUBLIC, anon, authenticated;" for t in _TABLES)
    assert check_card_hub_service_only(_repo(**{"001_hub": _CREATE, "002_lock": revoke})) == []


def test_revoke_from_authenticated_only_does_not_clear_anon():
    revoke = "\n".join(f"REVOKE ALL ON TABLE crm.lead_{t} FROM authenticated;" for t in _TABLES)
    assert check_card_hub_service_only(_repo(**{"001_hub": _CREATE, "002_lock": revoke}))


def test_policy_alone_is_not_a_revoke():
    pol = 'CREATE POLICY "x" ON crm.lead_notas FOR SELECT TO authenticated USING (true);'
    assert check_card_hub_service_only(_repo(**{"001_hub": _CREATE + pol}))


def test_blanket_all_tables_revoke_clears_it():
    lock = "REVOKE ALL ON ALL TABLES IN SCHEMA crm FROM PUBLIC, anon, authenticated;"
    assert check_card_hub_service_only(_repo(**{"001_hub": _CREATE, "002_lock": lock})) == []


def test_dynamic_loop_revoke_clears_it_igig_044_shape():
    lock = "DO $x$ BEGIN EXECUTE format('REVOKE ALL ON crm.%I FROM PUBLIC, anon, authenticated', r.relname); END $x$;"
    assert check_card_hub_service_only(_repo(**{"001_hub": _CREATE, "002_lock": lock})) == []


def test_default_privileges_revoke_makes_new_tables_born_private():
    lock = "ALTER DEFAULT PRIVILEGES IN SCHEMA crm REVOKE ALL ON TABLES FROM anon, authenticated;"
    assert check_card_hub_service_only(_repo(**{"000_dp": lock, "001_hub": _CREATE})) == []


def test_later_grant_re_exposes():
    revoke = "REVOKE ALL ON ALL TABLES IN SCHEMA crm FROM PUBLIC, anon, authenticated;"
    regrant = "GRANT SELECT ON TABLE crm.lead_notas TO authenticated;"
    assert _bad(check_card_hub_service_only(_repo(**{"001_hub": _CREATE, "002_lock": revoke, "003_g": regrant}))) == ["crm.lead_notas"]


def test_a_lone_notas_table_is_not_a_card_hub():
    assert check_card_hub_service_only(_repo(**{"001_x": "CREATE TABLE crm.acme_notas (id uuid);"})) == []


def test_paths_limit_the_report_to_touched_tables():
    repo = _repo(**{"001_hub": _CREATE, "002_other": "CREATE TABLE crm.unrelated (id uuid);"})
    rel = "products/p/backend/migrations/002_other.sql"
    assert check_card_hub_service_only(repo, [rel]) == []
    assert check_card_hub_service_only(repo, ["products/p/backend/migrations/001_hub.sql"])


def test_real_repo_hub_tables_exposure_is_only_whats_pending_lockdown():
    """Social-wiring's cliente_* hub is locked by 328 (enqueued); everything else -- igig 044, esteira 330 -- is clean."""
    bad = {t.split(".")[0] for t in _bad(check_card_hub_service_only(REPO_ROOT))}
    assert bad <= {"social_wiring"}
