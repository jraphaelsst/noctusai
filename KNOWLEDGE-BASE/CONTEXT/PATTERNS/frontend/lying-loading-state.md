# Lying-loading-state — `isLoading` is FALSE during a background refetch

> **Rule.** Never gate a loading UI (a `loading=`/`isLoading=` JSX prop, or a
> hand-rolled empty-state guard) on TanStack Query v5's `isLoading`. It is
> **FALSE mid-refetch** — the moment it drops, an "empty > loading"-priority
> component (or a `!X.isLoading && rows.length === 0` guard) renders "no
> data" **over data that exists**. Gate on `isPending || isFetching` instead.

Born 2026-07-21/22: `products/social-wiring/frontend/src/pages/leads/*.tsx`
shipped `loading={q.isLoading}` on every `ChartCard`/`StatTile`. A real user
(Priscila) watched a correct skeleton frame render, then ~2s later — mid
background-refetch — every card flipped to **"Sem dados para o período
selecionado."** against a live dataset of **28 brokers / 12,177 leads**. The
UI confidently reported zero data while holding the real numbers in memory.

---

## Why this bites

TanStack Query v5 changed the semantics of `isLoading`:

```
isLoading === isPending && isFetching
```

`isPending` means "no data has EVER resolved" (first load, or query reset).
`isFetching` means "a request is in flight right now" (first load OR a
background refetch). `isLoading` is the INTERSECTION — true only during the
very first fetch. The moment a background refetch starts on an ALREADY
resolved query, `isPending` is `false`, so `isLoading` is `false` too — **even
though a request is actively in flight and the previous data might be about
to change.**

Every consumer that treats `isLoading` as "show a loading state" is
correct **only for the first paint**. On every subsequent refetch (poll
interval, window refocus, `invalidateQueries`, a filter change that
re-triggers the query), `isLoading` silently goes `false` while the request
is still running — and whatever branch a component falls into NEXT wins.

### Shape 1 — the JSX prop (what shipped live)

`ChartCard`'s render priority is **loading > error > empty**:

```tsx
// BUGGY — isLoading is false mid-refetch, isEmpty wins, "Sem dados" renders
// over a fully-loaded dataset.
<ChartCard
  loading={byDimQ.isLoading}
  error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
  isEmpty={rankedBuckets.length === 0}
>
```

Fixed in `b0cb47b1` (14 props across 4 files — `Corretores.tsx` /
`Empreendimentos.tsx` / `Origens.tsx` / `VisaoGeral.tsx`):

```tsx
// CORRECT — covers first load AND every background refetch.
<ChartCard
  loading={byDimQ.isPending || byDimQ.isFetching}
  error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
  isEmpty={rankedBuckets.length === 0}
>
```

Because `loading` outranks `isEmpty` in `ChartCard`'s priority, this alone
makes the empty branch unreachable while data is in flight — no `isEmpty`
change needed.

### Shape 2 — the hand-rolled equivalent

The **same lie**, one layer down, without a wrapper component — fixed one
commit earlier (`ae9087ce`) in the pre-skeleton version of the same pages:

```tsx
// BUGGY
{byDimQ.isLoading && <TableSkeleton rows={8} columns={6} />}
{byDimQ.isError && <ErrorBanner />}
{!byDimQ.isLoading && !byDimQ.isError && buckets.length === 0 && (
  <EmptyState>Sem dados para o período selecionado.</EmptyState>
)}
```

```tsx
// CORRECT
{byDimQ.isPending && <TableSkeleton rows={8} columns={6} />}
{byDimQ.isError && <ErrorBanner />}
{!byDimQ.isPending && !byDimQ.isFetching && !byDimQ.isError && buckets.length === 0 && (
  <EmptyState>Sem dados para o período selecionado.</EmptyState>
)}
```

### Why unit tests miss it

A mocked query object is constructed with a fixed `{ isLoading, isPending,
isFetching, isError, data }` shape and never actually transitions through a
real refetch — so a test that asserts "empty state renders when
`isLoading=false` and `data=[]`" is *correct given its mock* and blind to the
live TanStack state machine. The toast/bug report from a real user was the
only signal both times this shipped. Per
`KB § PATTERNS/backend/boundary-contract-tests.md` § 5 (third-party-library
contract) — the same class as `check_query_fn_returns_undefined`'s
`queryFn`-returns-`undefined` gate, applied to the read side of the same
library's state machine.

---

## The correct gate

```tsx
loading={q.isPending || q.isFetching}
```

- `q.isPending` — covers the first load (no data has ever resolved).
- `q.isFetching` — covers every subsequent refetch (poll / refocus /
  invalidate / filter change) while the previous data is still displayed
  underneath.
- Never `q.isLoading` alone as a "is this query busy" signal in a UI branch
  that competes with an empty/success branch.

If a component genuinely only cares about "has this query EVER resolved"
(e.g. a one-shot mount-time skeleton with no empty-state sibling to race
against), `isPending` alone is fine — the bug is specifically the
**loading-vs-empty (or loading-vs-success) race**, not `isPending` in
isolation.

---

## The detector — `check_lying_loading_state`

`mcp/noctusai/tools/noctus/dev/compliance.py` (`check_lying_loading_state`,
severity **`warning`** — observe-first cadence on a brand-new detector, see
`_LYING_LOADING_SEVERITY` for the one-line promotion switch). Scans every
`products/<slug>/frontend/src/**/*.tsx`, flagging three shapes:

1. A JSX `loading=`/`isLoading=` prop whose value is EXACTLY `<chain>.isLoading`
   (a TanStack query member expression) — e.g. `loading={q.isLoading}`.
2. The higher-value variant: the SAME JSX opening tag also carries an
   `isEmpty=`/`empty=` prop — the exact "empty outranks loading" shape that
   shipped live. Reported with an elevated, incident-specific message.
3. The hand-rolled equivalent: `!X.isLoading && ... && rows.length === 0` on
   one line.

No tree-sitter / ts-morph dependency is available in this environment; the
scanner reuses the SAME code-only-text + brace-walk technique every other
TSX keeper in `compliance.py` already uses (`check_query_fn_returns_undefined`,
`scan_wiring._scan_promise_all_in_text`) — comments/strings blanked via the
shared `_strip_for_scan` helper, JSX opening-tag boundaries isolated via an
explicit `{`/`}` depth walk (`_find_jsx_opening_tag`) rather than a blind
`.*`-across-the-tag regex.

**Escape hatch:** `lying-loading-ok` in a same-line or up-to-3-preceding-line
comment (for a genuinely non-TanStack `isLoading` shape, e.g. a `Fake` test
double with no refetch semantics).

**Wired into:**
- `check_all_products()` (global sweep — `mcp/noctusai/tools/noctus/dev/compliance.py`)
- `tools/noctus/dev/review.py::_detect()` (global sweep leg)
- CLI: `python mcp/noctusai/cli.py --check-lying-loading-state`
- Pre-commit hook (`scripts/hooks/pre-commit` § 6f) — gated on staged
  `products/*/frontend/src/**/*.tsx`; advisory only (never blocks a commit —
  the CLI dispatch exits 0 unconditionally for this gate).
- Regression tests: `mcp/noctusai/tests/test_lying_loading_state_detector.py`
  (`TestLyingLoadingState`) — positive fixtures pinned to the EXACT pre-fix
  git content (`git show ae9087ce:.../Corretores.tsx`,
  `git show ae9087ce^:.../Corretores.tsx`), negative fixtures for the fixed
  gate and an unrelated plain-boolean `loading` prop.

**Verified against real history:** clean on the current (fixed) tree for
every `products/social-wiring/.../leads/*.tsx` file; flags **14** findings
against the `ae9087ce` tree (ChartCard-prop shape only — matches the
`b0cb47b1` commit message's own count exactly) and **18** findings against
`ae9087ce^` (both the ChartCard-prop AND hand-rolled shapes, across
`Corretores.tsx` / `Empreendimentos.tsx` / `Importacao.tsx` / `Origens.tsx` /
`VisaoGeral.tsx`). It also found a genuinely NEW, previously-unknown instance
of the same class live in `products/therapy-platform/frontend/src/pages/
therapist/Scheduling.tsx:140` — the detector generalizes beyond the incident
it was built for.

---

## Checklist — validate a future TanStack Query loading UI against this rule

- [ ] Every `loading=`/`isLoading=` prop passed to a component with an
      empty/success branch reads `q.isPending || q.isFetching`, never
      `q.isLoading` alone.
- [ ] Every hand-rolled empty-state guard reads
      `!q.isPending && !q.isFetching && ...`, never `!q.isLoading && ...`.
- [ ] `noctus.dev.review` / `--check-lying-loading-state` is clean — no new
      findings.
- [ ] A component whose priority order is loading > error > empty (or
      loading > empty > success) double-checks that its loading GATE, not
      just its data, survives a background refetch.

This is the Stage-4 codification of the 2026-07-21/22 live incident —
`compliance.py` (detector) + this doc + `scripts/hooks/pre-commit` § 6f +
`mcp/noctusai/cli.py` (`--check-lying-loading-state`) landed in the same
commit. See `KB § PATTERNS/common/methodology-codification-pipeline.md`.
