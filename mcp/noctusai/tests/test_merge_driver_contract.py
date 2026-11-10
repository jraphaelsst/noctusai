"""ONE contract every custom git merge driver must honour — discovered, not listed.

Why this exists (2026-11-10): a custom driver exited 1 on a real prose conflict and
left %A as "ours". git takes %A as the merge RESULT (a non-zero exit only flags the
path), so the file showed as conflicted with NO markers and the other side's line
silently gone. Each driver had its own test that pinned its own behaviour; none pinned
the contract, so a sibling (`lgpd-warnings`, `gate-inventory`) kept the same flaw.

Drivers are DISCOVERED from `.gitattributes` (`<pattern> merge=<name>`, builtin
`union` excluded) and `scripts/hooks/register-merge-drivers.sh` (`reg <name> ... <script>`),
so a new driver is covered the moment it is registered. A driver with no fixture in
`SPECS` below FAILS `test_every_driver_has_a_contract_fixture` — adding a driver means
adding its minimal valid fixture here (the construction leg of the build triad).

Per driver, through REAL `git merge` (so git's reading of %A is what is asserted):
  (i)   real conflict  -> merge exits non-zero, %A holds conflict markers AND both sides' lines;
  (ii)  clean merge    -> exit 0, both sides' lines present, no markers;
  (iii) the driver writes %A and NOTHING else (no tracked file, no scratch leftover).

KB § PATTERNS/common/auto-generated-merge-drivers.md
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import lgpd  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "scripts" / "hooks"
REAL_CLI = REPO / "mcp" / "noctusai" / "cli.py"
BUILTIN = {"union"}
MARKER_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.M)


# ── discovery ─────────────────────────────────────────────────────────────
def discover_drivers() -> dict[str, dict]:
    """{driver: {"patterns": [...], "script": "merge-x.sh"}} from the two committed sources."""
    attrs: dict[str, list[str]] = {}
    for line in (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\S+)\s+merge=(\S+)\s*$", line)
        if m and m.group(2) not in BUILTIN:
            attrs.setdefault(m.group(2), []).append(m.group(1))
    regs: dict[str, str] = {}
    for line in (HOOKS / "register-merge-drivers.sh").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^reg\s+(\S+)\s+".*"\s+(\S+\.sh)\s*$', line)
        if m:
            regs[m.group(1)] = m.group(2)
    return {n: {"patterns": attrs.get(n, []), "script": regs.get(n)} for n in sorted(set(attrs) | set(regs))}


DRIVERS = discover_drivers()


# ── per-driver minimal valid fixtures ─────────────────────────────────────
@dataclass(frozen=True)
class Spec:
    path: str                    # concrete tracked path the driver's pattern routes
    base: str
    ours_conflict: str
    theirs_conflict: str
    conflict_tokens: tuple[str, str]   # one token per side, must both survive in %A
    ours_clean: str
    theirs_clean: str
    clean_tokens: tuple[str, str]


def _lgpd_entry(concern: str, mit: str = "m") -> str:
    return lgpd._format_entry(concern=concern, code_path=f"{concern}.py", reason="r", mitigation=mit,
                              first_flagged="2026-10-10", last_seen="2026-10-10", checked=False)


def _lgpd_doc(*entries: str) -> str:
    return lgpd._FILE_HEADER + "\n".join(e.rstrip() for e in entries) + "\n"


def _inv(gates, decisions=()) -> str:
    return json.dumps({"measured_over": "m", "gates": {g: {"severity": s} for g, s in gates},
                       "decisions": list(decisions)}, indent=1, ensure_ascii=False) + "\n"


_KB_BASE = "# Doc\n\nrow-a\n\nmid-1\n\nmid-2\n\nrow-z\n"
_LGPD_BASE = _lgpd_doc(_lgpd_entry("alpha"))
_INV_BASE = _inv([("a", "x")])

SPECS: dict[str, Spec] = {
    "kb-counts": Spec(
        path="KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
        base=_KB_BASE,
        ours_conflict=_KB_BASE.replace("row-a", "row-a OURS-EDIT"),
        theirs_conflict=_KB_BASE.replace("row-a", "row-a THEIRS-EDIT"),
        conflict_tokens=("OURS-EDIT", "THEIRS-EDIT"),
        ours_clean="- top-ours-line\n" + _KB_BASE,
        theirs_clean=_KB_BASE + "- bottom-theirs-line\n",
        clean_tokens=("top-ours-line", "bottom-theirs-line"),
    ),
    "lgpd-warnings": Spec(
        path="LGPD-WARNINGS.md",
        base=_LGPD_BASE,
        ours_conflict=_lgpd_doc(_lgpd_entry("alpha", "OURS-MIT")),
        theirs_conflict=_lgpd_doc(_lgpd_entry("alpha", "THEIRS-MIT")),
        conflict_tokens=("OURS-MIT", "THEIRS-MIT"),
        ours_clean=_lgpd_doc(_lgpd_entry("beta"), _lgpd_entry("alpha")),
        theirs_clean=_lgpd_doc(_lgpd_entry("gamma"), _lgpd_entry("alpha")),
        clean_tokens=("beta.py", "gamma.py"),
    ),
    "gate-inventory": Spec(
        path="KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/gate-alignment-inventory.json",
        base=_INV_BASE,
        ours_conflict=_inv([("a", "OURS-SEV")]),
        theirs_conflict=_inv([("a", "THEIRS-SEV")]),
        conflict_tokens=("OURS-SEV", "THEIRS-SEV"),
        ours_clean=_inv([("a", "x"), ("n1", "x")]),
        theirs_clean=_inv([("a", "x"), ("n0", "x")]),
        clean_tokens=("n1", "n0"),
    ),
}


# ── fixture repo ──────────────────────────────────────────────────────────
def _git(cwd: Path, *a: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=check,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def _make_repo(tmp_path: Path, spec: Spec) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "mcp" / "noctusai").mkdir(parents=True)
    for f in HOOKS.glob("merge-*.sh"):
        shutil.copy(f, root / "scripts" / "hooks" / f.name)
    shutil.copy(HOOKS / "register-merge-drivers.sh", root / "scripts" / "hooks" / "register-merge-drivers.sh")
    # the REAL cli through a shim: the drivers resolve $REPO_ROOT/mcp/noctusai/cli.py
    (root / "mcp" / "noctusai" / "cli.py").write_text(
        f"import runpy, sys\nREAL = {str(REAL_CLI)!r}\nsys.argv[0] = REAL\nrunpy.run_path(REAL, run_name='__main__')\n")
    shutil.copy(REPO / ".gitattributes", root / ".gitattributes")
    (root / ".noctusai-workspace").write_text("")
    _git(root, "init", "-q", "-b", "main")
    p = root / spec.path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(spec.base, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    subprocess.run(["bash", str(root / "scripts/hooks/register-merge-drivers.sh"), str(root)], check=True,
                   capture_output=True, env={**os.environ, "PYTHON": sys.executable})
    return root


def _diverge(root: Path, spec: Spec, ours: str, theirs: str) -> None:
    _git(root, "checkout", "-q", "-b", "theirs", "main")
    (root / spec.path).write_text(theirs, encoding="utf-8")
    _git(root, "commit", "-qam", "theirs")
    _git(root, "checkout", "-q", "main")
    (root / spec.path).write_text(ours, encoding="utf-8")
    _git(root, "commit", "-qam", "ours")


# ── the contract ──────────────────────────────────────────────────────────
def test_discovery_finds_the_known_drivers():
    assert {"kb-counts", "lgpd-warnings", "gate-inventory"} <= set(DRIVERS)


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_driver_is_wired_end_to_end(name):
    d = DRIVERS[name]
    assert d["patterns"], f"driver {name!r} is registered but no .gitattributes pattern routes to it"
    assert d["script"], f"driver {name!r} is in .gitattributes but not registered in register-merge-drivers.sh"
    assert (HOOKS / d["script"]).is_file(), f"{d['script']} missing"


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_every_driver_has_a_contract_fixture(name):
    assert name in SPECS, (
        f"merge driver {name!r} has no minimal fixture in SPECS — add one so the merge-driver "
        f"contract (markers on conflict / clean merge / writes only %A) covers it")
    spec = SPECS[name]
    assert any(fnmatch.fnmatch(spec.path, pat) for pat in DRIVERS[name]["patterns"]), (
        f"SPECS[{name!r}].path {spec.path!r} is not routed to the driver by .gitattributes")


@pytest.mark.parametrize("name", sorted(set(DRIVERS) & set(SPECS)))
class TestContract:
    def test_real_conflict_leaves_markers_with_both_sides(self, tmp_path, name):
        spec = SPECS[name]
        root = _make_repo(tmp_path, spec)
        _diverge(root, spec, spec.ours_conflict, spec.theirs_conflict)
        r = _git(root, "merge", "--no-edit", "theirs", check=False, env={"PYTHON": sys.executable})
        assert r.returncode != 0, r.stdout + r.stderr
        text = (root / spec.path).read_text(encoding="utf-8")
        assert MARKER_RE.search(text), f"conflicted but NO markers: git would show a silent 'ours'\n{text}"
        for tok in spec.conflict_tokens:
            assert tok in text, f"{tok!r} (one side's line) was silently dropped from %A\n{text}"
        assert spec.path in _git(root, "diff", "--name-only", "--diff-filter=U").stdout

    def test_clean_merge_exits_zero_with_both_sides(self, tmp_path, name):
        spec = SPECS[name]
        root = _make_repo(tmp_path, spec)
        _diverge(root, spec, spec.ours_clean, spec.theirs_clean)
        r = _git(root, "merge", "--no-edit", "theirs", check=False, env={"PYTHON": sys.executable})
        assert r.returncode == 0, r.stdout + r.stderr
        text = (root / spec.path).read_text(encoding="utf-8")
        assert not MARKER_RE.search(text)
        for tok in spec.clean_tokens:
            assert tok in text, f"{tok!r} missing from a clean merge result\n{text}"

    @pytest.mark.parametrize("case", ["conflict", "clean"])
    def test_driver_writes_only_percent_a(self, tmp_path, name, case):
        spec = SPECS[name]
        root = _make_repo(tmp_path, spec)
        ours, theirs = ((spec.ours_conflict, spec.theirs_conflict) if case == "conflict"
                        else (spec.ours_clean, spec.theirs_clean))
        d = tmp_path / "args"
        d.mkdir()
        (d / "O").write_text(spec.base, encoding="utf-8")
        (d / "A").write_text(ours, encoding="utf-8")
        (d / "B").write_text(theirs, encoding="utf-8")
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        before = _git(root, "status", "--porcelain").stdout
        tracked_before = (root / spec.path).read_text(encoding="utf-8")
        subprocess.run([str(root / "scripts/hooks" / DRIVERS[name]["script"]),
                        str(d / "O"), str(d / "A"), str(d / "B"), spec.path], cwd=root, capture_output=True,
                       env={**os.environ, "PYTHON": sys.executable, "TMPDIR": str(scratch)})
        assert _git(root, "status", "--porcelain").stdout == before, "driver touched the work tree / index"
        assert (root / spec.path).read_text(encoding="utf-8") == tracked_before
        assert list(scratch.iterdir()) == [], "driver left scratch files behind"
        assert (d / "O").read_text(encoding="utf-8") == spec.base and (d / "B").read_text(encoding="utf-8") == theirs, \
            "driver modified %O/%B"

    @pytest.mark.parametrize("case", ["conflict", "clean"])
    def test_broken_toolkit_still_hands_git_both_sides(self, tmp_path, name, case):
        """The render half (python/cli) failing is the quiet path: the driver must fall back to
        the plain 3-way merge, never leave %A as 'ours' with a non-zero exit."""
        spec = SPECS[name]
        root = _make_repo(tmp_path, spec)
        (root / "mcp" / "noctusai" / "cli.py").write_text("import sys\nsys.exit(2)\n")
        _git(root, "commit", "-qam", "break cli")
        ours, theirs, toks = ((spec.ours_conflict, spec.theirs_conflict, spec.conflict_tokens) if case == "conflict"
                              else (spec.ours_clean, spec.theirs_clean, spec.clean_tokens))
        _diverge(root, spec, ours, theirs)
        _git(root, "merge", "--no-edit", "theirs", check=False, env={"PYTHON": sys.executable})
        text = (root / spec.path).read_text(encoding="utf-8")
        for tok in toks:
            assert tok in text, f"{tok!r} dropped when the render half failed\n{text}"
