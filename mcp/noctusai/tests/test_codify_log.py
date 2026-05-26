"""Tests for `codify_log` — s-stage-enforcing wrapper around auto_improvement.log_entry.

Invariants under test:
- s4-keeper requires preceding s3-codified for same target
- s3-codified requires preceding s1-emergent OR s2-memory for same target
- s1-emergent + s2-memory are entry points (no prereq)
- force=True bypasses the prereq check; the force flag is captured in source_ref
- invalid stages / empty targets / short descriptions are rejected

KB § PATTERNS/common/methodology-codification-pipeline.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import codify


def _write_prereq(ledger_path: Path, target: str, status: str) -> None:
    """Append a prereq entry to the ledger."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": "2026-05-01",
        "agent": "test",
        "scope": "broad",
        "kind": "improvement",
        "target": target,
        "description": "prereq entry for test",
        "status": status,
        "source_ref": "test",
    }
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


@pytest.fixture
def ledger(tmp_path):
    """Per-test isolated ledger path."""
    return tmp_path / "project-history" / "auto-improvement.ndjson"


class TestCodifyLogValidation:
    def test_invalid_stage_rejected(self, ledger):
        result = codify.codify_log(
            stage="s5-imaginary",
            target="x",
            description="some description here yes yes",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert "invalid stage" in result["error"]

    def test_legacy_s3_kb_not_emittable(self, ledger):
        """s3-kb is read-side compat only; emit-side rejects."""
        result = codify.codify_log(
            stage="s3-kb",
            target="x",
            description="some description here yes yes",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert "invalid stage" in result["error"]
        assert "legacy alias" in result["error"]

    def test_empty_target_rejected(self, ledger):
        result = codify.codify_log(
            stage="s1-emergent",
            target="",
            description="some description here yes yes",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert "target cannot be empty" in result["error"]

    def test_whitespace_target_rejected(self, ledger):
        result = codify.codify_log(
            stage="s1-emergent",
            target="   ",
            description="some description here yes yes",
            ledger_path=ledger,
        )
        assert result["ok"] is False

    def test_short_description_rejected(self, ledger):
        result = codify.codify_log(
            stage="s1-emergent",
            target="x",
            description="too short",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert ">= 20 chars" in result["error"]


class TestCodifyLogProgression:
    def test_s1_no_prereq_required(self, ledger):
        result = codify.codify_log(
            stage="s1-emergent",
            target="brand-new-pattern.md",
            description="Just surfaced this pattern emerging in the wild.",
            ledger_path=ledger,
        )
        assert result["ok"] is True
        assert result["entry"]["status"] == "s1-emergent"

    def test_s2_no_prereq_required(self, ledger):
        result = codify.codify_log(
            stage="s2-memory",
            target="brand-new-pattern.md",
            description="Logged in MEMORY.md as a deferred codification candidate.",
            ledger_path=ledger,
        )
        assert result["ok"] is True

    def test_s3_requires_prereq(self, ledger):
        result = codify.codify_log(
            stage="s3-codified",
            target="no-prereq.md",
            description="Tried to codify without prior s1/s2 — should be rejected.",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert "no preceding s1-emergent OR s2-memory" in result["error"]
        assert result["missing_prereq"] == "s1-emergent | s2-memory"

    def test_s3_accepts_after_s1(self, ledger):
        _write_prereq(ledger, "p.md", "s1-emergent")
        result = codify.codify_log(
            stage="s3-codified",
            target="p.md",
            description="Codified after s1 emergence was logged.",
            ledger_path=ledger,
        )
        assert result["ok"] is True

    def test_s3_accepts_after_s2(self, ledger):
        _write_prereq(ledger, "p.md", "s2-memory")
        result = codify.codify_log(
            stage="s3-codified",
            target="p.md",
            description="Codified after s2 memory entry landed.",
            ledger_path=ledger,
        )
        assert result["ok"] is True

    def test_s4_requires_s3(self, ledger):
        result = codify.codify_log(
            stage="s4-keeper",
            target="no-s3.md",
            description="Tried to ship keeper without codifying first.",
            ledger_path=ledger,
        )
        assert result["ok"] is False
        assert "no preceding s3-codified entry" in result["error"]
        assert result["missing_prereq"] == "s3-codified"

    def test_s4_accepts_after_s3_codified(self, ledger):
        _write_prereq(ledger, "p.md", "s3-codified")
        result = codify.codify_log(
            stage="s4-keeper",
            target="p.md",
            description="Keeper landed; KB pattern already exists per s3 entry.",
            ledger_path=ledger,
        )
        assert result["ok"] is True

    def test_s4_accepts_after_legacy_s3_kb(self, ledger):
        """The legacy s3-kb alias still counts as s3-satisfied on read."""
        _write_prereq(ledger, "p.md", "s3-kb")
        result = codify.codify_log(
            stage="s4-keeper",
            target="p.md",
            description="Keeper landed; legacy s3-kb entry counts as prereq.",
            ledger_path=ledger,
        )
        assert result["ok"] is True

    def test_target_isolation(self, ledger):
        """Prereqs are PER-TARGET — s3 for target A doesn't satisfy s4 for target B."""
        _write_prereq(ledger, "target-a.md", "s3-codified")
        result = codify.codify_log(
            stage="s4-keeper",
            target="target-b.md",
            description="Different target — should not benefit from target-a's prereq.",
            ledger_path=ledger,
        )
        assert result["ok"] is False


class TestCodifyLogForce:
    def test_force_bypasses_s3_prereq(self, ledger):
        result = codify.codify_log(
            stage="s3-codified",
            target="backfill.md",
            description="Same-commit s2→s3 compression — legitimate, force=True.",
            source_ref="session:compression",
            force=True,
            ledger_path=ledger,
        )
        assert result["ok"] is True
        # Force flag tagged into source_ref for audit
        assert "force:" in result["entry"]["source_ref"]
        assert "session:compression" in result["entry"]["source_ref"]

    def test_force_bypasses_s4_prereq(self, ledger):
        result = codify.codify_log(
            stage="s4-keeper",
            target="legacy-keeper.py",
            description="Backfill — keeper shipped before s3 entry got logged.",
            source_ref="session:backfill",
            force=True,
            ledger_path=ledger,
        )
        assert result["ok"] is True
        assert "force:" in result["entry"]["source_ref"]

    def test_force_without_source_ref_tagged_as_no_source_ref(self, ledger):
        result = codify.codify_log(
            stage="s4-keeper",
            target="forced.py",
            description="Force without explicit source_ref — still audit-tagged.",
            force=True,
            ledger_path=ledger,
        )
        assert result["ok"] is True
        assert "force:no-source-ref" in result["entry"]["source_ref"]


class TestCodifyLogLedgerIntegration:
    def test_writes_to_ndjson(self, ledger):
        codify.codify_log(
            stage="s2-memory",
            target="written.md",
            description="Verifying that the helper actually writes to ndjson.",
            ledger_path=ledger,
        )
        assert ledger.exists()
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["target"] == "written.md"
        assert entry["status"] == "s2-memory"

    def test_appends_not_overwrites(self, ledger):
        codify.codify_log(
            stage="s1-emergent",
            target="multi.md",
            description="First entry — establishing the pattern emergence.",
            ledger_path=ledger,
        )
        codify.codify_log(
            stage="s2-memory",
            target="multi.md",
            description="Second entry — memory landed after the emergence.",
            ledger_path=ledger,
        )
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
