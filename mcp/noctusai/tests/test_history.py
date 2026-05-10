"""Tests for the `noctus.dev.history_record` MCP tool.

Coverage:
- Pydantic record-shape validation.
- Append-not-overwrite (ledger grows by one line per call).
- NDJSON append-only discipline — re-stamping appends, no dedupe.
- Tokenizer called per file (counted via the shared helper).
- Missing improvements.md / empty proposals/ tolerated.
- Status / scope validation.
- MCP tool registered on the server.

Imports follow the test_archive.py convention.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.history import (
    HistoryRecord,
    history_record,
    _approximate_code_tokens,
    _CODE_TOKEN_PER_LINE_HEURISTIC,
    _SHORTSTAT_RE,
    _gather_phases,
    _git_short_stat_for_slug,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A tmp git repo shaped like noc's project tree."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    # Ledger dir
    (tmp_path / "project-history").mkdir()
    (tmp_path / "projects").mkdir()
    # Initial empty commit so log doesn't fail
    (tmp_path / ".gitkeep").touch()
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)
    return tmp_path


def _make_project(
    repo: Path,
    slug: str,
    with_improvements: bool = True,
    with_proposals: bool = True,
    project_body: str | None = None,
) -> Path:
    """Build a project folder and commit it with the slug in the message."""
    proj = repo / "projects" / slug
    proj.mkdir(parents=True)
    body = project_body or (
        f"# {slug}\n\n## §6 Phases\n\n"
        "Phase 0 — Scaffold ✅\nPhase 1 — Schema + writer\n"
    )
    (proj / "PROJECT.md").write_text(body)
    if with_improvements:
        (proj / "improvements.md").write_text(
            f"# Improvements for {slug}\n\n- improved a thing\n- improved another thing\n"
        )
    if with_proposals:
        (proj / "proposals").mkdir()
        (proj / "proposals" / "001-foo.md").write_text("# Proposal 1\n\nFoo proposal content.\n")
        (proj / "proposals" / "002-bar.md").write_text("# Proposal 2\n\nBar proposal content.\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"file {slug}: scaffold"], cwd=str(repo), check=True)
    return proj


# ---------------------------------------------------------------------------
# Pydantic record shape
# ---------------------------------------------------------------------------


class TestRecordShape:
    def test_minimal_record_validates(self):
        rec = HistoryRecord(
            slug="foo",
            scope="cross-product",
            status_at_close="shipped",
            dates={"created": "2026-05-01", "closed": "2026-05-10"},
            short_summary="A short summary.",
            short_review="- step 1\n- step 2",
            token_count={"total": 100, "tokenizer_used": "tiktoken-cl100k_base"},
        )
        assert rec.slug == "foo"
        assert rec.token_count.total == 100
        assert rec.outcome_signals == []
        assert rec.phases == []

    def test_full_record_round_trips_json(self):
        rec = HistoryRecord(
            slug="bar",
            scope="single-product",
            status_at_close="shipped",
            dates={"closed": "2026-05-10"},
            phases=[{"name": "Phase 0", "status": "shipped", "tokens": 50}],
            short_summary="x",
            short_review="y",
            token_count={
                "project_doc_tokens": 10,
                "improvements_tokens": 5,
                "proposals_tokens": 3,
                "code_delta_tokens": 80,
                "total": 98,
                "tokenizer_used": "tiktoken-cl100k_base",
            },
            outcome_signals=["pytest green"],
        )
        as_dict = rec.model_dump()
        # Round-trip through JSON ensures NDJSON-friendliness.
        roundtripped = HistoryRecord.model_validate_json(json.dumps(as_dict))
        assert roundtripped == rec

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            HistoryRecord(
                slug="x",
                scope="cross-product",
                status_at_close="shipped",
                dates={"closed": "2026-05-10"},
                short_summary="s",
                short_review="r",
                token_count={"total": 1},
                unknown_field="oops",  # noqa: # extra=forbid
            )


# ---------------------------------------------------------------------------
# Status / scope validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_status_raises(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        with pytest.raises(ValueError, match="invalid status_at_close"):
            history_record(
                project_path="projects/alpha",
                status_at_close="not-a-status",
                summary_md="s",
                review_md="r",
                repo_root=tmp_repo,
            )

    def test_invalid_scope_raises(self, tmp_repo):
        _make_project(tmp_repo, "beta")
        with pytest.raises(ValueError, match="invalid scope"):
            history_record(
                project_path="projects/beta",
                status_at_close="shipped",
                summary_md="s",
                review_md="r",
                scope="not-a-scope",
                repo_root=tmp_repo,
            )

    def test_missing_project_raises(self, tmp_repo):
        with pytest.raises(ValueError, match="project path does not exist"):
            history_record(
                project_path="projects/no-such-project",
                status_at_close="shipped",
                summary_md="s",
                review_md="r",
                repo_root=tmp_repo,
            )

    def test_missing_PROJECT_md_raises(self, tmp_repo):
        (tmp_repo / "projects" / "naked").mkdir()
        with pytest.raises(ValueError, match="no PROJECT.md"):
            history_record(
                project_path="projects/naked",
                status_at_close="shipped",
                summary_md="s",
                review_md="r",
                repo_root=tmp_repo,
            )

    def test_accepts_PROJECT_md_path_directly(self, tmp_repo):
        _make_project(tmp_repo, "delta")
        result = history_record(
            project_path="projects/delta/PROJECT.md",
            status_at_close="shipped",
            summary_md="s",
            review_md="r",
            repo_root=tmp_repo,
        )
        assert result["record"]["slug"] == "delta"


# ---------------------------------------------------------------------------
# Append-not-overwrite + idempotency
# ---------------------------------------------------------------------------


class TestAppendOnly:
    def test_first_call_creates_one_line(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="Alpha shipped.",
            review_md="- did stuff",
            repo_root=tmp_repo,
        )
        assert result["line_count"] == 1
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert ledger.exists()
        content = ledger.read_text(encoding="utf-8")
        assert content.count("\n") == 1
        # Each line is valid JSON
        rec = json.loads(content.strip())
        assert rec["slug"] == "alpha"

    def test_second_call_appends_does_not_overwrite(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="first",
            review_md="r",
            repo_root=tmp_repo,
        )
        result2 = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="second",
            review_md="r",
            repo_root=tmp_repo,
        )
        # Append-only: re-stamping the same project appends a new line.
        assert result2["line_count"] == 2
        ledger_lines = (tmp_repo / "project-history" / "ledger.ndjson").read_text().strip().splitlines()
        assert len(ledger_lines) == 2
        recs = [json.loads(L) for L in ledger_lines]
        assert recs[0]["short_summary"] == "first"
        assert recs[1]["short_summary"] == "second"

    def test_different_projects_share_ledger(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        _make_project(tmp_repo, "beta")
        history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="a", review_md="r",
            repo_root=tmp_repo,
        )
        r2 = history_record(
            project_path="projects/beta",
            status_at_close="shipped",
            summary_md="b", review_md="r",
            repo_root=tmp_repo,
        )
        assert r2["line_count"] == 2
        lines = (tmp_repo / "project-history" / "ledger.ndjson").read_text().strip().splitlines()
        slugs = [json.loads(L)["slug"] for L in lines]
        assert slugs == ["alpha", "beta"]

    def test_each_line_is_self_contained_json(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="a", review_md="r",
            repo_root=tmp_repo,
        )
        history_record(
            project_path="projects/alpha",
            status_at_close="abandoned",
            summary_md="b", review_md="r",
            repo_root=tmp_repo,
        )
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        for line in ledger.read_text().strip().splitlines():
            # Each line must parse independently — no multi-line records.
            assert json.loads(line) is not None
            assert "\n" not in line


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


class TestTokenCounting:
    def test_tokens_populated_from_files(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
        )
        tc = result["record"]["token_count"]
        # PROJECT.md has body, improvements.md exists, two proposals exist.
        assert tc["project_doc_tokens"] > 0
        assert tc["improvements_tokens"] > 0
        assert tc["proposals_tokens"] > 0
        assert tc["total"] >= (
            tc["project_doc_tokens"]
            + tc["improvements_tokens"]
            + tc["proposals_tokens"]
        )
        # Tokenizer label must be recorded for cost-efficiency comparisons.
        assert tc["tokenizer_used"]

    def test_missing_improvements_yields_zero(self, tmp_repo):
        _make_project(tmp_repo, "skinny", with_improvements=False, with_proposals=False)
        result = history_record(
            project_path="projects/skinny",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
        )
        tc = result["record"]["token_count"]
        assert tc["improvements_tokens"] == 0
        assert tc["proposals_tokens"] == 0
        assert tc["project_doc_tokens"] > 0  # PROJECT.md still counted

    def test_tokenizer_helper_invoked_per_input(self, tmp_repo):
        """N-call assertion — every file with content goes through the
        shared helper at `tools._tokens.count_tokens_in_text`.

        We patch the symbol where `history.py` imported it from (the
        function alias in the history module's namespace), not the
        helper module itself — both are valid; this matches the
        idiomatic 'patch where it is used' pytest pattern. We don't
        patch our own internal guards (per the no-monkey-patching-of-
        our-own-code rule) — `count_tokens_in_text` is a leaf helper
        with no guards downstream of it; patching to count invocations
        is a legitimate mock-the-IO-boundary pattern.
        """
        _make_project(tmp_repo, "alpha")
        # Side-effect mock that still returns a sane value so the rest
        # of the code path runs realistically.
        with patch(
            "tools.noctus.dev.history.count_tokens_in_text",
            return_value=(42, "tiktoken-cl100k_base"),
        ) as mocked:
            history_record(
                project_path="projects/alpha",
                status_at_close="shipped",
                summary_md="s", review_md="r",
                repo_root=tmp_repo,
            )
        # PROJECT.md + improvements.md + 2 proposals = 4 calls.
        # (project body is non-empty; improvements non-empty; both
        #  proposals non-empty in _make_project.)
        assert mocked.call_count == 4

    def test_code_delta_tokens_from_git_log(self, tmp_repo):
        """When the slug appears in commit messages, code_delta_tokens > 0."""
        _make_project(tmp_repo, "shipping")
        result = history_record(
            project_path="projects/shipping",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
        )
        # _make_project committed with message "file shipping: scaffold"
        # which contains the slug; insertions > 0.
        tc = result["record"]["token_count"]
        assert tc["code_delta_tokens"] > 0


# ---------------------------------------------------------------------------
# Phase extraction
# ---------------------------------------------------------------------------


class TestPhaseExtraction:
    def test_phases_extracted_from_review(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        review = (
            "- Phase 0 — Scaffold ✅\n"
            "- Phase 1 — Schema ✅\n"
            "- Phase 2 — Renderer (next session)\n"
        )
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s", review_md=review,
            repo_root=tmp_repo,
        )
        phases = result["record"]["phases"]
        assert len(phases) == 3
        assert "Phase 0" in phases[0]["name"]
        assert "Scaffold" in phases[0]["name"]

    def test_explicit_phases_override_extraction(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s",
            review_md="- Phase 0 — would-be-extracted",
            phases=[{"name": "Custom phase", "status": "shipped", "tokens": 999}],
            repo_root=tmp_repo,
        )
        phases = result["record"]["phases"]
        assert len(phases) == 1
        assert phases[0]["name"] == "Custom phase"
        assert phases[0]["tokens"] == 999

    def test_gather_phases_unit(self):
        phases = _gather_phases("Phase 1 — Foo ✅\n## Phase 2: Bar")
        names = [p.name for p in phases]
        assert any("Phase 1" in n for n in names)
        assert any("Phase 2" in n for n in names)


# ---------------------------------------------------------------------------
# Scope inference
# ---------------------------------------------------------------------------


class TestScopeInference:
    def test_cross_product_default(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
        )
        assert result["record"]["scope"] == "cross-product"

    def test_single_product_from_path(self, tmp_repo):
        # products/<x>/projects/<slug>/PROJECT.md
        proj_dir = tmp_repo / "products" / "pf" / "projects" / "in-product"
        proj_dir.mkdir(parents=True)
        (proj_dir / "PROJECT.md").write_text("# in-product\n")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "file in-product"], cwd=str(tmp_repo), check=True)
        result = history_record(
            project_path="products/pf/projects/in-product",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
        )
        assert result["record"]["scope"] == "single-product"

    def test_explicit_scope_overrides_inference(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            scope="platform-infra",
            repo_root=tmp_repo,
        )
        assert result["record"]["scope"] == "platform-infra"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestShortStatParsing:
    def test_regex_matches_full_line(self):
        line = " 3 files changed, 42 insertions(+), 7 deletions(-)"
        m = _SHORTSTAT_RE.search(line)
        assert m is not None
        assert int(m.group(1)) == 3
        assert int(m.group(2)) == 42
        assert int(m.group(3)) == 7

    def test_regex_matches_insertions_only(self):
        line = " 1 file changed, 10 insertions(+)"
        m = _SHORTSTAT_RE.search(line)
        assert m is not None
        assert int(m.group(2)) == 10
        assert m.group(3) is None

    def test_approximate_code_tokens(self):
        assert _approximate_code_tokens(0, 0) == 0
        assert _approximate_code_tokens(10, 0) == 10 * _CODE_TOKEN_PER_LINE_HEURISTIC
        assert _approximate_code_tokens(5, 5) == 10 * _CODE_TOKEN_PER_LINE_HEURISTIC


class TestGitShortStat:
    def test_returns_zero_when_no_match(self, tmp_repo):
        ins, dele = _git_short_stat_for_slug("never-existed", tmp_repo)
        assert (ins, dele) == (0, 0)

    def test_counts_for_real_slug(self, tmp_repo):
        _make_project(tmp_repo, "shipping")
        ins, dele = _git_short_stat_for_slug("shipping", tmp_repo)
        assert ins > 0


# ---------------------------------------------------------------------------
# Custom ledger path (test isolation)
# ---------------------------------------------------------------------------


class TestCustomLedgerPath:
    def test_ledger_path_override(self, tmp_repo, tmp_path):
        _make_project(tmp_repo, "alpha")
        custom = tmp_path / "elsewhere" / "my-ledger.ndjson"
        result = history_record(
            project_path="projects/alpha",
            status_at_close="shipped",
            summary_md="s", review_md="r",
            repo_root=tmp_repo,
            ledger_path=custom,
        )
        assert custom.exists()
        assert result["line_count"] == 1


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


class TestMcpRegistration:
    def test_register_function_exists(self):
        from tools.noctus.dev.history import register
        assert callable(register)

    def test_history_record_tool_in_server_registry(self):
        from server import build_server
        s = build_server()
        manager = s._tool_manager
        assert "noctus.dev.history_record" in manager._tools
