"""noctus.dev.dispatch_preflight — one call before any engineer dispatch.

Turns R2 (verify-seed-on-fork-base) + R4 (merge-debt) + worktree-collision
+ env-pin-drift + project-doc-phantom from "remember to check" into "the
tool checked". The base-mismatch class this catches cost a full two-wave
re-dispatch this session (engineers fork origin/main; unmerged feature-
branch lifts are invisible to them).

Codification history:
- Initial — R2/R4/collision checks (cured the 2026-05-18 two-wave incident).
- 2026-05-20 — added env-pin-drift (K-1: seed pyproject pins vs `pip show`
  on the active interpreter; cured the agent-a94cc7de313f7aebc stale-
  editable + starlette 1.0.0 drift that masked 986 router errors with one
  TypeError) + `project_slug` convenience (K-3: auto-includes
  `projects/<slug>/PROJECT.md` in wrap_paths so a locally-committed-but-
  unpushed project doc can't dispatch as a phantom path).
"""
from __future__ import annotations

import re
import subprocess
import sys
import sysconfig
from pathlib import Path

from settings import REPO_ROOT


# ---------------------------------------------------------------------------
# K-1 — env-pin drift detection
# ---------------------------------------------------------------------------

# Pins we care about for "the seed's cap MUST hold in the active env".
# These are the seed dependencies whose drift has produced silent runtime
# breakage (Router.__init__ on_startup, supabase ClientOptions.storage, …).
# Add to this list when a new pin is added to seed/lib/backend/pyproject.toml
# with an explicit "ceiling" semantic (operator `<`).
_ENV_PIN_WATCHLIST = {"starlette", "fastapi", "supabase", "pydantic"}

_PIN_LINE_RE = re.compile(
    r'^\s*"(?P<name>[a-zA-Z0-9_.-]+)\s*'
    r'(?P<spec>(?:[<>=!~]=?\s*[0-9][0-9a-z.-]*(?:\s*,\s*)?)+)"\s*,?\s*$'
)


def _parse_seed_pins(pyproject: Path) -> dict[str, str]:
    """Extract `name → spec` from `dependencies = [...]` in pyproject.toml.
    Tolerant of inline comments and multi-line arrays. Stops at the first
    closing bracket on its own indented line."""
    if not pyproject.exists():
        return {}
    in_block = False
    out: dict[str, str] = {}
    for raw in pyproject.read_text().splitlines():
        line = raw.split("#", 1)[0]  # drop inline comments
        if not in_block:
            if "dependencies" in raw and "[" in raw:
                in_block = True
            continue
        if line.strip().startswith("]"):
            break
        m = _PIN_LINE_RE.match(line)
        if m:
            name = m.group("name").lower()
            if name in _ENV_PIN_WATCHLIST:
                out[name] = m.group("spec").strip()
    return out


def _installed_version(pkg: str) -> str | None:
    """Look up an installed package version via importlib.metadata on the
    active interpreter (the same one running this MCP tool). No `pip show`
    subprocess: importlib.metadata is the authoritative source and avoids
    a 100ms+ shell-out per package."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover — Python <3.8 unsupported
        return None
    try:
        return version(pkg)
    except PackageNotFoundError:
        return None


def _spec_violated(spec: str, installed: str) -> bool:
    """True if `installed` does NOT satisfy `spec`. Returns False on parse
    failure (conservative — never block on uncertainty)."""
    try:
        from packaging.specifiers import SpecifierSet  # type: ignore
        from packaging.version import Version
    except ImportError:  # pragma: no cover — packaging always present w/ pip
        return False
    try:
        return Version(installed) not in SpecifierSet(spec)
    except Exception:
        return False


def _env_pin_drift() -> list[dict]:
    """Returns list of `{name, spec, installed, reason}` for each watched
    seed pin whose installed version violates the seed cap."""
    seed_py = REPO_ROOT / "seed" / "lib" / "backend" / "pyproject.toml"
    drifts: list[dict] = []
    for name, spec in _parse_seed_pins(seed_py).items():
        installed = _installed_version(name)
        if installed is None:
            drifts.append({
                "name": name, "spec": spec, "installed": None,
                "reason": "package not installed on active interpreter",
            })
            continue
        if _spec_violated(spec, installed):
            drifts.append({
                "name": name, "spec": spec, "installed": installed,
                "reason": f"installed {installed} violates seed cap {spec}",
            })
    return drifts


# ---------------------------------------------------------------------------
# Shell-out helper (unchanged)
# ---------------------------------------------------------------------------

def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), capture_output=True, text=True, timeout=120,
        cwd=cwd or str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def dispatch_preflight(
    target_paths: list[str],
    wrap_paths: list[str] | None = None,
    base_ref: str = "origin/main",
    project_slug: str | None = None,
    check_env_pins: bool = True,
) -> dict:
    """Pre-flight a brief.

    Args:
      target_paths: files the brief will edit (checked for live-worktree
        collision).
      wrap_paths: seed paths the brief consumes (must exist on `base_ref`).
      base_ref: the engineers' fork base (default `origin/main`).
      project_slug: if set, auto-includes `projects/<slug>/PROJECT.md` in
        wrap_paths. Cures the K-3 phantom-doc class: a locally-committed-
        but-unpushed PROJECT.md is invisible to a worktree spawned from
        `origin/main` and the engineer's `**Improvements:**` contract is
        unsatisfiable. Pass the slug; the tool auto-includes the path.
      check_env_pins: if True, diffs `seed/lib/backend/pyproject.toml`
        strict caps against installed versions on the active interpreter.
        Cures the K-1 stale-editable class (the seed pin can be correct
        while the venv stays stale forever).
    """
    wrap = list(wrap_paths or [])
    if project_slug:
        wrap.append(f"projects/{project_slug}/PROJECT.md")

    missing_on_base: list[str] = []
    for p in wrap:
        r = _run("git", "ls-tree", base_ref, "--", p)
        if not r.stdout.strip():
            missing_on_base.append(p)

    colliding: list[dict] = []
    wt_root = REPO_ROOT / ".claude" / "worktrees"
    if wt_root.exists():
        for wt in wt_root.glob("agent-*"):
            if not (wt / ".git").exists():
                continue
            dirty = {
                l[3:] for l in _run(
                    "git", "-C", str(wt), "status", "--porcelain"
                ).stdout.splitlines() if l.strip()
            }
            hits = sorted(t for t in target_paths if t in dirty)
            if hits:
                colliding.append({"worktree": wt.name, "paths": hits})

    md = _run("bash", str(REPO_ROOT / "scripts" / "merge-debt-monitor.sh"), "--json")
    merge_debt = md.stdout.strip().splitlines()[-1] if md.stdout.strip() else None

    env_drift = _env_pin_drift() if check_env_pins else []

    ok = not missing_on_base and not colliding and not env_drift
    rec = ""
    if missing_on_base:
        rec += ("BLOCK: wrap_paths absent on the fork base — engineers will "
                "STOP (R2 base-mismatch). Push origin/main current first "
                "(or inline the doc content into the brief). ")
    if colliding:
        rec += ("BLOCK: target paths are dirty in a live agent worktree — "
                "collision risk; serialize or re-scope. ")
    if env_drift:
        names = ", ".join(d["name"] for d in env_drift)
        rec += (f"BLOCK: env-pin drift — installed {names} violates seed cap. "
                f"Run `pip install --force-reinstall -e seed/lib/backend` "
                f"to re-resolve before dispatch (engineers share the venv). ")
    if not rec:
        rec = "CLEAR to dispatch."

    return {
        "ok": ok,
        "base_ref": base_ref,
        "missing_on_base": missing_on_base,
        "colliding_worktrees": colliding,
        "merge_debt": merge_debt,
        "env_pin_drift": env_drift,
        "active_interpreter": sys.executable,
        "recommendation": rec.strip(),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_preflight",
        description=(
            "Pre-flight an engineer brief BEFORE dispatch. Catches: "
            "(a) wrap_paths absent on engineers' fork base (R2 — unmerged "
            "lifts are invisible to worktrees); (b) target_paths dirty in a "
            "live agent worktree (collision); (c) seed pyproject pins "
            "violated by installed packages on the active interpreter "
            "(K-1 — the seed cap is correct, but a stale editable from a "
            "dead worktree can leave the venv stuck on the wrong version); "
            "(d) merge-debt severity. `project_slug` auto-includes "
            "projects/<slug>/PROJECT.md in wrap_paths (K-3 phantom-doc "
            "cure). Returns ok + a block/clear recommendation."
        ),
    )
    def _preflight(
        target_paths: list[str],
        wrap_paths: list[str] | None = None,
        base_ref: str = "origin/main",
        project_slug: str | None = None,
        check_env_pins: bool = True,
    ) -> dict:
        return dispatch_preflight(
            target_paths,
            wrap_paths=wrap_paths,
            base_ref=base_ref,
            project_slug=project_slug,
            check_env_pins=check_env_pins,
        )


__all__ = ["dispatch_preflight", "register"]
