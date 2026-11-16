"""ONE resolver for the toolkit's node toolchain (`mcp/noctusai/node`: ts-morph, PGlite).

`node_modules/` is gitignored, so every fresh worktree and every scrubbed export checkout lacks it, and each
ts-morph keeper then fails with a package-resolution error that reads like a real break (N>=4 on 2026-11-14/15:
the silent-refusal scanner refused two merge commits, polling-budget went red on a primary that was never
installed). Before this module each keeper resolved (or did not resolve) the install on its own.

`resolve(worktree)` is the single answer, in this order:
  1. the worktree's own `mcp/noctusai/node/node_modules` when it carries every required package;
  2. else another checkout's install (the primary, via git-common-dir; the checkout owning this interpreter's venv;
     explicit `sources=`) -- ONLY when its `package-lock.json` is byte-identical to the worktree's, because only
     then is it what CI's `npm ci` would install. It is symlinked in (`link=True`, gitignored) or, when the
     symlink cannot be made, borrowed through `Toolchain.invocation`;
  3. else a LOUD `Toolchain.reason` naming the exact `npm ci` command. A caller reports that as UNMEASURED or
     refuses with it. A mismatched install is never borrowed silently.

Stdlib only (the steward PreToolUse hook loads toolkit modules with nothing else on sys.path).
KB § PATTERNS/architect/mcp-tool-conventions.md (Node toolchain) · KB § PATTERNS/common/self-branching-mode.md § 5a.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

NODE_REL = ("mcp", "noctusai", "node")
DEFAULT_REQUIRE = ("ts-morph",)
_LOCK = "package-lock.json"


@dataclass(frozen=True)
class Toolchain:
    ok: bool
    node_dir: Path          # <worktree>/mcp/noctusai/node
    source: str             # "own" | "linked" | "installed" | "borrowed" | "" (not ok)
    provider: Path | None   # the node dir whose node_modules serves (== node_dir for own/linked)
    reason: str = ""        # "" when ok; else why not + the exact fix

    def invocation(self, script: Path) -> tuple[list[str], Path | None]:
        """`(argv, cwd)` that runs `script` with the required packages resolvable. Own/linked: run it in place.
        Borrowed (symlink impossible): feed the TREE's script text to node with the cwd at the install, so the tree's
        script is judged but its modules resolve from the matching install."""
        if self.source == "borrowed" and self.provider is not None:
            return ["node", "--input-type=module", "-e", script.read_text(encoding="utf-8")], self.provider
        return ["node", str(script)], None


def _git_common_checkout(worktree: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=worktree,
                             capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out).parent if out else None


def _candidate_sources(worktree: Path, sources: Sequence[Path | str] | None) -> list[Path]:
    """Checkout roots that may carry the install, most specific first. `sources` replaces auto-discovery."""
    if sources is not None:
        cands = [Path(s) for s in sources]
    else:
        cands = [Path(__file__).resolve().parents[2]]  # the checkout this toolkit process runs from
        prefix = Path(sys.prefix)
        if prefix.name == ".venv" and prefix.parent.name == "noctusai":  # <repo>/mcp/noctusai/.venv
            cands.append(prefix.parent.parent.parent)
        common = _git_common_checkout(worktree)
        if common is not None:
            cands.append(common)
    seen: set[Path] = set()
    out: list[Path] = []
    for c in cands:
        try:
            key = c.resolve()
        except OSError:
            key = c
        if key == worktree.resolve() or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _missing(node_dir: Path, require: Sequence[str]) -> list[str]:
    nm = node_dir / "node_modules"
    if not nm.exists():  # absent or a dangling symlink
        return list(require) or ["node_modules"]
    return [r for r in require if not (nm / r).exists()]


def lockfile_verdict(node_dir: Path, source_dir: Path) -> str:
    """"" when both `package-lock.json` files exist and are byte-identical, else why not."""
    a, b = node_dir / _LOCK, source_dir / _LOCK
    try:
        if a.read_bytes() != b.read_bytes():
            return f"{'/'.join(NODE_REL)}/{_LOCK} differs between the worktree and {source_dir} - its node_modules is not what CI installs"
    except OSError as exc:
        return f"cannot compare {'/'.join(NODE_REL)}/{_LOCK} with {source_dir}: {exc}"
    return ""


def resolve(worktree: Path | str | None = None, *, require: Sequence[str] = DEFAULT_REQUIRE, link: bool = True,
            sources: Sequence[Path | str] | None = None) -> Toolchain:
    """Resolve the node toolchain for `worktree` (default: this toolkit's own tree). See the module docstring."""
    wt = Path(worktree) if worktree is not None else Path(__file__).resolve().parents[2]
    node_dir = wt.joinpath(*NODE_REL)
    fix = f"run `npm ci --prefix {node_dir}`"
    own_missing = _missing(node_dir, require)
    if not own_missing:
        return Toolchain(True, node_dir, "own", node_dir)
    why: list[str] = []
    for src_root in _candidate_sources(wt, sources):
        src = src_root.joinpath(*NODE_REL)
        gone = _missing(src, require)
        if gone:
            why.append(f"{', '.join(gone)} is not installed in {src} (run `npm ci --prefix {src}`)")
            continue
        mismatch = lockfile_verdict(node_dir, src)
        if mismatch:
            why.append(mismatch)
            continue
        nm = node_dir / "node_modules"
        if link:
            try:
                if nm.is_symlink():
                    nm.unlink()  # dangling or stale link; a REAL directory is never touched
                if not nm.exists():
                    node_dir.mkdir(parents=True, exist_ok=True)
                    nm.symlink_to((src / "node_modules").resolve(), target_is_directory=True)
                    return Toolchain(True, node_dir, "linked", node_dir)
            except OSError:
                if not _missing(node_dir, require):  # a concurrent resolver linked it first
                    return Toolchain(True, node_dir, "linked", node_dir)
                # else fall through to the borrowed form
        return Toolchain(True, node_dir, "borrowed", src)
    state = "carries a real node_modules without " + ", ".join(own_missing) if (node_dir / "node_modules").is_dir() and not (node_dir / "node_modules").is_symlink() else "has no usable node_modules"
    detail = "; ".join(why) if why else "no other checkout with an install was found"
    return Toolchain(False, node_dir, "", None, f"node toolchain unavailable: {node_dir} {state} ({detail}) - {fix}")


def provision(worktree: Path | str | None = None, *, require: Sequence[str] = DEFAULT_REQUIRE,
              sources: Sequence[Path | str] | None = None, install: bool = True, timeout: int = 900,
              run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Toolchain:
    """`resolve`, and when there is NO usable install anywhere (no lockfile-identical one to link) INSTALL it:
    `npm ci --prefix <worktree node dir>` -- the one install CI itself runs, so the result is what CI judges against.

    This is the construction behind a fresh worktree/agent worktree: a lockfile-identical link when one exists, else a
    LOUD install (the returned `Toolchain` says `source="installed"`, or `ok=False` with npm's own tail). `install=False`
    is `resolve` plus the same loud reason. A `node_modules` that is a SYMLINK is removed before `npm ci` -- `npm ci`
    deletes the directory it installs into, and through a link that is another checkout's install."""
    wt = Path(worktree) if worktree is not None else Path(__file__).resolve().parents[2]
    tc = resolve(wt, require=require, sources=sources)
    if tc.ok or not install:
        return tc
    node_dir = tc.node_dir
    if not (node_dir / _LOCK).is_file():
        return Toolchain(False, node_dir, "", None, f"{tc.reason} (and {node_dir / _LOCK} is absent, so there is nothing to `npm ci`)")
    npm = shutil.which("npm")
    if npm is None:
        return Toolchain(False, node_dir, "", None, f"{tc.reason} (`npm` is not on PATH, so it was not installed automatically)")
    nm = node_dir / "node_modules"
    try:
        if nm.is_symlink():
            nm.unlink()
        proc = run([npm, "ci", "--prefix", str(node_dir), "--no-audit", "--no-fund"], capture_output=True, text=True,
                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return Toolchain(False, node_dir, "", None, f"`npm ci --prefix {node_dir}` exceeded {timeout}s - run it by hand: {tc.reason}")
    except OSError as exc:
        return Toolchain(False, node_dir, "", None, f"`npm ci --prefix {node_dir}` could not start ({exc}) - {tc.reason}")
    if proc.returncode != 0:
        tail = ((proc.stderr or proc.stdout or "").strip())[-400:]
        return Toolchain(False, node_dir, "", None, f"`npm ci --prefix {node_dir}` failed (exit {proc.returncode}): {tail}")
    after = _missing(node_dir, require)
    if after:
        return Toolchain(False, node_dir, "", None, f"`npm ci --prefix {node_dir}` succeeded but {', '.join(after)} is still missing - the lockfile does not install it")
    return Toolchain(True, node_dir, "installed", node_dir)


def run_files_scan(script_rel: Sequence[str], files: Sequence[Path], *, root: Path | None = None, timeout: int,
                   label: str = "node scan", worktree: Path | None = None,
                   run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                   ) -> tuple[dict[str, list[dict]], dict[str, str], str | None]:
    """Run a `{files:[...]} -> {ok, results, errors}` ts-morph scan script. Returns `(results, per_file_errors,
    bootstrap_error)`; `bootstrap_error` is set when the scan could not run at all (never a silent zero), with the
    exact fix. The one subprocess recipe behind the silent-refusal / motion-import / lying-loading / module-page /
    polling keepers."""
    if not files:
        return {}, {}, None
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    toolkit = Path(__file__).resolve().parents[2]
    script = base.joinpath(*script_rel)
    if not script.exists():  # the tree under check lacks the script: judge with the toolkit's own, from the toolkit's tree
        base, script = toolkit, toolkit.joinpath(*script_rel)
    if shutil.which("node") is None:
        return {}, {}, f"node_unavailable: `node` not on PATH - the {label} cannot run"
    if not script.exists():
        return {}, {}, f"script_missing: {script}"
    tc = resolve(worktree or base)
    if not tc.ok:
        return {}, {}, f"ts_morph_not_installed: {tc.reason}"
    argv, cwd = tc.invocation(script)
    try:
        proc = run(argv, input=json.dumps({"files": [str(f) for f in files]}), cwd=cwd,
                   capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}, {}, f"timeout: the {label} exceeded {timeout}s ({len(files)} files)"
    except OSError as exc:
        return {}, {}, f"spawn_failed: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-600:]
        if "Cannot find module" in tail or "ERR_MODULE_NOT_FOUND" in tail:
            return {}, {}, f"ts_morph_not_installed: run `npm ci --prefix {tc.node_dir}` - {tail.strip()[:300]}"
        return {}, {}, f"node_crashed (exit {proc.returncode}): {tail}"
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {}, {}, f"non_json_stdout: {exc}; stdout={proc.stdout[:300]!r}"
    if not parsed.get("ok", True):
        return {}, {}, f"bad_request: {parsed.get('error')}"
    return parsed.get("results", {}), parsed.get("errors", {}), None
