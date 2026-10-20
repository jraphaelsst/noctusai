"""`doc_staleness` -- the deterministic doc-staleness gate (owner order 2026-10-19).

Pins: the coupling rule (+ the `Docs-Reviewed:` trailer ack), the claim
resolver, the shrink-only ratchet, and that the gate catches the three real
staleness examples that slipped through that day (agents README/MASTER-PROMPT
"scaffold only", the 02-LANDSCAPE agents row missing a new studio agent, the
maya-blocks CONTRACT "nothing implemented yet" + "NOT applied").

-> KB § PATTERNS/common/doc-staleness-gate.md
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import doc_staleness as ds  # noqa: E402

ROUTES = "\n".join(f'@router.get("/r{i}")\ndef r{i}(): ...' for i in range(5))


def _git(root: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _commit(root: Path, msg: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _write(r, "products/acme/README.md", "# acme\n\nLive product.\n")
    _write(r, "products/acme/backend/app/routers/a.py", "@router.get('/a')\ndef a(): ...\n")
    _write(r, "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", "| acme | `products/acme/` |\n")
    _commit(r, "base")
    return r


# ── coupling ────────────────────────────────────────────────────────────────
def test_contract_citing_its_product_root_does_not_cover_the_whole_product(repo):
    _write(repo, "products/acme/backend/app/services/b.py", "x = 1\n")
    _write(repo, "products/acme/projects/p/CONTRACT.md",
           "Paths are relative to `products/acme/`.\n\nThe service `backend/app/services/b.py`.\n")
    cov = ds.doc_coverage(repo, ds.Doc(rel="products/acme/projects/p/CONTRACT.md",
                                       text=(repo / "products/acme/projects/p/CONTRACT.md").read_text()))
    assert "products/acme/**" not in cov
    assert cov == ["products/acme/backend/app/services/b.py"]  # the relative citation, resolved


def test_contract_relative_citation_that_is_not_built_is_not_a_cover(repo):
    doc = ds.Doc(rel="products/acme/projects/p/CONTRACT.md",
                 text="Paths are relative to `products/acme/`.\n`backend/app/services/nao_existe.py`\n")
    assert ds.doc_coverage(repo, doc) == []


def test_contract_without_a_declared_base_ignores_relative_tokens(repo):
    _write(repo, "products/acme/backend/app/services/b.py", "x = 1\n")
    doc = ds.Doc(rel="products/acme/projects/p/CONTRACT.md", text="`backend/app/services/b.py`\n")
    assert ds.doc_coverage(repo, doc) == []


def test_new_route_without_doc_fails_and_names_the_doc(repo):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "products/acme/backend/app/routers/b.py", "@router.post('/b')\ndef b(): ...\n")
    tip = _commit(repo, "feat(acme): add b")
    issues = ds.check_range(repo, f"{base}..{tip}")
    docs = {i["doc"] for i in issues}
    assert "products/acme/README.md" in docs
    assert "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md" in docs  # new router module -> roster rule


def test_touching_the_doc_in_range_satisfies_it(repo):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "products/acme/backend/app/routers/b.py", "@router.post('/b')\ndef b(): ...\n")
    _write(repo, "products/acme/README.md", "# acme\n\nNow has /b.\n")
    _write(repo, "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", "| acme | `products/acme/` b |\n")
    tip = _commit(repo, "feat(acme): add b")
    assert ds.check_range(repo, f"{base}..{tip}") == []


def test_trailer_acknowledges_with_reason_only(repo):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "products/acme/backend/app/routers/a.py", "@router.get('/a')\ndef a(): ...\n@router.get('/a2')\ndef a2(): ...\n")
    tip = _commit(repo, "feat(acme): a2\n\nDocs-Reviewed: products/acme/README.md — endpoint is internal, README lists none")
    assert ds.check_range(repo, f"{base}..{tip}") == []
    # reasonless trailer does not count
    _write(repo, "products/acme/backend/app/routers/a.py", "@router.get('/a')\ndef a(): ...\n@router.get('/a3')\ndef a3(): ...\n")
    tip2 = _commit(repo, "feat(acme): a3\n\nDocs-Reviewed: products/acme/README.md")
    assert [i["doc"] for i in ds.check_range(repo, f"{tip}..{tip2}")] == ["products/acme/README.md"]


def test_non_material_edits_do_not_fire(repo):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "products/acme/backend/app/routers/a.py", "@router.get('/a')\ndef a():\n    return 1  # body only\n")
    _write(repo, "products/acme/backend/tests/test_a.py", "def test_x(): ...\n")
    tip = _commit(repo, "fix(acme): body tweak")
    assert ds.check_range(repo, f"{base}..{tip}") == []


def test_frontmatter_covers_declares_coverage(repo):
    _write(repo, "KNOWLEDGE-BASE/CONTEXT/pat.md", "---\ncovers: [seed/lib/**]\n---\n# pat\n")
    base = _commit(repo, "kb pat")
    _write(repo, "seed/lib/y.py", "class Gadget: ...\n")
    tip = _commit(repo, "feat(seed): gadget")
    assert {i["doc"] for i in ds.check_range(repo, f"{base}..{tip}")} == {"KNOWLEDGE-BASE/CONTEXT/pat.md"}


def test_bad_range_fails_closed(repo):
    assert ds.check_range(repo, "nope")[0]["severity"] == "high"
    assert "fail-closed" in ds.check_range(repo, "deadbeef..cafebabe")[0]["issue"]


def test_parse_covers_inline_and_list():
    assert ds.parse_covers("---\ncovers: [a/**, b.py]\n---\nx") == ["a/**", "b.py"]
    assert ds.parse_covers("---\ncovers:\n  - a/**\n  - 'b.py'\n---\nx") == ["a/**", "b.py"]
    assert ds.parse_covers("no frontmatter") == []


# ── claims: the three real examples ─────────────────────────────────────────
def test_example_agents_scaffold_only_vs_live_routes(repo):
    _write(repo, "products/acme/backend/app/routers/many.py", ROUTES)
    _write(repo, "products/acme/MASTER-PROMPT.md", "**Status (2026-09-14):** scaffold only. Every domain item below is PLANNED.\n")
    _write(repo, "products/acme/README.md", "> **Status:** scaffolded. Domain code is planned, not built.\n")
    _commit(repo, "docs")
    kinds = {(f["kind"], f["doc"]) for f in ds.check_claims(repo)}
    assert ("status_contradiction", "products/acme/MASTER-PROMPT.md") in kinds
    assert ("status_contradiction", "products/acme/README.md") in kinds


def test_scaffold_claim_is_fine_while_product_really_is_a_scaffold(repo):
    _write(repo, "products/acme/MASTER-PROMPT.md", "scaffold only.\n")
    _commit(repo, "docs")
    assert [f for f in ds.check_claims(repo) if f["kind"] == "status_contradiction"] == []


def test_example_contract_nothing_implemented_and_migration_not_applied(repo):
    _write(repo, "products/acme/backend/migrations/286_blocos.sql", "-- m\n")
    _write(repo, "products/acme/backend/migrations-applied.json", json.dumps({"applied": {"286_blocos.sql": "x"}}))
    _write(repo, "products/acme/backend/app/svc/one.py", "x=1\n")
    _write(repo, "products/acme/backend/app/svc/two.py", "x=1\n")
    _write(repo, "products/acme/projects/blocks/CONTRACT.md", (
        "Schema = `products/acme/backend/migrations/286_blocos.sql` (NOT applied).\n"
        "See `products/acme/backend/app/svc/one.py` and `products/acme/backend/app/svc/two.py`.\n"
        "Everything below is the contract; nothing is implemented yet.\n"))
    _commit(repo, "contract")
    found = {(f["kind"], f["doc"]) for f in ds.check_claims(repo)}
    assert ("status_contradiction", "products/acme/projects/blocks/CONTRACT.md") in found
    assert ("migration_state", "products/acme/projects/blocks/CONTRACT.md") in found


def test_unapplied_migration_claim_is_true_when_not_in_ledger(repo):
    _write(repo, "products/acme/backend/migrations-applied.json", json.dumps({"applied": {}}))
    _write(repo, "products/acme/projects/blocks/CONTRACT.md", "`286_blocos.sql` is NOT applied.\n")
    _commit(repo, "c")
    assert [f for f in ds.check_claims(repo) if f["kind"] == "migration_state"] == []


# ── claims: path resolver ───────────────────────────────────────────────────
def test_missing_cited_path_flags_and_existing_or_placeholder_does_not(repo):
    _write(repo, "products/acme/README.md", (
        "See `products/acme/backend/app/routers/a.py` (exists), `products/acme/backend/app/gone.py` (gone), "
        "`products/<slug>/x.py` and `products/*/y.py` (placeholders).\n"))
    _commit(repo, "d")
    miss = [f for f in ds.check_claims(repo) if f["kind"] == "missing_path"]
    assert [f["id"] for f in miss] == ["missing_path::products/acme/README.md::products/acme/backend/app/gone.py"]


def test_project_docs_may_cite_unbuilt_paths(repo):
    _write(repo, "products/acme/projects/p/PROJECT.md", "Will add `products/acme/backend/app/future.py`.\n")
    _commit(repo, "d")
    assert [f for f in ds.check_claims(repo) if f["kind"] == "missing_path"] == []


# ── ratchet ─────────────────────────────────────────────────────────────────
def test_ratchet_only_new_staleness_fails_and_shrink_never_grows(repo):
    _write(repo, "products/acme/README.md", "`products/acme/old.py`\n")
    _commit(repo, "d")
    assert ds.write_baseline(repo, ds.check_claims(repo), "init")["entries"] == 1
    assert ds.write_baseline(repo, ds.check_claims(repo), "init")["ok"] is False  # init once
    assert ds.check_tree(repo)["new"] == []
    _write(repo, "products/acme/MASTER-PROMPT.md", "`products/acme/also_gone.py`\n")
    _commit(repo, "d2")
    new = ds.check_tree(repo)["new"]
    assert [f["doc"] for f in new] == ["products/acme/MASTER-PROMPT.md"]
    # shrink drops fixed entries but does not adopt the new one
    _write(repo, "products/acme/README.md", "fixed\n")
    _commit(repo, "d3")
    r = ds.write_baseline(repo, ds.check_claims(repo), "shrink")
    assert r["entries"] == 0 and r["dropped"] == 1
    assert [f["doc"] for f in ds.check_tree(repo)["new"]] == ["products/acme/MASTER-PROMPT.md"]


class TestCheckDocStaleness:
    """Regression tests for the `check_doc_staleness` keeper (compliance wrapper)."""

    def test_keeper_wrapper_issue_shape(self, repo):
        _write(repo, "products/acme/README.md", "`products/acme/old.py`\n")
        _commit(repo, "d")
        from tools.noctus.dev.compliance import check_doc_staleness
        issues = check_doc_staleness(repo_root=repo)
        assert issues and set(issues[0]) >= {"product", "file", "issue", "severity"}

    def test_keeper_range_mode_is_coupling(self, repo):
        base = _git(repo, "rev-parse", "HEAD")
        _write(repo, "products/acme/backend/app/routers/b.py", "@router.post('/b')\ndef b(): ...\n")
        tip = _commit(repo, "feat(acme): b")
        from tools.noctus.dev.compliance import check_doc_staleness
        files = {i["file"] for i in check_doc_staleness(repo_root=repo, rev_range=f"{base}..{tip}")}
        assert "products/acme/README.md" in files

    def test_committed_baseline_is_loaded_and_live_tree_holds_it(self):
        """The REAL baseline file is read explicitly; the live tree may not exceed it."""
        from settings import REPO_ROOT
        baseline_path = REPO_ROOT / ds.BASELINE_REL
        assert baseline_path.is_file()
        entries = json.loads(baseline_path.read_text(encoding="utf-8"))["entries"]
        assert entries == ds.load_baseline(REPO_ROOT)
        findings = ds.check_claims(REPO_ROOT)  # claims only: no git-log age scan
        new = [f for f in findings if f["id"] not in entries]
        assert new == [], "new doc staleness (fix the doc, never grow the baseline):\n" + ds.suggest({"new": new})
