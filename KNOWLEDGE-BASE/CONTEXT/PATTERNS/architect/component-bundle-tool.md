# component-bundle-tool — `noctus.dev.component_bundle`

**Shipped:** 2026-05-29 · Project: seed-organs-cache W2

## Purpose

`noctus.dev.component_bundle` returns the **organ bundle** — a single structured
payload that gives an agent everything it needs to understand and use a shared
seed-lib frontend component:

```python
{
  "source":            str,         # full .tsx/.ts source text
  "types":             list[str],   # exported type/interface/function signatures (AST-extracted)
  "tests":             str | None,  # colocated <Name>.test.tsx source, or None
  "deps":              list[str],   # unique import module paths
  "consumers":         list[str],   # module paths that consume this component (noc-graph)
  "wiring_snippet":    str,         # 5-line usage example from first consumer
  "validation_status": str,         # validated | emerging | shelfware | unknown
  "last_touched":      str | None,  # git log -1 --format=%ci timestamp
}
```

## Bundle Field Details

| Field | Source | Notes |
|---|---|---|
| `source` | `Path.read_text()` on the `.tsx`/`.ts` file | Located via known seed-lib roots |
| `types` | Column-0-anchored regex on prettier-formatted TS | Export declarations only; no type body content |
| `tests` | Colocated `<Name>.test.tsx` / `<Name>.test.ts` | `None` if absent |
| `deps` | Same AST-equivalent extraction — `import … from '…'` | Unique, ordered |
| `consumers` | noc-graph `consumes_component` edge (W1) or `imports` fallback | See W1 fallback below |
| `wiring_snippet` | First consumer file — lines containing `<Name` or `import Name` | 5-line window max; `<Name />` placeholder if extraction fails |
| `validation_status` | `derive_validation_status(...)` from `noctusai_lib.validation_signal` (W3) | Falls back to `"unknown"` if W3 not yet shipped |
| `last_touched` | `git log -1 --format=%ci <path>` | `None` if untracked |

## AST Extraction Rationale

Type signatures are extracted via **column-0-anchored regex** on
prettier/eslint-formatted TS declarations.  This is the same accepted
deviation documented in `outline_typescript.py`:

> Phase 4 audit (2026-05-02): regex on prettier-formatted TS hits ~95%
> of practical declarations at ~5ms per call vs ~200ms + ~50MB for the
> TypeScript Compiler API.

The extraction is **NOT** arbitrary body regex — it anchors at column 0 and
matches only the first line of each top-level exported declaration.  Indented
declarations (inside class bodies, function bodies, string literals) are
explicitly excluded by the column-0 anchor.

Upgrade path → tree-sitter or the TypeScript Compiler API if precision
becomes load-bearing.

## Cross-Dependency Fallback Semantics

### W1 — `consumes_component` edge (noc-graph)

W1 adds `EdgeKind.CONSUMES_COMPONENT` to the graph schema so the graph
distinguishes "renders as JSX" from "imports from module".

- **W1 landed:** `consumers` = neighbors via `consumes_component` edge.
- **W1 not yet landed:** `consumers` = neighbors via `imports` edge (over-broad —
  includes modules that import utility functions from the file, not just JSX
  consumers).  One `WARNING` is logged.  Pass `fallback_when_w1_missing=False` to
  get `[]` instead.

### W3 — `derive_validation_status` (validation_signal)

W3 ships `noctusai_lib.validation_signal.derive_validation_status(...)`.  The
bundle calls it with:

```python
derive_validation_status(
    component_name=name,
    consumers_count=len(consumers),
    has_test=test_path is not None,
    test_passes_ci=None,   # not available in-process
    has_noc_remediate_markers=bool("NOC-REMEDIATE" in source),
    recent_bugfix_commits_14d=int,
)
```

- **W3 landed:** `validation_status` = one of `validated|emerging|shelfware|unknown`.
- **W3 not yet landed:** `validation_status = "unknown"`.  One `WARNING` is
  logged.

Both warnings are **one-shot** (module-level `_W3_WARNED` / `_W1_WARNED` guards).

## CLI

```bash
python mcp/noctusai/cli.py --component-bundle ResourceManager
python mcp/noctusai/cli.py --component-bundle ResourceManager --json
```

## Extension Path

- **Richer AST:** replace col-0 regex with tree-sitter-typescript or
  `node --eval "ts.createSourceFile(...)"` subprocess for full type-aware
  extraction.
- **Test-pass status:** pipe `vitest --reporter=json` output into
  `bundle_component(..., test_pass_status=...)` parameter for a real CI
  signal rather than `None`.
- **W1 retest:** once `consumes_component` edges land, run
  `noctus.dev.component_bundle ResourceManager` and verify `consumers` list
  is JSX-accurate (vs the broader `imports` set).

## Related

- `KB § PATTERNS/common/cache-as-agent-tool.md` — the graph-query pattern this tool builds on
- `KB § PATTERNS/architect/noc-graph.md` — noc-graph schema + EdgeKind taxonomy
- `KB § PATTERNS/frontend/product-internal-wiring.md` — why ResourceManager exists
- `KB § PATTERNS/architect/mcp-first-scripts.md` — why this is an MCP tool not a script
