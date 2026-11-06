"""Workflow-content keepers: `cli.py` flags exist, `pip install -r` paths resolve,
actionlint verdict honesty. Red fixtures + real-tree baseline-zero.

-> KB § PATTERNS/devops/dev-main-ci-gates.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as C  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CLI_PY = (
    "import argparse\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--check-real', action='store_true')\n"
    "p.add_argument('--other', metavar='X')\n"
)


def _repo(tmp_path: Path, run: str, step_extra: str = "", job_extra: str = "", files: dict | None = None) -> Path:
    (tmp_path / "mcp" / "noctusai").mkdir(parents=True)
    (tmp_path / "mcp" / "noctusai" / "cli.py").write_text(CLI_PY)
    for rel, body in (files or {}).items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    ind = "\n".join("          " + ln for ln in run.splitlines())
    (d / "a.yml").write_text(
        f"jobs:\n  x:\n    runs-on: u\n    timeout-minutes: 5\n{job_extra}    steps:\n"
        f"      - name: s\n{step_extra}        run: |\n{ind}\n"
    )
    return tmp_path



class TestWorkflowCliFlagsExist:
    def test_unknown_flag_flagged(self, tmp_path):
        out = C.check_workflow_cli_flags_exist(_repo(tmp_path, "python mcp/noctusai/cli.py --check-ghost"))
        assert len(out) == 1 and "--check-ghost" in out[0]["issue"] and out[0]["severity"] == "high"


    def test_known_flags_pass_including_continuation_and_equals(self, tmp_path):
        run = "python mcp/noctusai/cli.py \\\n  --check-real --other=foo && echo done"
        assert C.check_workflow_cli_flags_exist(_repo(tmp_path, run)) == []


    def test_flags_after_separator_not_attributed_to_cli(self, tmp_path):
        run = "python mcp/noctusai/cli.py --check-real | tee x --not-a-cli-flag"
        assert C.check_workflow_cli_flags_exist(_repo(tmp_path, run)) == []


    def test_flag_set_is_derived_from_parser(self):
        defined = C._cli_defined_flags(REPO)
        assert "--check-workflow-cli-flags-exist" in defined and "--check-workflow-job-timeouts" in defined


class TestWorkflowMcpRequirementsPath:
    def test_root_relative_requirements_missing_flagged(self, tmp_path):
        out = C.check_workflow_mcp_requirements_path(_repo(tmp_path, "pip install -r requirements.txt"))
        assert len(out) == 1 and "requirements.txt" in out[0]["issue"] and out[0]["severity"] == "high"


    def test_mcp_path_passes(self, tmp_path):
        r = _repo(tmp_path, "pip install -r mcp/noctusai/requirements.txt", files={"mcp/noctusai/requirements.txt": ""})
        assert C.check_workflow_mcp_requirements_path(r) == []


    def test_working_directory_and_cd_respected(self, tmp_path):
        f = {"mcp/noctusai/requirements.txt": ""}
        r1 = _repo(tmp_path / "a", "pip install -r requirements.txt", step_extra="        working-directory: mcp/noctusai\n", files=f)
        assert C.check_workflow_mcp_requirements_path(r1) == []
        r2 = _repo(tmp_path / "b", "(cd mcp/noctusai && pip install -r requirements.txt)", files=f)
        assert C.check_workflow_mcp_requirements_path(r2) == []
        r3 = _repo(tmp_path / "c", "cd mcp/noctusai\npip install -r requirements.txt", files=f)
        assert C.check_workflow_mcp_requirements_path(r3) == []


class TestWorkflowActionlint:
    def test_actionlint_absent_is_inconclusive_never_clean(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _n: None)
        out = C.check_workflow_actionlint(tmp_path)
        assert len(out) == 1 and out[0]["severity"] == "inconclusive"
        assert C.check_workflow_actionlint(tmp_path, require=True)[0]["severity"] == "high"


    @pytest.mark.skipif(not (shutil.which("actionlint") and shutil.which("shellcheck")), reason="actionlint/shellcheck absent")
    def test_actionlint_red_then_green(self, tmp_path):
        d = tmp_path / ".github" / "workflows"
        d.mkdir(parents=True)
        wf = "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          v=$1\n          echo $v\n"
        (d / "a.yml").write_text(wf)
        red = C.check_workflow_actionlint(tmp_path)
        assert red and "SC2086" in red[0]["issue"]
        (d / "a.yml").write_text(wf.replace("echo $v", 'echo "$v"').replace("v=$1", "v=1"))
        assert C.check_workflow_actionlint(tmp_path) == []

# ── real-tree baseline zero ──────────────────────────────────────────────────
def test_real_tree_clean():
    assert C.check_workflow_cli_flags_exist(REPO) == []
    assert C.check_workflow_mcp_requirements_path(REPO) == []
    assert all(i["severity"] == "inconclusive" for i in C.check_workflow_actionlint(REPO))
