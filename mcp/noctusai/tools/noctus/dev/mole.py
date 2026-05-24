"""noctus.dev.mole — storage-hygiene mole (native Python port).

MCP-first: this is the NATIVE-Python implementation of the storage-hygiene
`mole` (formerly a thin subprocess shim over `scripts/mole.sh`). An agent
can scan/sweep storage waste — artifacts (regenerable caches/builds),
environments (venv/node_modules dup, advisory-only), worktrees (stale
`.claude/worktrees/agent-*/`).

Project cleanup is a DIFFERENT surface — already `noctus.dev.archive`.

═══ SAFE-GATE (what makes a sweep safe to execute) ═══════════════════════
Destructive ONLY under `mode="sweep", force=True`. The classifier NEVER
removes:
  • a worktree with uncommitted changes,
  • a worktree whose branch is NOT merged-to-`dev` — "merged" =
    reachable from `origin/dev` (the integration branch engineer worktrees
    integrate to — KB § PATTERNS/branching-and-merging.md § 0) by
    SHA-ancestry OR all commits present by PATCH-ID (our orchestrator
    integrates via cherry-pick → new SHA, same patch; the patch-id /
    `git cherry` check covers that),
  • the main worktree, sibling/seed workspaces, `.env`, or migration
    files.
Additional operator gate (NOT enforced here — caller's duty):
  • Confirm NO other agent is mid-flight in a target worktree. A branch
    can be patch-id-merged while an agent still has that worktree open;
    sweeping it mid-flight destroys live work. `mode="scan"` first,
    eyeball the STALE/ORPHAN list, only then `sweep` with `force=True`.
`mode="sweep"` WITHOUT `force=True` is a **dry-run** (lists what would
go, deletes nothing) — the safe default this tool returns by default.
═════════════════════════════════════════════════════════════════════════

Behaviour parity: this module reproduces `scripts/mole.sh` exactly —
same artifact deny-list + prune rules, same advisory-only environments
scope, same 6-category worktree taxonomy (`_classify_worktrees` →
STALE / STALE_LOCKED / STALE_DIRTY / ACTIVE / ORPHAN / PHANTOM), same
shared-stash subtraction (THE-P11), same dead-pid auto-unlock, same
self-skip, same severity grading + next_action thresholds, same JSON
result shape. The merged-base + merged predicate is the shared
`_worktree_staleness` helper (consumed identically by
`noctus.dev.cleanup_stale_worktrees`) — one source of truth, no parity
drift.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from settings import REPO_ROOT
from workspace import resolve_caller_root
from tools.noctus.dev import _worktree_staleness as wts

# ── Severity thresholds (mirror disk-usage-monitor.sh exit-code semantics) ──
ARTIFACT_WARNING_MB = 2048    # 2 GB
ARTIFACT_CRITICAL_MB = 5120   # 5 GB
WORKTREE_WARNING_COUNT = 15
WORKTREE_CRITICAL_COUNT = 30

# Patterns the artifact-scope matches (the deny-list of safe-to-wipe dirs).
ARTIFACT_DIR_NAMES = (
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tsbuildinfo",
    "coverage",
)
# Frontend build outputs — only safe under products/*/frontend/.
ARTIFACT_FRONTEND_BUILD_NAMES = ("dist", "build", ".next")

_SAFE_GATE = (
    "sweep deletes ONLY merged-to-dev (SHA-ancestry|patch-id) "
    "worktrees + regenerable artifacts; never uncommitted / "
    "unmerged / main / siblings / .env / migrations. Caller MUST "
    "also confirm no agent is mid-flight in a target worktree. "
    "Run scan first; sweep needs force=True (else dry-run)."
)


# ───────────────────────────── git helpers ─────────────────────────────
def _git(root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ─────────────────────────── artifacts scope ───────────────────────────
def _iter_artifact_dirs(root: Path):
    """Yield artifact dirs honoring mole.sh prune rules.

    Pruned: ./.claude/worktrees, ./*/.venv, ./*/*/.venv, ./venv,
    ./node_modules. Frontend build names (dist/build/.next) only under
    products/*/frontend/ and never inside node_modules.
    """
    prune_abs = {
        root / ".claude" / "worktrees",
        root / "venv",
        root / "node_modules",
    }

    def _is_pruned(d: Path) -> bool:
        for p in prune_abs:
            if d == p or p in d.parents:
                return True
        # ./*/.venv and ./*/*/.venv  → any .venv at depth 1 or 2
        if d.name == ".venv":
            rel = d.relative_to(root)
            if len(rel.parts) in (2, 3):
                return True
        return False

    for name in ARTIFACT_DIR_NAMES:
        for d in root.rglob(name):
            if not d.is_dir():
                continue
            if _is_pruned(d):
                continue
            # Skip anything under a pruned ancestor (worktrees / venv / node_modules).
            if any(
                anc.name in ("node_modules",)
                or anc == root / ".claude" / "worktrees"
                or anc == root / "venv"
                for anc in d.parents
            ):
                continue
            if any(
                anc.name == ".venv"
                and len(anc.relative_to(root).parts) in (2, 3)
                for anc in d.parents
            ):
                continue
            yield d

    products = root / "products"
    if products.is_dir():
        for name in ARTIFACT_FRONTEND_BUILD_NAMES:
            # find ./products -maxdepth 4 -type d -name <name> | grep /frontend/
            # | grep -v /node_modules/
            for d in products.rglob(name):
                if not d.is_dir():
                    continue
                rel = d.relative_to(products)
                if len(rel.parts) > 4:
                    continue
                full = str(d)
                if "/frontend/" not in full + "/":
                    continue
                if "/node_modules/" in full:
                    continue
                yield d


def _scan_artifacts(root: Path) -> tuple[int, list[tuple[Path, int]]]:
    entries: list[tuple[Path, int]] = []
    total_kb = 0
    for d in _iter_artifact_dirs(root):
        mb_path = d
        # du -sk gives KB; recompute in KB for parity with the script total.
        kb = _du_kb(mb_path)
        if kb <= 0:
            continue
        total_kb += kb
        entries.append((d, kb))
    return total_kb // 1024, entries


def _du_kb(path: Path) -> int:
    total_kb = 0
    if path.is_file():
        try:
            return path.stat().st_size // 1024
        except OSError:
            return 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for fn in filenames:
            fp = Path(dirpath) / fn
            try:
                if fp.is_symlink():
                    continue
                total_kb += fp.stat().st_size // 1024
            except OSError:
                continue
    return total_kb


def _sweep_artifacts(
    root: Path, dry_run: bool, log_lines: list[str]
) -> tuple[int, int, list[str]]:
    removed_kb = 0
    removed_count = 0
    notes: list[str] = []
    for d in list(_iter_artifact_dirs(root)):
        kb = _du_kb(d)
        if kb <= 0:
            continue
        if dry_run:
            notes.append(f"[dry-run] would remove: {d} ({kb} KB)")
        else:
            try:
                shutil.rmtree(d)
                removed_kb += kb
                removed_count += 1
            except OSError:
                continue
    if not dry_run:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_lines.append(
            f"{ts} artifacts: {removed_count} dirs / {removed_kb // 1024} MB"
        )
    return removed_count, removed_kb, notes


# ─────────────────────────── environments scope ────────────────────────
def _scan_environments(root: Path) -> tuple[int, list[tuple[Path, int]]]:
    """Advisory-only: venv/.venv + product-level node_modules. NEVER swept."""
    entries: list[tuple[Path, int]] = []
    total_kb = 0
    worktrees = root / ".claude" / "worktrees"

    venvs: list[Path] = []
    for name in (".venv", "venv"):
        for d in root.rglob(name):
            if not d.is_dir():
                continue
            if d == worktrees or worktrees in d.parents:
                continue
            venvs.append(d)
    for d in sorted(venvs)[:50]:
        kb = _du_kb(d)
        if kb <= 0:
            continue
        total_kb += kb
        entries.append((d, kb))

    nm: list[Path] = []
    for base in (root / "products", root / "seed"):
        if not base.is_dir():
            continue
        for d in base.rglob("node_modules"):
            if not d.is_dir():
                continue
            rel = d.relative_to(base)
            if len(rel.parts) > 4:
                continue
            # grep -v /node_modules/  → exclude nested node_modules
            if "node_modules" in [p for p in rel.parts[:-1]]:
                continue
            nm.append(d)
    for d in sorted(nm)[:50]:
        kb = _du_kb(d)
        if kb <= 0:
            continue
        total_kb += kb
        entries.append((d, kb))

    return total_kb // 1024, entries


# ──────────────────── worktree classification (parity) ─────────────────
# SINGLE SOURCE OF TRUTH used by both scan + sweep. Mirrors the bash
# `_classify_worktrees` + `_classify_emit_registered` exactly.
#
# Categories: STALE / STALE_LOCKED / STALE_DIRTY / ACTIVE / ORPHAN / PHANTOM.
# Record shape: (category, path:str, branch:str, reason:str).
def _classify_worktrees(root: Path) -> list[tuple[str, str, str, str]]:
    worktree_dir = root / ".claude" / "worktrees"
    records: list[tuple[str, str, str, str]] = []

    # Refresh origin/dev once for accurate merge detection. Engineer worktrees
    # integrate to the dev integration branch, not main
    # (KB § PATTERNS/branching-and-merging.md § 0).
    _git(root, "fetch", "origin", "dev", "--quiet")

    # Resolve the merged-base (prefer origin/dev, fall back to dev) + the
    # merged predicate via the shared _worktree_staleness helper — the single
    # source of truth shared with noctus.dev.cleanup_stale_worktrees.
    wts_run = wts.make_subprocess_runner(root, timeout=60)
    base = wts.resolve_merged_base(wts_run)

    # Snapshot main repo stash hashes (THE-P11 shared-stash false positive).
    main_stashes: set[str] = set()
    sp = _git(REPO_ROOT, "stash", "list", "--pretty=%H")
    if sp.returncode == 0:
        main_stashes = {ln.strip() for ln in sp.stdout.splitlines() if ln.strip()}

    seen_paths: set[str] = set()

    # Pass 1: walk registered worktrees.
    porcelain = _git(root, "worktree", "list", "--porcelain")
    wt = ""
    branch = ""
    locked = False
    lines = porcelain.stdout.splitlines() if porcelain.returncode == 0 else []

    def _flush() -> None:
        nonlocal wt, branch, locked
        if wt and branch:
            _classify_emit_registered(
                root, worktree_dir, wt, branch, locked,
                records, seen_paths, main_stashes, wts_run, base,
            )

    for line in lines:
        if line.startswith("worktree "):
            _flush()
            wt = line[len("worktree "):]
            branch = ""
            locked = False
        elif line.startswith("branch "):
            branch = line[len("branch refs/heads/"):]
        elif line.startswith("locked"):
            locked = True
            # Auto-unlock dead-pid locks (THE-P11, 2026-05-12).
            if "(pid " in line:
                pid = line.split("(pid ", 1)[1].split(")", 1)[0].strip()
                if pid and not _pid_alive(pid):
                    if _git(root, "worktree", "unlock", wt).returncode == 0:
                        locked = False
        elif line == "":
            if wt and branch:
                _flush()
                wt = ""
                branch = ""
                locked = False
    _flush()

    # Pass 2: on-disk agent-* dirs not in the seen set → ORPHAN.
    if worktree_dir.is_dir():
        for d in worktree_dir.iterdir():
            if not d.is_dir():
                continue
            if not d.name.startswith("agent-"):
                continue
            if str(d) not in seen_paths:
                records.append(
                    (
                        "ORPHAN",
                        str(d),
                        "-",
                        "on-disk but not git-registered (safe to rm -rf)",
                    )
                )
    return records


def _pid_alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def _classify_emit_registered(
    root: Path,
    worktree_dir: Path,
    wt: str,
    branch: str,
    locked: bool,
    records: list[tuple[str, str, str, str]],
    seen_paths: set[str],
    main_stashes: set[str],
    wts_run: wts.GitRunner,
    base: str,
) -> None:
    # Filter: only agent-* worktrees under WORKTREE_DIR. Non-agent paths
    # (main repo, sibling workspaces) ignored entirely.
    agent_prefix = str(worktree_dir / "agent-")
    if not wt.startswith(agent_prefix):
        return

    # Record we've seen this path BEFORE the self-skip — Pass 2 must not
    # mis-flag the engineer's OWN worktree as ORPHAN.
    seen_paths.add(wt)

    # Skip the worktree we're running from (REPO_ROOT may == an agent worktree).
    if wt == str(root):
        return

    # Merge check (shared _worktree_staleness helper): ancestry OR patch-id
    # (`git cherry`) equivalence vs the dev integration base. BEFORE the
    # on-disk check so an unmerged phantom is ACTIVE not PHANTOM.
    merged = wts.is_merged(wts_run, branch, base)

    if not merged:
        records.append(
            (
                "ACTIVE",
                wt,
                branch,
                "branch has unmerged commits (work-in-progress)",
            )
        )
        return

    # On-disk check (after merge — only PHANTOM-classify merged ones).
    if not Path(wt).is_dir():
        records.append(
            (
                "PHANTOM",
                wt,
                branch,
                "registered + merged but on-disk dir missing (safe to remove)",
            )
        )
        return

    # Merged. Check uncommitted / stashes / lock.
    st = _git(Path(wt), "status", "--porcelain")
    dirty = len([ln for ln in st.stdout.splitlines() if ln]) if st.returncode == 0 else 0

    sl = _git(Path(wt), "stash", "list", "--pretty=%H")
    if sl.returncode == 0:
        wt_stashes = {ln.strip() for ln in sl.stdout.splitlines() if ln.strip()}
        stashes = len(wt_stashes - main_stashes)
    else:
        stashes = 0

    if dirty != 0:
        records.append(
            (
                "STALE_DIRTY",
                wt,
                branch,
                f"{dirty} uncommitted file(s) — INVESTIGATE before removing",
            )
        )
    elif stashes != 0:
        records.append(
            (
                "STALE_DIRTY",
                wt,
                branch,
                f"{stashes} stash(es) — recover before removing",
            )
        )
    elif locked:
        records.append(
            (
                "STALE_LOCKED",
                wt,
                branch,
                "locked (clean dir) — safe to unlock+remove after PID check",
            )
        )
    else:
        records.append(
            (
                "STALE",
                wt,
                branch,
                "branch merged to origin/dev; safe to remove",
            )
        )


def _scan_worktrees(root: Path) -> tuple[int, dict[str, int], list[tuple[str, str, str, str]]]:
    """Return (actionable_count, tally, records). Actionable = STALE+ORPHAN+PHANTOM."""
    worktree_dir = root / ".claude" / "worktrees"
    if not worktree_dir.is_dir():
        return 0, {}, []
    records = _classify_worktrees(root)
    tally = {
        "STALE": 0,
        "STALE_LOCKED": 0,
        "STALE_DIRTY": 0,
        "ACTIVE": 0,
        "ORPHAN": 0,
        "PHANTOM": 0,
    }
    for cat, *_rest in records:
        if cat in tally:
            tally[cat] += 1
    actionable = tally["STALE"] + tally["ORPHAN"] + tally["PHANTOM"]
    return actionable, tally, records


def _sweep_worktrees(
    root: Path,
    dry_run: bool,
    records: list[tuple[str, str, str, str]],
    log_lines: list[str],
) -> tuple[int, int, int, int, list[str]]:
    target = [r for r in records if r[0] in ("STALE", "ORPHAN", "PHANTOM")]
    skipped = [
        r for r in records if r[0] in ("STALE_LOCKED", "STALE_DIRTY", "ACTIVE")
    ]
    notes: list[str] = []
    if not target:
        return 0, 0, 0, len(skipped), notes
    if dry_run:
        for cat, path, branch, reason in target:
            notes.append(f"[{cat}] {path} (branch: {branch}) — {reason}")
        return 0, 0, len(target), len(skipped), notes

    removed = 0
    failed = 0
    for cat, path, _branch, _reason in target:
        if cat in ("STALE", "PHANTOM"):
            if _git(root, "worktree", "remove", "--force", path).returncode == 0:
                removed += 1
            else:
                # Lock raced between classify and act — do NOT rm -rf
                # (KB § PATTERNS/storage-hygiene.md §2.3 — THE-P10 incident).
                notes.append(
                    f"WARN: git refused to remove {path} "
                    "(lock raced between scan and sweep)"
                )
                failed += 1
        elif cat == "ORPHAN":
            try:
                shutil.rmtree(path)
                removed += 1
            except OSError:
                failed += 1
    _git(root, "worktree", "prune")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_lines.append(
        f"{ts} worktrees: removed={removed} failed={failed} "
        f"targeted={len(target)} skipped={len(skipped)}"
    )
    return removed, failed, len(target), len(skipped), notes


# ─────────────────────── severity / next_action ────────────────────────
def _grade_severity(artifacts_mb: int, worktree_count: int) -> str:
    if (
        artifacts_mb >= ARTIFACT_CRITICAL_MB
        or worktree_count >= WORKTREE_CRITICAL_COUNT
    ):
        return "CRITICAL"
    if (
        artifacts_mb >= ARTIFACT_WARNING_MB
        or worktree_count >= WORKTREE_WARNING_COUNT
    ):
        return "WARNING"
    return "OK"


def _next_action(artifacts_mb: int, worktree_count: int, envs_mb: int) -> str:
    if worktree_count >= WORKTREE_CRITICAL_COUNT:
        return (
            f"worktrees: {worktree_count} stale → "
            "noctus.dev.mole(mode='sweep', scope='worktrees', force=True)"
        )
    if artifacts_mb >= ARTIFACT_CRITICAL_MB:
        return (
            f"artifacts: {artifacts_mb} MB → "
            "noctus.dev.mole(mode='sweep', scope='artifacts', force=True)"
        )
    if worktree_count >= WORKTREE_WARNING_COUNT:
        return (
            f"worktrees: {worktree_count} stale → "
            "noctus.dev.mole(mode='sweep', scope='worktrees', force=True)"
        )
    if artifacts_mb >= ARTIFACT_WARNING_MB:
        return f"artifacts: {artifacts_mb} MB → noctus.dev.mole(mode='sweep', scope='artifacts')"
    if envs_mb > 3000:
        return (
            f"environments: {envs_mb} MB (advisory — pnpm-workspace "
            "candidate; see KB § PATTERNS/storage-hygiene.md §2.2)"
        )
    return "ok — nothing to do"


# ──────────────────────────── public entry ─────────────────────────────
def run_mole(
    mode: Literal["scan", "sweep"] = "scan",
    scope: Literal["all", "artifacts", "environments", "worktrees"] = "all",
    force: bool = False,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Native-Python storage-hygiene mole. Behaviour-identical to the
    former `scripts/mole.sh` subprocess.

    `force` is honored ONLY with `mode="sweep"` — and even then the
    safe-gate (see module docstring) is the real guard. `scan` is always
    read-only. `sweep` without `force` is a dry-run.
    """
    try:
        root = (
            resolve_caller_root(worktree_path) if worktree_path else REPO_ROOT
        )
        root = Path(root)
    except Exception as exc:  # noqa: BLE001 — surface, never silently fallback
        return {"ok": False, "error": f"cannot resolve root: {exc}", "executed": False}

    if not (root / ".git").exists():
        return {
            "ok": False,
            "error": f"not inside a git repo: {root}",
            "executed": False,
        }

    do_artifacts = scope in ("all", "artifacts")
    do_environments = scope in ("all", "environments")
    do_worktrees = scope in ("all", "worktrees")

    will_delete = mode == "sweep" and force
    dry_run = mode == "sweep" and not force

    artifacts_mb = 0
    environments_mb = 0
    worktrees_actionable = 0
    stderr_lines: list[str] = []
    log_lines: list[str] = []
    records: list[tuple[str, str, str, str]] = []

    try:
        if mode in ("scan",):
            if do_artifacts:
                artifacts_mb, art_entries = _scan_artifacts(root)
                stderr_lines.append(
                    f"ARTIFACTS: {len(art_entries)} dirs / {artifacts_mb} MB"
                )
            if do_environments:
                environments_mb, env_entries = _scan_environments(root)
                stderr_lines.append(
                    f"ENVIRONMENTS (advisory): {len(env_entries)} / "
                    f"{environments_mb} MB"
                )
            if do_worktrees:
                worktrees_actionable, tally, records = _scan_worktrees(root)
                stderr_lines.append(
                    "WORKTREES: " + " ".join(f"{k}={v}" for k, v in tally.items())
                )
        elif mode == "sweep":
            if do_artifacts:
                rc, rkb, notes = _sweep_artifacts(root, dry_run, log_lines)
                stderr_lines.extend(notes)
                if not dry_run:
                    stderr_lines.append(
                        f"artifacts removed: {rc} dirs / {rkb // 1024} MB"
                    )
                # Re-scan for the result-shape size figure.
                artifacts_mb, _ = _scan_artifacts(root)
            if do_environments:
                stderr_lines.append(
                    "environments: NEVER auto-swept "
                    "(see KB § PATTERNS/storage-hygiene.md §3.2)"
                )
                environments_mb, _ = _scan_environments(root)
            if do_worktrees:
                _, _tally, records = _scan_worktrees(root)
                removed, failed, ntarget, nskip, notes = _sweep_worktrees(
                    root, dry_run, records, log_lines
                )
                stderr_lines.extend(notes)
                stderr_lines.append(
                    f"worktrees: target={ntarget} skipped={nskip} "
                    f"removed={removed} failed={failed}"
                )
                # Recompute actionable post-sweep for the result figure.
                worktrees_actionable, _, _ = _scan_worktrees(root)
        else:
            return {
                "ok": False,
                "error": f"unknown mode: {mode}",
                "executed": False,
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git operation timed out", "executed": False}

    # Persist sweep log (parity with $LOG_FILE append).
    if log_lines:
        try:
            log_file = root / "scripts" / "mole-last-sweep.log"
            with log_file.open("a", encoding="utf-8") as fh:
                for ln in log_lines:
                    fh.write(ln + "\n")
        except OSError:
            pass

    severity = _grade_severity(artifacts_mb, worktrees_actionable)
    na = _next_action(artifacts_mb, worktrees_actionable, environments_mb)

    return {
        "ok": True,
        "mode": mode,
        "scope": scope,
        "executed_destructive": will_delete,
        "dry_run": dry_run,
        "exit_code": 0,
        "severity": severity,
        "artifacts_mb": artifacts_mb,
        "environments_mb": environments_mb,
        "worktrees_stale": worktrees_actionable,
        "next_action": na,
        "safe_gate": _SAFE_GATE,
        "stderr_tail": "\n".join(stderr_lines[-12:]),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.mole",
        description=(
            "Storage-hygiene mole (custodial sibling of keeper/hound). "
            "`mode='scan'` (default, READ-ONLY) reports artifacts/env/"
            "worktree waste + severity + next_action. `mode='sweep'` "
            "removes it — but ONLY with `force=True`; without force it is "
            "a DRY-RUN. SAFE-GATE: never deletes uncommitted / unmerged / "
            "main / sibling / .env / migration content; removes a worktree "
            "only when its branch is merged-to-dev by SHA-ancestry OR "
            "patch-id (shares the _worktree_staleness predicate with "
            "noctus.dev.cleanup_stale_worktrees). Caller's extra duty: "
            "confirm no other agent is mid-flight in a target worktree "
            "before force-sweeping. Project cleanup is the separate "
            "noctus.dev.archive tool. Pass worktree_path when called from "
            "inside a git worktree. See KB § PATTERNS/storage-hygiene.md."
        ),
    )
    def _mole(
        mode: Literal["scan", "sweep"] = "scan",
        scope: Literal["all", "artifacts", "environments", "worktrees"] = "all",
        force: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return run_mole(
            mode=mode, scope=scope, force=force, worktree_path=worktree_path
        )


__all__ = ["run_mole", "register"]
