"""Colocated regression test for `check_db_agent_mirror_integrity` (Agent Packages §M4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.agent_package_build import _surface  # noqa: E402
from tools.noctus.dev.compliance import REPO_ROOT, check_db_agent_mirror_integrity  # noqa: E402


def _repo(tmp_path: Path, *, edit=None, pkg_version="v-1", with_pkg=True) -> Path:
    # the keeper loads the parser from <root>/products/agents/backend: point it at the real one
    (tmp_path / "products" / "agents").mkdir(parents=True)
    (tmp_path / "products" / "agents" / "backend").symlink_to(REPO_ROOT / "products" / "agents" / "backend")
    md = _surface().db_mirror_markdown(
        key="media-analyst", descricao="d", idioma="pt-BR", compiled_text="Corpo.", tools=["Read"], model=None,
        owns_kb=[], versao="1.0.0", version_id="v-1")
    if edit:
        md = edit(md)
    a = tmp_path / ".claude" / "agents"
    a.mkdir(parents=True)
    (a / "media-analyst.md").write_text(md)
    (a / "architect.md").write_text("---\nname: architect\n---\nhand-written agent, not a mirror\n")
    if with_pkg:
        p = tmp_path / "agents" / "media-analyst"
        p.mkdir(parents=True)
        (p / "PACKAGE.json").write_text(json.dumps({"version_id": pkg_version}))
    return tmp_path


class TestDbAgentMirrorIntegrity:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_db_agent_mirror_integrity(repo_root=_repo(tmp_path)) == []

    def test_no_mirror_no_issues(self, tmp_path):
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / ".claude" / "agents" / "x.md").write_text("---\nname: x\n---\nbody\n")
        assert check_db_agent_mirror_integrity(repo_root=tmp_path) == []

    def test_a_hand_edit_of_the_body_is_flagged(self, tmp_path):
        issues = check_db_agent_mirror_integrity(repo_root=_repo(tmp_path, edit=lambda m: m.replace("Corpo.", "Corpo!")))
        assert len(issues) == 1 and "edited by hand" in issues[0]["issue"] and issues[0]["severity"] == "high"

    def test_a_broken_frontmatter_is_flagged(self, tmp_path):
        issues = check_db_agent_mirror_integrity(repo_root=_repo(tmp_path, edit=lambda m: m.replace("studio:\n", "")))
        assert len(issues) == 1 and "does not parse" in issues[0]["issue"]

    def test_mixed_or_partial_exports_are_flagged(self, tmp_path):
        assert "mixed exports" in check_db_agent_mirror_integrity(repo_root=_repo(tmp_path, pkg_version="v-0"))[0]["issue"]

    def test_a_missing_package_json_is_flagged(self, tmp_path):
        assert "partial export" in check_db_agent_mirror_integrity(repo_root=_repo(tmp_path, with_pkg=False))[0]["issue"]
