"""The composite apt action runs under GitHub's `bash -e -o pipefail` (composite `shell: bash`).

2026-11-11 (run 43124289219, found by b5): the first line grep'd for a Google apt source, found none on the
ubuntu24 image, grep exited 1, pipefail + -e killed the step in 19ms with no output - in all 16 jobs. These
tests run the action's REAL script body under that exact shell with sudo / apt-get / timeout stubbed and the
apt paths pointed at a temp tree, so a non-matching grep can never silently kill CI again.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

# The action runs on ubuntu runners: GNU `sed -i -E`. BSD sed (macOS) reads `-E` as the -i backup suffix and never
# rewrites the sources, so a mirror-switch assertion there is vacuous (a3140d263 passed locally, ejected in CI 43163857803).
GNU_SED = subprocess.run(["sed", "--version"], capture_output=True).returncode == 0

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / ".github/actions/apt-install/action.yml"


def _script() -> str:
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    assert len(steps) == 1 and steps[0]["shell"] == "bash"
    return steps[0]["run"]


def _stub(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, *, update_out: str, pkgs: str = "", google: bool = False,
         failing_host: str = "") -> subprocess.CompletedProcess:
    etc = tmp_path / "etc/apt"
    (etc / "sources.list.d").mkdir(parents=True)
    (etc / "apt.conf.d").mkdir()
    (etc / "sources.list.d/ubuntu.sources").write_text(
        "Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\nSuites: noble\n")
    if google:
        (etc / "sources.list.d/google-chrome.list").write_text("deb http://dl.google.com/linux/chrome/deb/ stable main\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "sudo", 'exec "$@"')
    _stub(bin_dir, "timeout", 'shift; exec "$@"')
    # With `failing_host`, only THAT mirror answers `update_out`; any other mirror the sources point at answers healthy,
    # exactly like a real outage of one mirror (the stub used to answer Ign: for every mirror, so the walk never stopped).
    failing = (f'if grep -rqF "{failing_host}" "{etc}/sources.list.d"; then printf "%s\\n" "{update_out}"; '
               f'else printf "%s\\n" "{HEALTHY}"; fi' if failing_host else f'printf "%s\\n" "{update_out}"')
    _stub(bin_dir, "apt-get", f'if [ "$1" = update ]; then {failing}; fi; exit 0')
    script = _script().replace("/etc/apt", str(etc))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PKGS": pkgs, "CAP": "5"}
    # Exactly GitHub's composite invocation: bash --noprofile --norc -eo pipefail {0}
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                          env=env, capture_output=True, text=True, timeout=60)


HEALTHY = "Get:1 http://azure.archive.ubuntu.com/ubuntu noble InRelease"


def test_no_google_source_on_the_image_does_not_kill_the_step(tmp_path):
    r = _run(tmp_path, update_out=HEALTHY)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "apt sources ready" in r.stdout


def test_a_google_source_is_removed(tmp_path):
    r = _run(tmp_path, update_out=HEALTHY, google=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (tmp_path / "etc/apt/sources.list.d/google-chrome.list").exists()


def test_packages_install_on_a_healthy_mirror(tmp_path):
    r = _run(tmp_path, update_out=HEALTHY, pkgs="jq")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "apt install OK" in r.stdout


@pytest.mark.skipif(not GNU_SED, reason="the action targets GNU sed (ubuntu runners); BSD sed cannot rewrite the sources")
def test_an_ign_mirror_is_switched_to_the_first_healthy_fallback(tmp_path):
    r = _run(tmp_path, update_out="Ign:1 http://azure.archive.ubuntu.com/ubuntu noble InRelease",
             failing_host="azure.archive.ubuntu.com")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "apt mirror switched to http://archive.ubuntu.com/ubuntu/" in r.stdout
    assert "mirrors.txt" not in r.stdout  # stopped at the first mirror that answered cleanly
    sources = (tmp_path / "etc/apt/sources.list.d/ubuntu.sources").read_text()
    assert "URIs: http://archive.ubuntu.com/ubuntu/" in sources and "azure." not in sources


@pytest.mark.skipif(not GNU_SED, reason="the action targets GNU sed (ubuntu runners); BSD sed cannot rewrite the sources")
def test_every_mirror_failing_walks_to_the_mirrors_list(tmp_path):
    r = _run(tmp_path, update_out="Ign:1 http://archive.ubuntu.com/ubuntu noble InRelease")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no apt mirror answered cleanly" in r.stdout
    assert "mirror+http://mirrors.ubuntu.com/mirrors.txt" in (tmp_path / "etc/apt/sources.list.d/ubuntu.sources").read_text()


@pytest.mark.parametrize("line", ["set -uo pipefail", "set +e"])
def test_the_script_owns_its_error_handling(line):
    # The script checks every rc itself; -e from the composite shell must be OFF before the first probe.
    commands = [l.strip() for l in _script().splitlines() if l.strip() and not l.strip().startswith("#")]
    assert line in commands[:2]
