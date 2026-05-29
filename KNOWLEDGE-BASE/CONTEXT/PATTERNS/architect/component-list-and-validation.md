# Component list and validation signal

> Organ catalog discoverability (W3 of project `seed-organs-cache`). Paired with
> `component-bundle-tool.md` (W2) and `noc-graph.md` (the storage layer these tools extend).

## Problem

The seed ships reusable components (the "bodies") but agents rediscover them via grep every
session — no queryable catalog, no signal for which ones are trustworthy for reuse. The
silent default is "I'll build it myself," even when a validated LoginForm already exists and
has 9 consumers.

## Solution: derived validation signal + `noctus.dev.component_list`

Two deliverables in the W3 slice:

1. **`noctusai_lib.components.validation_signal`** — pure-Python derivation function.
   The canonical reuse-signal logic lives in the seed lib so any cross-product
   consumer can call it without depending on the MCP layer.

2. **`noctus.dev.component_list`** — MCP tool + CLI flag (`--component-list`). Walks
   all `kind=component` nodes in the noc-graph, derives their status, returns a sorted
   + filterable list.

## Validation status semantics

| Status | Meaning |
|---|---|
| `validated` | All 5 gates pass — proven, stable, ready for reuse |
| `emerging` | In use but one or more gates open — the healthy trajectory |
| `shelfware` | Zero consumers — built but not wired anywhere |
| `unknown` | Data missing — treat as `emerging` for reuse purposes |

**Shelfware is NOT the same as "broken."** A shelfware component may be correct. It's
named explicitly to surface the anti-pattern ("available but nobody uses it") so it can be
wired or deleted deliberately — never left silently "available."

## The 5-gate formula for `validated`

```python
validated = (
    consumers_count >= CONSUMERS_THRESHOLD   # ≥ 3 wired consumers
    and has_test                             # colocated test file exists
    and test_passes_ci is True               # CI confirms green (not unknown)
    and not has_noc_remediate_markers        # no deferred debt in source
    and recent_bugfix_commits_14d == 0       # no bug-fixes in last 14 days
)
```

A **single gate failure** drops to `emerging`. ALL five must hold for `validated`.

## Threshold constants (tunable)

Defined at `noctusai_lib.components.validation_signal`:

| Constant | Default | Rationale |
|---|---|---|
| `CONSUMERS_THRESHOLD` | `3` | The recurrence rule applied to components: N≥3 proves cross-product value |
| `BUGFIX_WINDOW_DAYS` | `14` | Two-week settling window — long enough to catch fire-fighting, short enough to not penalise old one-off fixes |

**Never inline these at call-sites.** Import from the module so changing a threshold
propagates everywhere automatically.

## Derived-first principle

Validation status is DERIVED, never manually entered. This is the core decision that prevents
catalog rot:

- Manual entries = someone remembers to update them. Decay is guaranteed.
- Derived entries = re-computed on every `list_components()` call against live signals.

The five inputs are all observable (consumer graph edges, test file co-location, git log,
source text for NOC-REMEDIATE markers). No opinion, no vote.

**Phase-2 exception:** `validation_override.yaml` sidecars (W4 design decision) will allow
explicit `test_passes_ci: true` overrides for components where CI signal is unavailable at
this layer. Overrides are ADDITIVE — they supply missing data, not override derived facts.

## Signal fallback chain

`consumers_count` is derived from the noc-graph edge walk:

1. **`consumes_component` edges** (W1 — correct attribution through re-exports) — preferred.
2. **`imports` edges** fallback when W1 hasn't landed, with a `WARNING` log entry per
   component. The warning is NOT a silent-ok — it names the missing dependency.

## Query examples

```bash
# All organs sorted by reuse (top of list = most proven)
python mcp/noctusai/cli.py --component-list

# Surface zero-consumer organs (audit dead code or un-wired components)
python mcp/noctusai/cli.py --component-list --filter-status shelfware

# Find only fully validated organs (safe to reuse without inspection)
python mcp/noctusai/cli.py --component-list --filter-status validated

# Alphabetical view
python mcp/noctusai/cli.py --component-list --sort name --json
```

Via MCP (in-session):
```
noctus.dev.component_list sort="consumers_desc"
noctus.dev.component_list filter_status=["shelfware"]
noctus.dev.component_list sort="name" filter_status=["validated", "emerging"]
```

## Performance contract

`list_components()` re-computes on every call; results are cached in-process keyed by
`aggregate_source_sha`. A sha match skips re-traversal (typically < 50ms). A sha mismatch
triggers a full re-derivation (graph walk + disk + git, typically 1-5s for the seed set).
The graph itself is lazy-rebuilt by `_ensure_fresh_on_read` only when stale.

## Consuming validation_signal cross-product

The derivation function is in the shared lib so product-level tools can call it directly:

```python
from noctusai_lib.components.validation_signal import (
    derive_validation_status,
    compute_signal_inputs,
    CONSUMERS_THRESHOLD,
)

inputs = compute_signal_inputs(component_path, graph_neighbors, repo_root)
status = derive_validation_status(component_name="MyComponent", **inputs)
```

The `compute_signal_inputs` helper handles disk reads + git subprocess calls. The
`derive_validation_status` function is a pure function with no side effects — trivially
unit-testable.

## Composes with

- `KB § PATTERNS/architect/noc-graph.md` — the graph layer that stores component nodes +
  `consumes_component` edges.
- `KB § PATTERNS/common/cache-as-agent-tool.md` — organs participate as structured graph
  nodes; use `noctus.dev.component_list` before building a new component.
- `KB § PATTERNS/common/remediation-markers.md` — `NOC-REMEDIATE` markers in source are
  one of the five validation gates.
- `KB § PATTERNS/architect/seed-absorption.md` — the sibling methodology for absorbing
  product code → seed lib.

## Born

2026-05-29 — W3 of project `seed-organs-cache` (Phase 1 seed pilot). Implemented by
`backend-engineer` lens, inline.
