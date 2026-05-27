"""Regression tests for `check_agent_kb_alignment` — the agent-context-architecture gate.

KB § PATTERNS/common/agent-context-architecture.md. The keeper enforces that every
agent's frontmatter `owns_kb:` declares full-domain ownership AND every declared
path exists ∧ is body-referenced ∧ is exclusively claimed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_agent_kb_alignment  # noqa: E402


def _write_agent(root: Path, stem: str, frontmatter: str, body: str) -> Path:
    agents_dir = root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    # Ensure KB dir exists so the keeper doesn't short-circuit. Tests that need
    # a KB doc call `_write_kb` separately.
    (root / "KNOWLEDGE-BASE").mkdir(parents=True, exist_ok=True)
    p = agents_dir / f"{stem}.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return p


def _write_kb(root: Path, rel: str, body: str = "# placeholder\n") -> Path:
    kb_dir = root / "KNOWLEDGE-BASE"
    p = kb_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestAgentKbAlignment:
    def test_missing_owns_kb_flagged(self, tmp_path):
        _write_agent(
            tmp_path, "backend-engineer",
            "name: backend-engineer\ndescription: executor.\ntools: Read, Edit",
            "Apply the engineer-seed protocol.",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("missing `owns_kb:`" in i["issue"] for i in issues)

    def test_empty_owns_kb_meta_agent_passes(self, tmp_path):
        # engineer-seed is a meta-agent; `owns_kb: []` is the correct shape.
        _write_agent(
            tmp_path, "engineer-seed",
            "name: engineer-seed\ndescription: protocol.\ntools: Read, Edit\nowns_kb: []",
            "# protocol body",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert issues == []

    def test_meta_agent_with_non_empty_owns_flagged(self, tmp_path):
        _write_kb(tmp_path, "CONTEXT/PATTERNS/foo.md")
        _write_agent(
            tmp_path, "skill-scout",
            "name: skill-scout\ndescription: scout.\ntools: Read, WebSearch\nowns_kb:\n  - CONTEXT/PATTERNS/foo.md",
            "Body referencing KB § PATTERNS/foo.md.",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("Meta-agent" in i["issue"] and "non-empty" in i["issue"] for i in issues)

    def test_declared_path_missing_on_disk_flagged(self, tmp_path):
        _write_agent(
            tmp_path, "backend-engineer",
            "name: backend-engineer\ndescription: executor.\ntools: Read, Edit\nowns_kb:\n  - CONTEXT/PATTERNS/nonexistent.md",
            "Body referencing KB § PATTERNS/nonexistent.md.",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("does NOT exist" in i["issue"] for i in issues)

    def test_declared_path_without_body_pointer_flagged(self, tmp_path):
        _write_kb(tmp_path, "CONTEXT/PATTERNS/backend/backend.md")
        _write_agent(
            tmp_path, "backend-engineer",
            "name: backend-engineer\ndescription: executor.\ntools: Read, Edit\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "Body with no KB pointer at all.",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("no" in i["issue"] and "pointer" in i["issue"] for i in issues)

    def test_declared_path_with_short_form_pointer_passes(self, tmp_path):
        # Post-reorg shape: owns_kb references the subfolder path; body uses
        # the canonical `KB § <short>` form (CONTEXT/ stripped).
        _write_kb(tmp_path, "CONTEXT/PATTERNS/backend/backend.md")
        _write_agent(
            tmp_path, "backend-engineer",
            "name: backend-engineer\ndescription: executor.\ntools: Read, Edit\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "Apply the engineer-seed protocol. → KB § PATTERNS/backend/backend.md",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        # No "missing body pointer" issue — the body explicitly mentions the path.
        assert not any(
            "declares" in i["issue"] and "no" in i["issue"] and "pointer" in i["issue"]
            for i in issues
        )

    def test_double_claim_flagged(self, tmp_path):
        _write_kb(tmp_path, "CONTEXT/PATTERNS/shared.md")
        _write_agent(
            tmp_path, "backend-engineer",
            "name: backend-engineer\ndescription: executor.\ntools: Read, Edit\nowns_kb:\n  - CONTEXT/PATTERNS/shared.md",
            "Apply engineer-seed. KB § PATTERNS/shared.md",
        )
        _write_agent(
            tmp_path, "frontend-engineer",
            "name: frontend-engineer\ndescription: executor.\ntools: Read, Edit\nowns_kb:\n  - CONTEXT/PATTERNS/shared.md",
            "Apply engineer-seed. KB § PATTERNS/shared.md",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("claimed by ≥2 agents" in i["issue"] for i in issues)

    def test_unclaimed_in_scope_doc_flagged(self, tmp_path):
        # An in-scope KB doc (PATTERNS/) with no owner and not in the
        # unowned-allowlist trips the keeper.
        _write_kb(tmp_path, "CONTEXT/PATTERNS/orphan-pattern.md")
        _write_agent(
            tmp_path, "engineer-seed",
            "name: engineer-seed\ndescription: protocol.\ntools: Read, Edit\nowns_kb: []",
            "# protocol body",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert any("not claimed by any agent" in i["issue"] for i in issues)

    def test_unowned_allowlist_passes(self, tmp_path):
        # 01-PHILOSOPHY is in `_AGENT_KB_UNOWNED_ALLOWLIST` — universal commons.
        _write_kb(tmp_path, "CONTEXT/01-PHILOSOPHY.md")
        _write_agent(
            tmp_path, "engineer-seed",
            "name: engineer-seed\ndescription: protocol.\ntools: Read, Edit\nowns_kb: []",
            "# protocol body",
        )
        issues = check_agent_kb_alignment(repo_root=tmp_path)
        assert issues == []
