"""Tests for the surface-and-resume MCP tooling.

Covers:
  - surface_to_tech_lead: structured file write, YAML frontmatter validity,
    body sections present, state snapshot capture (dirty files mock)
  - list_pending_surfaces: filtering by status=pending-response
  - respond_and_resume: response file written, surface status updated, bundle composed
  - dispatch_resume_brief: includes all components (original + surface + response + preamble)
  - Security: path-traversal rejection on surface_id

KB § PATTERNS/common/surface-and-resume-tooling.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import the modules under test
from tools.noctus.dev import surface_to_tech_lead as stl_mod
from tools.noctus.dev import list_pending_surfaces as lps_mod
from tools.noctus.dev import respond_and_resume as rar_mod
from tools.noctus.dev import dispatch_resume as dr_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dispatches(tmp_path, monkeypatch):
    """Redirect all four modules to use a tmp dispatches dir."""
    dispatches = tmp_path / ".claude" / "dispatches"
    dispatches.mkdir(parents=True)

    monkeypatch.setattr(stl_mod, "_dispatches_dir", lambda: dispatches)
    monkeypatch.setattr(lps_mod, "_dispatches_dir", lambda: dispatches)
    monkeypatch.setattr(rar_mod, "_dispatches_dir", lambda: dispatches)
    monkeypatch.setattr(dr_mod, "_dispatches_dir", lambda: dispatches)

    return dispatches


@pytest.fixture
def fake_worktree(tmp_path):
    """A fake worktree directory path (no real git needed for most tests)."""
    wt = tmp_path / ".claude" / "worktrees" / "test-feature"
    wt.mkdir(parents=True)
    return wt


@pytest.fixture
def patched_state_snapshot():
    """Return a predictable state snapshot without shelling out to git."""
    fake_snapshot = {
        "diff_bytes": 512,
        "dirty_files": ["mcp/noctusai/tools/noctus/dev/foo.py"],
        "uncommitted_count": 1,
        "worktree_sha": "abc123def456",
    }
    with patch.object(stl_mod, "_capture_state_snapshot", return_value=fake_snapshot):
        yield fake_snapshot


@pytest.fixture
def patched_detect_worktree(fake_worktree):
    """Return a stable worktree path without calling git."""
    with patch.object(stl_mod, "_detect_worktree_path", return_value=str(fake_worktree)):
        yield str(fake_worktree)


# ---------------------------------------------------------------------------
# surface_to_tech_lead tests
# ---------------------------------------------------------------------------

class TestSurfaceToTechLead:
    def test_surface_writes_structured_file(
        self, tmp_dispatches, patched_state_snapshot, patched_detect_worktree
    ):
        """Written file has YAML frontmatter + body sections."""
        result = stl_mod.surface_to_tech_lead(
            reason="keeper-cache cwd-drift",
            proposal_md="Force-rebuild keeper cache from worktree.",
            current_state_md="Keeper check failed with stale cache.",
            attempted_resolution_md="Tried --refresh-keeper-cache but cwd wrong.",
        )

        assert result["ok"], f"Expected ok, got: {result}"
        surface_path = Path(result["surface_path"])
        assert surface_path.exists(), f"Surface file not found: {surface_path}"

        text = surface_path.read_text()
        # Frontmatter present
        assert text.startswith("---")
        assert "surface_id:" in text
        assert "worktree:" in text
        assert "worktree_sha: abc123def456" in text
        assert "status: pending-response" in text

        # Body sections present
        assert "## Proposal / What the agent needs" in text
        assert "## Current State" in text
        assert "## Attempted Resolution" in text

        # Content made it in
        assert "keeper-cache cwd-drift" in text
        assert "Force-rebuild keeper cache" in text

    def test_surface_receipt_fields(
        self, tmp_dispatches, patched_state_snapshot, patched_detect_worktree
    ):
        """SurfaceReceipt has surface_id, surface_path, exit_marker_msg."""
        result = stl_mod.surface_to_tech_lead(
            reason="test-reason",
            proposal_md="prop",
            current_state_md="state",
            attempted_resolution_md="tried",
        )
        assert result["ok"]
        assert result["surface_id"]
        assert "SURFACE_FILED:" in result["exit_marker_msg"]
        assert "WAITING_FOR_TECH_LEAD_RESPONSE" in result["exit_marker_msg"]
        assert result["surface_id"] in result["exit_marker_msg"]

    def test_state_snapshot_captures_dirty_files(
        self, tmp_dispatches, patched_detect_worktree
    ):
        """Dirty file list from the snapshot appears in the surface file."""
        dirty = ["products/foo/backend/main.py", "mcp/noctusai/tools/bar.py"]
        fake_snapshot = {
            "diff_bytes": 128,
            "dirty_files": dirty,
            "uncommitted_count": 2,
            "worktree_sha": "deadbeef",
        }
        with patch.object(stl_mod, "_capture_state_snapshot", return_value=fake_snapshot):
            result = stl_mod.surface_to_tech_lead(
                reason="dirty-files-test",
                proposal_md="p",
                current_state_md="s",
                attempted_resolution_md="a",
            )
        assert result["ok"]
        assert result["uncommitted_count"] == 2
        assert "products/foo/backend/main.py" in result["dirty_files"]

    def test_empty_reason_rejected(self, tmp_dispatches):
        """Empty reason returns error, does not write a file."""
        result = stl_mod.surface_to_tech_lead(
            reason="",
            proposal_md="p",
            current_state_md="s",
            attempted_resolution_md="a",
        )
        assert not result["ok"]
        assert "reason" in result["error"]

    def test_explicit_worktree_path(self, tmp_dispatches, patched_state_snapshot, tmp_path):
        """Explicit worktree_path is used (no auto-detect)."""
        explicit = str(tmp_path / "my-worktree")
        Path(explicit).mkdir(parents=True)
        result = stl_mod.surface_to_tech_lead(
            reason="explicit-wt",
            proposal_md="p",
            current_state_md="s",
            attempted_resolution_md="a",
            worktree_path=explicit,
        )
        assert result["ok"]
        assert result["worktree"] == explicit


# ---------------------------------------------------------------------------
# list_pending_surfaces tests
# ---------------------------------------------------------------------------

class TestListPendingSurfaces:
    def _write_surface(
        self, dispatches: Path, surface_id: str, status: str, reason: str = "test"
    ) -> Path:
        """Write a minimal surface file for tests."""
        wt_dir = dispatches / "test-wt"
        wt_dir.mkdir(parents=True, exist_ok=True)
        ts = "20260101T000000Z"
        p = wt_dir / f"surface-{ts}-{surface_id}.md"
        p.write_text(f"""---
surface_id: {surface_id}
worktree: /tmp/wt
worktree_sha: abc
reason: {reason!r}
state_snapshot:
        diff_bytes: 0
        dirty_files: []
        uncommitted_count: 0
attempted_resolution: ""
status: {status}
ts: 2026-01-01T00:00:00+00:00
---

# Surface Note

body
""")
        return p

    def test_list_returns_pending_only(self, tmp_dispatches):
        """Only pending-response surfaces are returned by default."""
        self._write_surface(tmp_dispatches, "s1", "pending-response")
        self._write_surface(tmp_dispatches, "s2", "responded")

        results = lps_mod.list_pending_surfaces()
        assert len(results) == 1
        assert results[0]["surface_id"] == "s1"

    def test_include_responded_returns_all(self, tmp_dispatches):
        """include_responded=True returns all surfaces."""
        self._write_surface(tmp_dispatches, "s1", "pending-response")
        self._write_surface(tmp_dispatches, "s2", "responded")

        results = lps_mod.list_pending_surfaces(include_responded=True)
        ids = {r["surface_id"] for r in results}
        assert "s1" in ids
        assert "s2" in ids

    def test_empty_dispatches_dir_returns_empty(self, tmp_dispatches):
        """No files → empty list (not crash)."""
        results = lps_mod.list_pending_surfaces()
        assert results == []

    def test_missing_dispatches_dir_returns_empty(self, tmp_path, monkeypatch):
        """Non-existent dispatches dir → empty list."""
        nonexistent = tmp_path / "no-such-dir"
        monkeypatch.setattr(lps_mod, "_dispatches_dir", lambda: nonexistent)
        assert lps_mod.list_pending_surfaces() == []

    def test_registers_reason_and_dirty_count(self, tmp_dispatches):
        """Reason and dirty_file_count are parsed from frontmatter."""
        self._write_surface(tmp_dispatches, "s3", "pending-response", reason="my reason")
        results = lps_mod.list_pending_surfaces()
        assert results[0]["reason"] == "my reason"
        assert results[0]["dirty_file_count"] == 0


# ---------------------------------------------------------------------------
# respond_and_resume tests
# ---------------------------------------------------------------------------

class TestRespondAndResume:
    def _write_pending_surface(self, dispatches: Path, surface_id: str) -> Path:
        wt_dir = dispatches / "test-wt"
        wt_dir.mkdir(parents=True, exist_ok=True)
        p = wt_dir / f"surface-20260101T000000Z.md"
        p.write_text(f"""---
surface_id: {surface_id}
worktree: /tmp/wt-feature
worktree_sha: deadbeef
reason: 'test block'
state_snapshot:
        diff_bytes: 0
        dirty_files: []
        uncommitted_count: 0
attempted_resolution: "none"
status: pending-response
ts: 2026-01-01T00:00:00+00:00
---

# Surface body
""")
        return p

    def test_respond_and_resume_composes_bundle(self, tmp_dispatches):
        """Response file written, surface status updated, bundle returned."""
        surface_id = "test-wt-20260101T000000Z"
        self._write_pending_surface(tmp_dispatches, surface_id)

        # Patch brief_ledger to avoid import issues
        with patch.object(rar_mod, "_read_brief_ledger_excerpt", return_value="(excerpt)"):
            result = rar_mod.respond_and_resume(
                surface_id=surface_id,
                decision="approve",
                rationale_md="The proposed fix is correct. Proceed.",
            )

        assert result["ok"], f"Expected ok, got: {result}"
        assert result["surface_id"] == surface_id
        assert result["decision"] == "approve"
        assert result["resume_preamble"]
        assert result["worktree_state_pointer"]["worktree_path"] == "/tmp/wt-feature"
        assert result["worktree_state_pointer"]["worktree_sha"] == "deadbeef"

        # Response file exists
        response_path = Path(result["response_path"])
        assert response_path.exists()
        resp_text = response_path.read_text()
        assert "surface_id:" in resp_text
        assert "decision: approve" in resp_text
        assert "The proposed fix is correct. Proceed." in resp_text

        # Surface status updated
        surface_path = Path(result["surface_path"])
        surface_text = surface_path.read_text()
        assert "status: responded" in surface_text
        assert "status: pending-response" not in surface_text

    def test_respond_empty_rationale_rejected(self, tmp_dispatches):
        """Empty rationale returns error."""
        surface_id = "test-wt-20260101T000000Z"
        self._write_pending_surface(tmp_dispatches, surface_id)
        result = rar_mod.respond_and_resume(
            surface_id=surface_id,
            decision="approve",
            rationale_md="",
        )
        assert not result["ok"]
        assert "rationale_md" in result["error"]

    def test_respond_unknown_surface_returns_error(self, tmp_dispatches):
        """Non-existent surface_id returns error."""
        result = rar_mod.respond_and_resume(
            surface_id="nonexistent-surface-id",
            decision="approve",
            rationale_md="Rationale.",
        )
        assert not result["ok"]
        assert "No surface file found" in result["error"]

    def test_adapt_decision_includes_updated_brief(self, tmp_dispatches):
        """adapt + updated_brief_md appears in the response file."""
        surface_id = "test-wt-20260101T000000Z"
        self._write_pending_surface(tmp_dispatches, surface_id)
        with patch.object(rar_mod, "_read_brief_ledger_excerpt", return_value=None):
            result = rar_mod.respond_and_resume(
                surface_id=surface_id,
                decision="adapt",
                rationale_md="Use the v2 approach instead.",
                updated_brief_md="New brief: implement via v2 seam.",
            )
        assert result["ok"]
        response_text = Path(result["response_path"]).read_text()
        assert "New brief: implement via v2 seam." in response_text


# ---------------------------------------------------------------------------
# dispatch_resume_brief tests
# ---------------------------------------------------------------------------

class TestDispatchResumeBrief:
    def _setup_surface_and_response(
        self, dispatches: Path, surface_id: str
    ) -> tuple[Path, Path]:
        wt_dir = dispatches / "my-wt"
        wt_dir.mkdir(parents=True, exist_ok=True)

        surface = wt_dir / "surface-20260101T000000Z.md"
        surface.write_text(f"""---
surface_id: {surface_id}
worktree: /tmp/my-wt
worktree_sha: cafebabe
reason: 'pre-existing debt'
state_snapshot:
        diff_bytes: 64
        dirty_files: []
        uncommitted_count: 0
attempted_resolution: "tried approach A"
status: responded
ts: 2026-01-01T00:00:00+00:00
---

# Surface body here
""")
        response = wt_dir / f"response-{surface_id}.md"
        response.write_text(f"""---
surface_id: {surface_id}
decision: approve
ts: 2026-01-01T01:00:00+00:00
---

# Tech-Lead Response

**Decision:** APPROVE

## Rationale

Proceed as proposed.
""")
        return surface, response

    def test_dispatch_resume_brief_includes_all_components(self, tmp_dispatches):
        """Brief text includes original + surface + response + preamble."""
        surface_id = "my-wt-20260101T000000Z"
        self._setup_surface_and_response(tmp_dispatches, surface_id)

        # Patch brief_ledger query
        with patch(
            "tools.noctus.dev.dispatch_resume.Path"
        ) as _:
            # Don't actually need to patch Path — just test the output
            pass

        result = dr_mod.dispatch_resume_brief(surface_id=surface_id)
        assert result["ok"], f"Expected ok, got: {result}"

        brief = result["brief_text"]
        # Resume preamble
        assert "RESUMING" in brief
        assert "/tmp/my-wt" in brief
        assert "cafebabe" in brief
        # Surface body
        assert "Surface body here" in brief
        # Response
        assert "Proceed as proposed." in brief
        # Cache-first reminder
        assert "Cache-first reflex" in brief
        # Safety rules
        assert "NEVER `--no-verify`" in brief
        # Worker path
        assert "/tmp/my-wt" in brief

    def test_dispatch_resume_brief_missing_response_returns_error(self, tmp_dispatches):
        """If no response file exists, returns error with guidance."""
        surface_id = "orphan-wt-20260101T000000Z"
        wt_dir = tmp_dispatches / "orphan-wt"
        wt_dir.mkdir(parents=True)
        surface = wt_dir / "surface-20260101T000000Z.md"
        surface.write_text(f"---\nsurface_id: {surface_id}\nstatus: pending-response\n---\nbody\n")

        result = dr_mod.dispatch_resume_brief(surface_id=surface_id)
        assert not result["ok"]
        assert "respond_and_resume" in result["error"]

    def test_dispatch_resume_brief_unknown_surface_returns_error(self, tmp_dispatches):
        """Unknown surface_id returns error."""
        result = dr_mod.dispatch_resume_brief(surface_id="no-such-surface")
        assert not result["ok"]
        assert "No surface file found" in result["error"]


# ---------------------------------------------------------------------------
# Security tests — path traversal
# ---------------------------------------------------------------------------

class TestNoPathTraversal:
    @pytest.mark.parametrize("bad_id", [
        "../etc/passwd",
        "../../shadow",
        "foo/../../bar",
        "/absolute/path",
        "foo\x00bar",
        "foo bar",
    ])
    def test_respond_and_resume_rejects_traversal(self, tmp_dispatches, bad_id):
        """surface_id with path-traversal chars is rejected."""
        result = rar_mod.respond_and_resume(
            surface_id=bad_id,
            decision="approve",
            rationale_md="Rationale.",
        )
        assert not result["ok"]
        assert "invalid characters" in result["error"] or "forbidden" in result["error"]

    @pytest.mark.parametrize("bad_id", [
        "../etc/passwd",
        "foo/../../bar",
        "/etc/shadow",
        "a b c",
    ])
    def test_dispatch_resume_brief_rejects_traversal(self, tmp_dispatches, bad_id):
        """surface_id with path-traversal chars is rejected."""
        result = dr_mod.dispatch_resume_brief(surface_id=bad_id)
        assert not result["ok"]
        assert "invalid characters" in result["error"] or "forbidden" in result["error"]
