"""Keeper-delta gate — run ONLY the keepers a diff added or changed, over the
whole tree, against the committed compliance baseline (2026-10-10).

WHY. A new or edited `check_*` keeper can go red on EXISTING files the branch
never touched (2026-10-10: `check_migration_number_refs_in_tests` landed green
and dev CI went red on a social-wiring test it had never seen). The gate that
would catch it — `test_compliance.py::TestSeedCompliance::test_all_products_compliant`
— runs `check_all_products()` (every keeper × every product, ~4.5 min), which no
integrate budget fits, so it timed out unmeasured and integrate pushed.

This runs the SAME judgement on the SAME baseline, restricted to the keepers the
diff can have affected:

- **changed keepers** = top-level `check_*` functions in `compliance.py` whose
  AST differs from the merge-base version (or is new), plus every `check_*`
  that transitively calls a changed module-level helper.
- **how to call them** = DERIVED from `check_all_products()`'s own body: a call
  with the per-product loop variable is run once per ACTIVE product dir, a
  no-arg call once. A changed keeper the aggregator never calls is not part of
  the baseline gate — reported in `not_aggregated`, never silently passed.
- **verdict** = the high/critical, non-env-artifact fingerprints those keepers
  produce, minus `tests/compliance_baseline.json` — computed with the
  regenerator's own `fingerprint` / `is_env_artifact_issue` (one source of truth with
  `test_compliance.py`).

Gate: `gate_sweep`'s `keeper_delta` (scheduled FIRST when `compliance.py` is in
the diff). CLI: `--check-keeper-delta [--base-ref origin/dev]`.
KB § PATTERNS/compliance/compliance-regression-baseline.md.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

from . import symbol_scope

COMPLIANCE_REL = "mcp/noctusai/tools/noctus/dev/compliance.py"
_AGGREGATOR = "check_all_products"


def _top_level_functions(src: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(src)
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def changed_keepers(base_src: str | None, head_src: str) -> list[str]:
    """`check_*` functions (excluding the aggregator) the diff can have
    affected: every keeper that is, or transitively references, a top-level
    symbol whose AST changed — a function, a class, or a named constant (an
    allowlist edit changes what the keepers reading it report). Uses
    `symbol_scope`, the one "what did this diff change" mechanism the
    merged-tip mcp gate also scopes by.

    Falls back to EVERY keeper — never zero — when the change can't be
    attributed: the file is new (`base_src=None`), a side doesn't parse, a
    differing statement binds no name (an import, an `if` block), or the
    module reads its own names dynamically (`globals()`)."""
    head_fns = _top_level_functions(head_src)
    every = sorted(n for n in head_fns if n.startswith("check_") and n != _AGGREGATOR)
    if base_src is None:
        return every
    changed = symbol_scope.changed_by_ast(base_src, head_src)
    syms = symbol_scope._symbols(head_src)
    if changed is None or syms is None:
        return every
    affected = symbol_scope.closure(changed, syms)
    return sorted(n for n in affected
                  if n in head_fns and n.startswith("check_") and n != _AGGREGATOR)


def aggregator_call_shapes(head_src: str) -> dict[str, str]:
    """`{keeper: 'per_product' | 'global'}` for every keeper
    `check_all_products()` calls, read from its own AST: a call whose args
    include the per-product loop target is per-product, a no-arg call global."""
    fn = _top_level_functions(head_src).get(_AGGREGATOR)
    if fn is None:
        return {}
    loop_vars = {t.id for loop in ast.walk(fn) if isinstance(loop, ast.For)
                 for t in ast.walk(loop.target) if isinstance(t, ast.Name)}
    shapes: dict[str, str] = {}
    for call in ast.walk(fn):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id.startswith("check_")):
            continue
        uses_loop = any(isinstance(n, ast.Name) and n.id in loop_vars
                        for a in call.args for n in ast.walk(a))
        if uses_loop:
            shapes[call.func.id] = "per_product"
        elif not call.args and not call.keywords:
            shapes.setdefault(call.func.id, "global")
    return shapes


def _base_source(root: Path, base_ref: str) -> str | None:
    mb = subprocess.run(["git", "merge-base", base_ref, "HEAD"], cwd=root,
                        capture_output=True, text=True)
    if mb.returncode != 0:
        raise RuntimeError(f"git merge-base {base_ref} HEAD failed: {mb.stderr.strip()}")
    show = subprocess.run(["git", "show", f"{mb.stdout.strip()}:{COMPLIANCE_REL}"],
                          cwd=root, capture_output=True, text=True)
    return show.stdout if show.returncode == 0 else None


def _baseline_module(root: Path):
    """The regenerator `test_compliance.py` itself loads — same isolation idiom
    (importlib, no tests/-dir sys.path insert)."""
    path = root / "mcp" / "noctusai" / "tests" / "refresh_compliance_baseline.py"
    spec = importlib.util.spec_from_file_location("refresh_compliance_baseline", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def keeper_delta(root: Path, base_ref: str = "origin/dev") -> dict[str, Any]:
    """Run the changed keepers and diff their high/critical fingerprints
    against the committed baseline. `ok` is False iff a NEW fingerprint exists."""
    from tools.noctus.dev import compliance as c

    head_src = (root / COMPLIANCE_REL).read_text(encoding="utf-8")
    keepers = changed_keepers(_base_source(root, base_ref), head_src)
    shapes = aggregator_call_shapes(head_src)
    rcb = _baseline_module(root)
    baseline = set(json.loads(rcb.BASELINE_PATH.read_text(encoding="utf-8"))["fingerprints"])

    ran: list[str] = []
    not_aggregated: list[str] = []
    issues: list[dict] = []
    product_dirs = c._active_product_dirs(c.PRODUCTS_DIR)
    for name in keepers:
        shape = shapes.get(name)
        fn = getattr(c, name)
        if shape == "per_product":
            for d in product_dirs:
                issues.extend(fn(d))
        elif shape == "global":
            issues.extend(fn())
        else:
            not_aggregated.append(name)
            continue
        ran.append(name)
    live = {rcb.fingerprint(i) for i in issues
            if i.get("severity") in ("high", "critical")
            and not rcb.is_env_artifact_issue(i)}
    new = sorted(live - baseline)
    return {"ok": not new, "keepers_changed": keepers, "ran": ran,
            "not_aggregated": not_aggregated, "new_fingerprints": new}
