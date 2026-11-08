"""Regression tests for ``compliance.check_storage_service_only_policy`` (Leg D of the storage-bucket gate).

THE INCIDENT (2026-11-07): the finance organ rendered four ``finance-attachments_storage_*`` policies
``TO authenticated`` into ~10 hosts, so any org member could read/overwrite/delete the org's invoices straight
through the Supabase storage API. The keeper replays each product's migration chain and judges the policies
still ALIVE at the end (immutable history keeps the original CREATE lines forever).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev.compliance import REPO_ROOT, check_storage_service_only_policy  # noqa: E402

BUCKET = "finance-attachments"
OPEN_SELECT = (
    f'CREATE POLICY "{BUCKET}_storage_select" ON storage.objects FOR SELECT TO authenticated\n'
    f"  USING (bucket_id = '{BUCKET}' AND (storage.foldername(name))[1] = 'x');\n"
)
DROP_SELECT = f'DROP POLICY IF EXISTS "{BUCKET}_storage_select" ON storage.objects;\n'
SERVICE = (
    f'CREATE POLICY "{BUCKET}_storage_service" ON storage.objects FOR ALL TO service_role\n'
    f"  USING (bucket_id = '{BUCKET}') WITH CHECK (bucket_id = '{BUCKET}');\n"
)


def _chain(tmp_path: Path, files: dict[str, str], product: str = "p") -> Path:
    d = tmp_path / "products" / product / "backend" / "migrations"
    d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(body)
    return tmp_path


def test_open_authenticated_policy_is_flagged(tmp_path):
    root = _chain(tmp_path, {"001_f.sql": OPEN_SELECT})
    out = check_storage_service_only_policy(repo_root=root)
    assert len(out) == 1 and out[0]["severity"] == "critical"
    assert "finance-attachments_storage_select" in out[0]["issue"]


def test_later_drop_closes_it_even_though_history_keeps_the_create(tmp_path):
    root = _chain(tmp_path, {"001_f.sql": OPEN_SELECT, "002_close.sql": DROP_SELECT + SERVICE})
    assert check_storage_service_only_policy(repo_root=root) == []


def test_numeric_order_not_lexical(tmp_path):
    # 9 < 10 numerically: the drop in 10_ comes AFTER the create in 9_.
    root = _chain(tmp_path, {"9_f.sql": OPEN_SELECT, "10_close.sql": DROP_SELECT})
    assert check_storage_service_only_policy(repo_root=root) == []


def test_recreate_after_drop_is_flagged(tmp_path):
    root = _chain(tmp_path, {"001.sql": OPEN_SELECT, "002.sql": DROP_SELECT, "003.sql": OPEN_SELECT})
    assert len(check_storage_service_only_policy(repo_root=root)) == 1


def test_anon_and_no_to_clause_are_flagged(tmp_path):
    anon = OPEN_SELECT.replace("TO authenticated", "TO anon").replace("_select", "_anon")
    bare = f"CREATE POLICY \"{BUCKET}_storage_bare\" ON storage.objects FOR SELECT USING (bucket_id = '{BUCKET}');\n"
    root = _chain(tmp_path, {"001.sql": anon + bare})
    assert len(check_storage_service_only_policy(repo_root=root)) == 2


def test_service_role_policy_and_other_buckets_are_clean(tmp_path):
    other = "CREATE POLICY \"docs_storage_select\" ON storage.objects FOR SELECT TO authenticated USING (bucket_id = 'docs');\n"
    root = _chain(tmp_path, {"001.sql": SERVICE + other})
    assert check_storage_service_only_policy(repo_root=root) == []


def test_commented_out_policy_is_ignored(tmp_path):
    root = _chain(tmp_path, {"001.sql": "-- " + OPEN_SELECT.replace("\n", "\n-- ") + "\n" + SERVICE})
    assert check_storage_service_only_policy(repo_root=root) == []


def test_paths_scope_selects_chains(tmp_path):
    root = _chain(tmp_path, {"001.sql": OPEN_SELECT}, product="a")
    _chain(tmp_path, {"001.sql": OPEN_SELECT}, product="b")
    out = check_storage_service_only_policy(repo_root=root, paths=["products/a/backend/migrations/001.sql"])
    assert [f["file"] for f in out] == ["products/a/backend/migrations/001.sql"]


def test_real_tree_has_no_browser_policy_on_a_service_only_bucket():
    assert check_storage_service_only_policy(repo_root=REPO_ROOT) == []
