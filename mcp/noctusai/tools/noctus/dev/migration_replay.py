"""noctus.dev.migration_replay — replay a product's migration chain on a fresh PGlite.

**The gap it closes.** Every migration gate we had was static (keepers parse the SQL)
or ran against PRODUCTION (``migrate_product``, ``verify_db_guards``). Nothing ever
executed a chain on a real Postgres before prod did, so a migration that only breaks
when it RUNS reached prod first — SW 231 v1 (2026-10-10) refused its own backfill
with 23514 because it ran the UPDATE under the CHECK it was about to replace.

**What it does.** A fresh PGlite (real PG16 compiled to WASM, in-process, no server)
gets the versioned Supabase-surface stubs (``mcp/noctusai/node/migration_replay/
stubs.sql``), then — core FIRST, since every product's 001 references core's public
tables — the product's chain:

- **history** (every file the change does not touch): statement-level, in order, so
  one failure never hides its neighbours. Each failure is compared with the
  product's known residue (``products/<slug>/backend/migration-replay.json``); only a
  failure NOT in the residue is red.
- **targets** (new/changed files): the WHOLE file in one simple-query call, exactly
  how ``migrate_product`` sends it to Supabase (implicit transaction), then a SECOND
  time — a migration that cannot be re-applied is red (idempotency).
- **fixtures** (per-product ``fixtures`` in the same JSON): prod-shaped rows inserted
  just before a named file, so a migration must survive the data it will meet — a
  fresh DB is empty, and an empty table never trips a CHECK.

**Verdicts.** ``green`` | ``red`` | ``inconclusive``. The harness failing to MEASURE
(no ``node``, PGlite not installed, stubs not loading, a crash, a timeout) is
``inconclusive`` — never green, never a product verdict.

KB § PATTERNS/backend/migration-chain-replay.md.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from settings import REPO_ROOT  # noqa: E402  (path constants)

logger = logging.getLogger(__name__)

NODE_DIR = Path("mcp/noctusai/node")
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
CONFIG_NAME = "migration-replay.json"
CORE = "core"
DEFAULT_TIMEOUT_S = 900

# Every residue entry names its destination; an entry whose class is not declared
# here is refused (a deferral without a destination is a silent error).
#
# NOC-REMEDIATE[migration-chain-rebaseline]: core 001 / SW 001 were rewritten to the current state while the later deltas stayed (core 002 re-creates 001's policies, core 027 renames columns 001 already renamed, SW 001 forward-references 005+ tables and re-creates its youtube policies); applied files are immutable (ledger checksum), so the fix is a chain rebaseline, not an edit — 2026-10-10
# NOC-REMEDIATE[mailing-schema-migration]: the legacy `mailing` schema existed in prod with no migration creating it; SW 236 (2026-10-10) now declares it, so fresh chains have it — but SW 012/212/214 run BEFORE 236 and still fail on a fresh chain, so these residue entries resolve only with a chain rebaseline — 2026-10-10
# NOC-REMEDIATE[erp-asleep-owner]: SW 011 alters the `erp` schema owned by erp-imobiliario, which is asleep (not in the active scope), so its chain is never replayed before SW — resolves when erp wakes or SW 011's erp leg is guarded — 2026-10-10
REMEDIATE_CLASSES = frozenset({
    "migration-chain-rebaseline",
    "mailing-schema-migration",
    "erp-asleep-owner",
})


def _root(root: Path | str | None) -> Path:
    return Path(root) if root else Path(REPO_ROOT)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def _migration_dir(slug: str) -> str:
    return f"products/{slug}/backend/migrations"


def _ordered(names: list[str]) -> list[str]:
    """migrate_product's apply order: numbered direct children, by number, then name."""
    from tools.noctus.dev.migrate_product import _NN_RE

    numbered = []
    for name in names:
        m = _NN_RE.match(name)
        if m and name.endswith(".sql"):
            numbered.append((int(m.group(1)), name))
    return [n for _, n in sorted(numbered)]


def chain_files(root: Path, slug: str, source: str = "worktree") -> list[tuple[str, str]]:
    """``[(filename, sql)]`` in apply order. ``source``: ``worktree`` | ``index`` | a git sha."""
    rel = _migration_dir(slug)
    if source == "worktree":
        d = root / rel
        if not d.is_dir():
            return []
        names = [p.name for p in d.iterdir() if p.is_file()]
        return [(n, (d / n).read_text(encoding="utf-8")) for n in _ordered(names)]
    if source == "index":
        listing = _git(root, "ls-files", "--", rel).splitlines()
        prefix = ":"
    else:
        listing = _git(root, "ls-tree", "--name-only", "-r", source, "--", rel).splitlines()
        prefix = f"{source}:"
    names = [p.rpartition("/")[2] for p in listing if p.rpartition("/")[0] == rel]
    return [(n, _git(root, "show", f"{prefix}{rel}/{n}")) for n in _ordered(names)]


def load_config(root: Path, slug: str, source: str = "worktree") -> dict:
    rel = f"products/{slug}/backend/{CONFIG_NAME}"
    try:
        if source == "worktree":
            p = root / rel
            raw = p.read_text(encoding="utf-8") if p.exists() else None
        else:
            prefix = ":" if source == "index" else f"{source}:"
            try:
                raw = _git(root, "show", f"{prefix}{rel}")
            except RuntimeError:
                raw = None
    except OSError as exc:
        raise ValueError(f"{rel}: unreadable ({exc})") from exc
    if raw is None:
        return {"residue": [], "fixtures": []}
    cfg = json.loads(raw)
    for entry in cfg.get("residue", []):
        cls = entry.get("remediate")
        if cls not in REMEDIATE_CLASSES:
            raise ValueError(
                f"{rel}: residue entry {entry.get('file')!r} names remediate class {cls!r}, "
                f"which is not declared in migration_replay.REMEDIATE_CLASSES — every "
                f"known failure needs a NOC-REMEDIATE destination."
            )
    cfg.setdefault("residue", [])
    cfg.setdefault("fixtures", [])
    return cfg


def products_for_paths(paths: list[str]) -> list[str]:
    """Product slugs whose migration chain (or replay config) a path touches."""
    slugs = []
    for p in paths:
        parts = p.split("/")
        if len(parts) >= 4 and parts[0] == "products" and parts[2] == "backend" and (
            (len(parts) == 5 and parts[3] == "migrations" and p.endswith(".sql"))
            or (len(parts) == 4 and parts[3] == CONFIG_NAME)
        ):
            if parts[1] not in slugs:
                slugs.append(parts[1])
    return slugs


def _steps_for(root: Path, slug: str, targets: set[str], source: str, overrides: dict[str, str]) -> list[dict]:
    """Core-first step list for ONE product replay."""
    chain = [CORE, slug] if slug != CORE else [CORE]
    steps: list[dict] = []
    for owner in chain:
        cfg = load_config(root, owner, source)
        fixtures: dict[str, list[dict]] = {}
        for fx in cfg["fixtures"]:
            fixtures.setdefault(fx["before"], []).append(fx)
        for name, sql in chain_files(root, owner, source):
            rel = f"{_migration_dir(owner)}/{name}"
            sql = overrides.get(rel, sql)
            for fx in fixtures.get(name, []):
                steps.append({"product": owner, "file": f"fixture:{name}", "sql": fx["sql"], "mode": "file", "twice": False})
            is_target = owner == slug and rel in targets
            steps.append({
                "product": owner, "file": name, "sql": sql,
                "mode": "file" if is_target else "statements", "twice": is_target,
            })
    return steps


def _run_harness(steps: list[dict], timeout_s: int, node_bin: str | None) -> dict:
    """Run the node half from the TOOLKIT's own install (never the replayed tree's)."""
    toolkit = Path(REPO_ROOT)
    node = node_bin or shutil.which("node")
    if node is None:
        return {"ok": False, "error": "`node` not on PATH"}
    harness = toolkit / HARNESS
    if not harness.exists():
        return {"ok": False, "error": f"{HARNESS} missing"}
    payload = json.dumps({"stubs": (toolkit / STUBS).read_text(encoding="utf-8"), "steps": steps})
    try:
        proc = subprocess.run(
            [node, str(harness)], input=payload, capture_output=True, text=True,
            cwd=toolkit / NODE_DIR, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"harness exceeded {timeout_s}s"}
    except OSError as exc:
        return {"ok": False, "error": f"cannot start node ({node}): {exc}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"harness exit {proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}"}


def _judge(slug: str, result: dict, residues: dict[str, list[dict]]) -> dict:
    """Compare one product replay's failures with the residue of each owning product."""
    observed: Counter = Counter()
    target_failures: list[dict] = []
    for step in result["steps"]:
        for f in step["failures"]:
            if step["mode"] == "file":
                target_failures.append({"product": step["product"], "file": step["file"], **f})
            else:
                observed[(step["product"], step["file"], f["error"])] += 1
    known: Counter = Counter()
    for owner, entries in residues.items():
        for e in entries:
            known[(owner, e["file"], e["error"])] += int(e.get("count", 1))
    new = [
        {"product": p, "file": f, "error": e, "count": n - known.get((p, f, e), 0)}
        for (p, f, e), n in sorted(observed.items()) if n > known.get((p, f, e), 0)
    ]
    resolved = [
        {"product": p, "file": f, "error": e, "count": n - observed.get((p, f, e), 0)}
        for (p, f, e), n in sorted(known.items()) if observed.get((p, f, e), 0) < n
    ]
    return {
        "product": slug,
        "verdict": "red" if (new or target_failures) else "green",
        "statements": sum(s["statements"] for s in result["steps"]),
        "new_failures": new,
        "target_failures": target_failures,
        "known_residue": sum(min(n, known.get(k, 0)) for k, n in observed.items()),
        "resolved_residue": resolved,
    }


def migration_replay(
    products: list[str] | None = None,
    paths: list[str] | None = None,
    *,
    source: str = "worktree",
    overrides: dict[str, str] | None = None,
    root: Path | str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    active_only: bool = True,
    node_bin: str | None = None,
) -> dict[str, Any]:
    """Replay chains on PGlite and judge them. ``paths`` = the changed files (targets);
    ``products`` defaults to the ones ``paths`` touch. Returns ``{status, products, ...}``."""
    root = _root(root)
    paths = list(paths or [])
    overrides = dict(overrides or {})
    slugs = list(products or products_for_paths(paths + list(overrides)))
    skipped: list[str] = []
    if active_only:
        from tools.noctus.dev.product_scope import filter_active

        active = set(filter_active(slugs, root))
        skipped = [s for s in slugs if s not in active]
        slugs = [s for s in slugs if s in active]
    if not slugs:
        return {"status": "green", "products": [], "skipped_asleep": skipped,
                "message": "no active product chain touched"}
    targets = {p for p in paths + list(overrides) if p.endswith(".sql")}
    reports = []
    for slug in slugs:
        t0 = time.monotonic()
        try:
            steps = _steps_for(root, slug, targets, source, overrides)
            residues = {o: load_config(root, o, source)["residue"] for o in {CORE, slug}}
        except (ValueError, RuntimeError, OSError) as exc:
            reports.append({"product": slug, "verdict": "inconclusive", "error": str(exc)})
            continue
        result = _run_harness(steps, timeout_s, node_bin)
        if not result.get("ok"):
            reports.append({"product": slug, "verdict": "inconclusive", "error": result.get("error")})
            continue
        report = _judge(slug, result, residues)
        report["seconds"] = round(time.monotonic() - t0, 1)
        report["pglite"] = result.get("pglite")
        reports.append(report)
    verdicts = {r["verdict"] for r in reports}
    status = "inconclusive" if "inconclusive" in verdicts else ("red" if "red" in verdicts else "green")
    return {"status": status, "products": reports, "skipped_asleep": skipped}


def changed_migration_paths(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """Migration/config paths changed in ``base..head`` (the CI push range)."""
    out = _git(root, "diff", "--name-only", "--diff-filter=ACMR", f"{base}..{head}")
    return [p for p in out.splitlines() if products_for_paths([p])]


def format_report(r: dict) -> str:
    lines = [f"migration_replay: {r['status'].upper()}"]
    for p in r["products"]:
        if p["verdict"] == "inconclusive":
            lines.append(f"  {p['product']}: INCONCLUSIVE — {p.get('error')}")
            continue
        lines.append(
            f"  {p['product']}: {p['verdict']} · {p['statements']} stmts · "
            f"{p['known_residue']} known residue · {p.get('seconds')}s"
        )
        for f in p["target_failures"]:
            lines.append(f"    ✗ {f['product']}/{f['file']} [{f['phase']}] {f.get('code') or ''} {f['error']}")
        for f in p["new_failures"]:
            lines.append(f"    ✗ NEW {f['product']}/{f['file']} ×{f['count']}: {f['error']}")
        for f in p["resolved_residue"]:
            lines.append(f"    ↓ residue no longer seen (prune it): {f['product']}/{f['file']} ×{f['count']}: {f['error']}")
    if r.get("skipped_asleep"):
        lines.append(f"  skipped (asleep): {', '.join(r['skipped_asleep'])}")
    return "\n".join(lines)


def register(server) -> None:
    @server.tool(
        name="noctus.dev.migration_replay",
        description=(
            "Replay product migration chains on a fresh PGlite (real PG16/WASM) with "
            "versioned Supabase-surface stubs, core first. History files replay "
            "statement-level and are judged against the product's known residue "
            "(products/<slug>/backend/migration-replay.json — every entry carries a "
            "NOC-REMEDIATE destination); new/changed files (`paths`) apply as a whole "
            "file like migrate_product does, then a SECOND time (idempotency). "
            "Per-product fixtures insert prod-shaped rows before a named file. "
            "status: green | red | inconclusive (harness could not measure — never green). "
            "`source`: worktree | index | <sha>. KB § PATTERNS/backend/migration-chain-replay.md."
        ),
    )
    def _migration_replay(
        products: list[str] | None = None,
        paths: list[str] | None = None,
        source: str = "worktree",
        base: str | None = None,
    ) -> dict:
        root = _root(None)
        if base:
            paths = (paths or []) + changed_migration_paths(root, base)
        return migration_replay(products, paths, source=source, root=root)


__all__ = [
    "REMEDIATE_CLASSES",
    "chain_files",
    "changed_migration_paths",
    "format_report",
    "load_config",
    "migration_replay",
    "products_for_paths",
    "register",
]
