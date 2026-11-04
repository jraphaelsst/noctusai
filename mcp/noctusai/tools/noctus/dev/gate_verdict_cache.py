"""Gate verdict cache — reuse a GREEN gate verdict on identical inputs.

Why (2026-11-04, noctusai-04, a fleet train on integrate attempt 7, owner:
"fix it so it stops drifting"): every integrate retry re-ran ALL ~30 merged-tip
gates from zero (~45 min), including the ones already green on the very same
inputs. Each retry was a fresh lottery against machine load, re-rolled on a
moving `dev`. With this cache a retry runs only the gates whose inputs changed,
or that were red / produced no verdict last time.

Key = sha256 of:
  * the gate name, argv and cwd (relative to the repo root);
  * the git TREE ids, at HEAD, of the gate's input closure (below) plus every
    root-level tracked file (lockfiles, configs);
  * a runner fingerprint: gate_sweep / harness_signatures source, the test
    interpreter and `node` (path + mtime), the e2e CI flag, and the per-job
    worker cap.

Input closure — deliberately coarse, so a stale green cannot leak:
  * product gates (`pytest|vite_build|vitest|e2e:<slug>`):
    products/<slug>/, seed/, templates/, deploy/
  * seed gates (`pytest|vitest:seed/...`): seed/, templates/
  * anything else (mcp toolkit, keepers, contracts...): NOT cached. Those read
    across the whole repo, so they always re-run.

A product test that reads a path outside its closure would be the hole. The
kill switch is `NOCTUS_GATE_VERDICT_CACHE=off`.

Only an unambiguous GREEN is stored: ran, exit 0, and no harness_suspect,
harness_invalid, timed_out, waiting_for_slot, or false_red / flaky_under_load
(a flaky green is not reused). A tree with uncommitted changes in the closure
is never looked up or stored — the key describes HEAD, not the working tree.

Store: append-only ndjson at ~/.noctus/gate-verdicts.ndjson (override:
NOCTUS_GATE_VERDICT_CACHE=<path>). Machine-local by design: the fingerprint
includes local interpreter paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_PRODUCT_KINDS = ("pytest", "vite_build", "vitest", "e2e")
_NOT_GREEN_KEYS = ("harness_suspect", "harness_invalid", "timed_out", "waiting_for_slot",
                   "false_red", "flaky_under_load")
_RUNNER_FILES = ("gate_sweep.py", "harness_signatures.py")
_LOOKBACK_LINES = 20000

GitFn = Callable[[list[str]], "tuple[int, str]"]


def cache_path() -> Path | None:
    """None when disabled (`NOCTUS_GATE_VERDICT_CACHE=off|0|false`)."""
    raw = (os.environ.get("NOCTUS_GATE_VERDICT_CACHE") or "").strip()
    if raw.lower() in ("off", "0", "false", "no"):
        return None
    return Path(raw) if raw else Path.home() / ".noctus" / "gate-verdicts.ndjson"


def input_closure(gate: str) -> list[str] | None:
    """Repo-relative paths a gate's verdict depends on, or None = never cached."""
    kind, _, target = gate.partition(":")
    if kind not in _PRODUCT_KINDS or not target:
        return None
    if target.startswith("seed/"):
        return ["seed", "templates"]
    if "/" in target:
        return None
    return [f"products/{target}", "seed", "templates", "deploy"]


def is_cacheable_green(entry: dict[str, Any]) -> bool:
    return (entry.get("ran") is True and entry.get("exit_code") == 0
            and not any(entry.get(k) not in (None, False) for k in _NOT_GREEN_KEYS))


def _file_stamp(path: str | None) -> str:
    if not path:
        return "absent"
    try:
        return f"{path}@{os.stat(path).st_mtime_ns}"
    except OSError:
        return f"{path}@missing"


class GateVerdictCache:
    def __init__(self, root: Path, *, path: Path | None = None, git: GitFn | None = None,
                 runner_fingerprint: str | None = None, now: Callable[[], datetime] | None = None):
        self.root = Path(root)
        self.path = path
        self._git = git or self._real_git
        self._lock = threading.Lock()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._fp = runner_fingerprint
        self._head: str | None = None
        self._root_files: str | None = None
        self.hits: list[str] = []

    # -- seams -------------------------------------------------------------
    def _real_git(self, args: list[str]) -> "tuple[int, str]":
        p = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        return p.returncode, p.stdout

    def _runner_fingerprint(self) -> str:
        if self._fp is None:
            here = Path(__file__).resolve().parent
            h = hashlib.sha256()
            for name in _RUNNER_FILES:
                try:
                    h.update((here / name).read_bytes())
                except OSError:
                    h.update(f"{name}:missing".encode())
            self._fp = h.hexdigest()
        return self._fp

    # -- key ---------------------------------------------------------------
    def _head_sha(self) -> str | None:
        if self._head is None:
            rc, out = self._git(["rev-parse", "HEAD"])
            self._head = out.strip() if rc == 0 and out.strip() else ""
        return self._head or None

    def _tree_id(self, rel: str) -> str:
        rc, out = self._git(["rev-parse", f"HEAD:{rel}"])
        return out.strip() if rc == 0 and out.strip() else "absent"

    def _root_files_id(self) -> str:
        if self._root_files is None:
            rc, out = self._git(["ls-tree", "HEAD"])
            blobs = sorted(ln for ln in out.splitlines() if "\tblob " not in ln and " blob " in ln)
            self._root_files = hashlib.sha256("\n".join(blobs).encode()).hexdigest() if rc == 0 else ""
        return self._root_files

    def _dirty(self, closure: list[str]) -> bool:
        rc, out = self._git(["status", "--porcelain", "--untracked-files=no", "--", *closure])
        if rc != 0:
            return True                      # cannot tell -> treat as dirty (never cache)
        if out.strip():
            return True
        rc, out = self._git(["status", "--porcelain", "--untracked-files=no"])
        return rc != 0 or any("/" not in ln[3:] for ln in out.splitlines() if ln.strip())

    def key(self, spec: Any, job_workers: int | None = None) -> str | None:
        closure = input_closure(spec.gate)
        if closure is None or self._head_sha() is None or not self._root_files_id():
            return None
        if self._dirty(closure):
            return None
        try:
            cwd = str(Path(spec.cwd).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return None
        argv0 = spec.argv[0] if spec.argv else ""
        parts = {
            "gate": spec.gate, "argv": list(spec.argv), "cwd": cwd,
            "trees": {p: self._tree_id(p) for p in closure},
            "root_files": self._root_files_id(),
            "runner": self._runner_fingerprint(),
            "interp": _file_stamp(shutil.which(argv0) or argv0) if argv0 else "none",
            "node": _file_stamp(shutil.which("node")),
            "ci": spec.gate.startswith("e2e:"),
            "job_workers": job_workers,
        }
        return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    # -- store -------------------------------------------------------------
    def lookup(self, spec: Any, job_workers: int | None = None) -> dict[str, Any] | None:
        if self.path is None or not self.path.exists():
            return None
        k = self.key(spec, job_workers)
        if k is None:
            return None
        with self._lock:
            lines = self.path.read_text().splitlines()[-_LOOKBACK_LINES:]
        for ln in reversed(lines):
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if row.get("key") == k:
                self.hits.append(spec.gate)
                return {
                    "gate": spec.gate, "ran": True, "exit_code": 0, "duration_s": 0.0,
                    "summary": (f"cached green - identical inputs passed at {row.get('tip', '?')[:9]} "
                                f"({row.get('ts')}); original: {row.get('summary', '')}")[:600],
                    "cached_from": {"tip": row.get("tip"), "ts": row.get("ts"), "key": k[:16],
                                    "duration_s": row.get("duration_s")},
                }
        return None

    def store(self, spec: Any, entry: dict[str, Any], job_workers: int | None = None) -> bool:
        if self.path is None or entry.get("cached_from") or not is_cacheable_green(entry):
            return False
        k = self.key(spec, job_workers)
        if k is None:
            return False
        row = {"key": k, "gate": spec.gate, "tip": self._head_sha(),
               "ts": self._now().isoformat(timespec="seconds"),
               "duration_s": entry.get("duration_s"), "summary": str(entry.get("summary", ""))[:300]}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True


def make_cache(root: Path) -> GateVerdictCache | None:
    """The real cache for `root`, or None when disabled."""
    p = cache_path()
    return GateVerdictCache(root, path=p) if p is not None else None
