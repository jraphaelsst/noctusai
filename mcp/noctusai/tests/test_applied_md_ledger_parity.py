"""APPLIED.md headings are derived from migrations-applied.json (the ledger is the source of truth)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import applied_md  # noqa: E402
from tools.noctus.dev.compliance import check_applied_md_ledger_parity  # noqa: E402

MD = """# x

## 255 — alpha — NOT APPLIED

Body that says NOT APPLIED in prose and must stay.

```
## 256 — fenced — NOT APPLIED
```

## 256 — beta — NOT APPLIED (waiting on image)

## 257 — gamma — APPLIED (verified 2026-10-13)

## 300 — delta — NOT APPLIED
"""
LEDGER = ["255_alpha.sql", "256_beta.sql", "257_gamma.sql"]


def _product(root: Path, md: str, ledger: list[str]) -> None:
    be = root / "products" / "p" / "backend"
    (be / "migrations").mkdir(parents=True)
    (be / "migrations" / "APPLIED.md").write_text(md)
    (be / "migrations-applied.json").write_text(json.dumps({"applied": {n: "x" for n in ledger}}))


def test_sync_rewrites_only_ledger_headings_and_keeps_body_and_fences():
    new, changed = applied_md.sync_applied_md(MD, LEDGER)
    assert changed == [255, 256]
    assert "## 255 — alpha — APPLIED (recorded in migrations-applied.json)" in new
    assert "## 256 — beta — APPLIED (waiting on image)" in new
    assert "## 256 — fenced — NOT APPLIED" in new  # fenced block untouched
    assert "Body that says NOT APPLIED in prose" in new
    assert "## 300 — delta — NOT APPLIED" in new  # not in ledger: stays


def test_sync_is_idempotent():
    once, _ = applied_md.sync_applied_md(MD, LEDGER)
    twice, changed = applied_md.sync_applied_md(once, LEDGER)
    assert twice == once and changed == []


class TestCheckAppliedMdLedgerParity:
    def test_not_applied_but_in_ledger_is_flagged(self, tmp_path):
        _product(tmp_path, MD, LEDGER)
        issues = check_applied_md_ledger_parity(repo_root=tmp_path)
        assert {i["severity"] for i in issues} == {"high"}
        assert any("255" in i["issue"] for i in issues)

    def test_synced_text_is_clean(self, tmp_path):
        _product(tmp_path, applied_md.sync_applied_md(MD, LEDGER)[0], LEDGER)
        assert check_applied_md_ledger_parity(repo_root=tmp_path) == []

    def test_applied_heading_inside_covered_range_but_absent_is_flagged(self, tmp_path):
        _product(tmp_path, "## 256 — x — APPLIED\n", ["255_a.sql", "257_c.sql"])
        assert len(check_applied_md_ledger_parity(repo_root=tmp_path)) == 1

    def test_applied_heading_below_ledger_floor_is_not_judged(self, tmp_path):
        _product(tmp_path, "## 079 — old — APPLIED\n", ["255_a.sql"])
        assert check_applied_md_ledger_parity(repo_root=tmp_path) == []

    def test_product_without_ledger_is_skipped(self, tmp_path):
        be = tmp_path / "products" / "p" / "backend" / "migrations"
        be.mkdir(parents=True)
        (be / "APPLIED.md").write_text("## 255 — a — NOT APPLIED\n")
        assert check_applied_md_ledger_parity(repo_root=tmp_path) == []

    def test_real_tree_is_clean(self):
        assert check_applied_md_ledger_parity() == []
