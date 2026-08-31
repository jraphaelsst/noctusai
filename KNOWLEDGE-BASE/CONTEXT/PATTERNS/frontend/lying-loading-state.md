# Lying-loading-state — a loading UI must never claim the app has no data

> **Rule — two signals, derived from `data`, never `isLoading`.**
>
> ```tsx
> const showSkeleton = q.isPending && !q.data;   // nothing to render yet → skeleton
> const isRefreshing = q.isFetching && !!q.data; // data exists → KEEP RENDERING
> ```
>
> `showSkeleton` gates the skeleton / empty-state branch. `isRefreshing` gates
> **at most** a subtle, non-layout-reserving indicator (header spinner, dimmed
> opacity, disabled control). It NEVER gates an early `return`.
> For a query whose `queryKey` changes with user input, add
> `placeholderData: (prev) => prev` so `data` never becomes `undefined`
> mid-transition. **Never `q.isLoading`.**

**This doc widens an earlier rule; it does not reverse it.** The 2026-07-21
prohibition on `.isLoading` stands, unchanged and absolute. What changed on
2026-08-31 is the *replacement* the doc prescribed: `isPending || isFetching`
closed one failure mode by opening its mirror image. If you are ever tempted to
"go back to `isPending || isFetching`", read § *Both incidents* first — the two
bugs are complementary, and only the two-signal form closes both.

---

## Both incidents — the same lie, told in opposite directions

Both bugs are one class: **the UI asserts "I have nothing to show you" while
holding real data in memory.** Mode A tells that lie with an empty state; Mode
B tells it with a skeleton. Neither is more real than the other; a fix that
trades one for the other has fixed nothing.

### Mode A — empty-over-data (2026-07-21/22, `ae9087ce` + `b0cb47b1`)

`products/social-wiring/frontend/src/pages/leads/*.tsx` shipped
`loading={q.isLoading}` on every `ChartCard` / `StatTile`. A real user
(Priscila) watched a correct skeleton frame render, then ~2s later — mid
background-refetch — every card flipped to **"Sem dados para o período
selecionado."** against a live dataset of **28 brokers / 12,177 leads**.

Cause: TanStack Query v5 defines `isLoading === isPending && isFetching`, so
`isLoading` goes **false** the moment a refetch starts on an already-resolved
query. `ChartCard`'s priority is `loading > error > empty`; with `loading`
false and `isEmpty` computed off a still-`undefined`/stale array, the empty
branch won.

### Mode B — skeleton-over-data / refetch-unmount (2026-08-31)

A user recorded a screen capture: editing one field on the social-wiring
client card made the 8-row **"DADOS OBRIGATÓRIOS"** block vanish and the card's
layout collapse, then reappear. A fleet-wide audit found **70 instances of the
same shape** plus **140 key-change-flicker sites**, across `social-wiring`,
`igig`, `erp-imobiliario` and two seed organs.

Cause: the fix for Mode A, applied literally. `isFetching` is true during
**every** background refetch, so

```tsx
if (isPending || isFetching) return <Skeleton />;   // ← unmounts on every mutation
```

tears down the subtree each time any mutation invalidates the query. The
`return` is the damage: React unmounts the real children, local UI state
(scroll, focus, open accordions, in-progress inputs) dies with them, and the
layout reflows twice per interaction.

**Nobody wrote a bug here.** Every one of those 70 sites was following
`CLAUDE.md` §1 and this document as written. A rule stated as a universal when
it was only true of one race manufactured its own counter-incident at fleet
scale. That is the real finding, and it is why the rule below is stated as a
*decision procedure* rather than as a single blessed expression.

---

## Why this bites — the TanStack v5 state machine

```
isPending  = "no data has EVER resolved"   (first load, or query reset)
isFetching = "a request is in flight NOW"  (first load OR background refetch)
isLoading  = isPending && isFetching       (the INTERSECTION — first fetch only)
```

Read the three against what the user can actually see:

| `isPending` | `isFetching` | `data` | What the user should see |
|---|---|---|---|
| `true` | `true` | `undefined` | **Skeleton.** Nothing to render yet. |
| `false` | `true` | present | **The data, still.** Plus a subtle refreshing hint. |
| `false` | `false` | present | The data. |
| `false` | `false` | `[]` / empty | The **empty state** — and only here. |

`isLoading` is true only in row 1, which is why gating on it lets row 2 fall
through to whatever branch comes next (Mode A). `isPending || isFetching` is
true in rows 1 **and** 2, which is why it re-arms the skeleton in row 2
(Mode B). `isPending && !data` is true only in row 1. That is the whole
argument.

---

## The decision procedure

Ask, in order:

1. **Is there anything to render right now?** `!!q.data` (or
   `items.length > 0` for a section that owns its own array). If yes — render
   it. The answer does not depend on any query flag.
2. **If not, is that because it hasn't arrived yet, or because it's genuinely
   empty?** `q.isPending` → hasn't arrived → skeleton. `!q.isPending` →
   arrived and empty → empty state.
3. **Is a fetch in flight on top of data that already exists?** `q.isFetching
   && !!q.data` → a *non-destructive* affordance only: header spinner, `aria-
   busy`, dimmed opacity, disabled submit. Never an early `return`, never a
   branch that removes DOM.
4. **Can the `queryKey` change from user input** (filter, search, page,
   selected entity)? → `placeholderData: (prev) => prev`, so step 1 keeps
   answering "yes" across the transition. See § *Key-changing queries*.

Steps 1–3 collapse to the two-signal form in the rule box. Step 4 is what
keeps step 1 true when the key moves.

### Canonical implementations in-tree

`products/orbity/frontend/src/pages/Funil.tsx:733` — the scoped form, with its
reasoning written next to it:

```tsx
if (isPending || (isFetching && stages.length === 0)) {
```

`isFetching` is admitted **only** while there is nothing on screen, which is
the same predicate as `!data` expressed against the section's own array. Also
`seed/lib/frontend/src/components/pipeline/PipelineStagesManager.tsx:58-61`.

`products/social-wiring/frontend/src/components/card/DocumentoChecklistSection.tsx`
(`d2726e13`) — the two-signal contract at a section boundary, plus the
belt-and-braces half that matters: **each section's own render refuses to
skeleton once its items array is non-empty**, so a stale `loading={true}` from
a caller can never blank real rows even in isolation. Prefer that shape for
organ-like components — it makes the component correct independently of how
carefully its consumer computed the prop.

`products/igig/frontend/src/hooks/` (`1e770842`) — **fix it at the hook, not
the page.** All 18 occurrences lived in one place: every `use*` hook returned
`loading: query.isPending || query.isFetching`. Changing the formula at the
source fixed ten consuming pages with zero page-level edits. When a `loading`
field is computed in a hook or a container and passed down as a prop, that
computation is the site — chasing the consumers is the expensive way to fix
the same bug N times.

---

## Shapes to recognise

### Shape 1 — the JSX prop (Mode A, what shipped 2026-07-21)

```tsx
// BUGGY — isLoading false mid-refetch, isEmpty wins, "Sem dados" over 12,177 leads
<ChartCard loading={byDimQ.isLoading} isEmpty={rankedBuckets.length === 0}>

// CORRECT
<ChartCard loading={byDimQ.isPending && !byDimQ.data} isEmpty={rankedBuckets.length === 0}>
```

### Shape 2 — the hand-rolled empty guard (Mode A)

```tsx
// BUGGY
{!byDimQ.isLoading && !byDimQ.isError && buckets.length === 0 && <EmptyState/>}

// CORRECT — an empty state is only honest once the query has resolved
{!byDimQ.isPending && !byDimQ.isError && buckets.length === 0 && <EmptyState/>}
```

### Shape 3 — the early-return skeleton (Mode B, what shipped 2026-08-31)

```tsx
// BUGGY — true on EVERY refetch; unmounts the whole subtree per mutation
if (isPending || isFetching) return <Skeleton />;

// CORRECT
if (isPending && !data) return <Skeleton />;
// …and, if you want to signal the refresh at all:
<CardHeader>{isFetching && !!data && <Spinner size="sm" aria-label="Atualizando" />}</CardHeader>
```

### Shape 4 — the derived `loading` field (Mode B, at the source)

```ts
// BUGGY — one hook, every consuming page
return { data, loading: query.isPending || query.isFetching, ... };

// CORRECT
return { data, loading: query.isPending && !query.data,
         refreshing: query.isFetching && !!query.data, ... };
```

---

## Key-changing queries — `placeholderData`

When `queryKey` includes user-changeable state (search text, status filter,
competência, page number, selected entity id), a key change starts a *new*
cache entry: `data` becomes `undefined` and `isPending` becomes `true` again.
The two-signal rule then correctly shows a skeleton — but the user experiences
a flicker on every keystroke, because from their point of view the list was
right there a moment ago.

```ts
useQuery({
  queryKey: ['clientes', busca, status],
  queryFn: fetchClientes,
  placeholderData: (prev) => prev,   // or `keepPreviousData` from @tanstack/react-query
});
```

`data` now holds the previous key's result during the transition, so step 1 of
the decision procedure keeps answering "yes" and the structure stays mounted.
Pair it with `isFetching && !!data` for the refreshing hint — that is exactly
what the indicator is for. Landed fleet-wide in `991848b1` (42 files) and
`15c56505` (51 of 52 dynamic-keyed hooks in `erp-imobiliario`);
`ca62b07b` wires it into the seed's `createPipelineHooks`
(`useBoard` / `useAIOutputFor` / `useNotificacoes`) so consumers inherit it.

### The deliberate refusal — when stale-visible is the wrong answer

`placeholderData` is a default, not a law. Keeping the previous page visible is
a UX win for a property grid and a **data-exposure bug** for a personal-data
table: it means one operator's screen keeps rendering rows the current query no
longer authorises. `products/erp-imobiliario/frontend/src/hooks/
useVistaShowcase.ts:244` refuses it on those grounds and says so in the
docstring:

> `placeholderData` is NOT used here on purpose. Keeping the previous page
> visible while the next loads is nice for a property grid; for a personal data
> table it means one admin's screen keeps showing rows the current query no
> longer authorises. Page changes show a skeleton instead.

**Codified rule:** a query returning personal data whose key encodes an
authorisation-relevant dimension (tenant, owner, role-scoped filter, page of a
restricted list) MUST NOT use `placeholderData`, and MUST carry a one-sentence
comment saying why — otherwise the next audit reads the omission as an
oversight and "fixes" it. The refusal is part of the pattern, not an exception
to it. → `KB § PATTERNS/security/lgpd.md`

---

## Why tests miss it — and worse, defend it

A mocked query object is constructed with a fixed
`{ isPending, isFetching, isError, data }` shape and never transitions through
a real refetch. A test asserting "empty state renders when `isLoading=false`
and `data=[]`" is *correct given its mock* and blind to the live state machine.
A real user's bug report was the only signal, **both times**.

It gets worse than blindness. When `0c182a9b` fixed the 14 social-wiring page
files, **two pre-existing tests failed because they hard-coded the buggy
contract** — `PortalRoi.test.tsx` and `LeadgenWebhookCard.test.tsx`, the latter
with a case literally named:

```
it("renders the loading state while a background refetch is in flight (isPending false, isFetching true)")
```

That test was written in good faith from this document, and it was actively
defending the unmount. **A rule stated too broadly does not merely permit the
bug — it gets encoded into the suite, which then blocks the fix.** When you
correct a loading gate and a test goes red, check which contract the test is
asserting before you "restore" anything.

Both files now assert the correct contract *and* the 2026-07-21 guard
(`data: undefined` never renders rows, with `isFetching: false` so the
assertion cannot ride on `isFetching` to cover the gap). Keep both halves in
any new regression test — that is what makes this a widening rather than a
swap. Per `KB § PATTERNS/backend/boundary-contract-tests.md` § 5
(third-party-library contract).

---

## The detector — `check_lying_loading_state`

`mcp/noctusai/tools/noctus/dev/compliance.py`, severity `warning`
(`_LYING_LOADING_SEVERITY` is the one-line promotion switch). Scans every
`products/<slug>/frontend/src/**/*.tsx` and flags three shapes:

1. A JSX `loading=` / `isLoading=` prop whose value is EXACTLY
   `<chain>.isLoading`.
2. The higher-value variant: the same JSX opening tag also carries an
   `isEmpty=` / `empty=` prop — the exact "empty outranks loading" shape that
   shipped live.
3. The hand-rolled `!X.isLoading && … && rows.length === 0` guard.

**Scope — it covers Mode A only.** The detector early-exits on
`if "isLoading" not in content`, and its prop regex requires the value to be
*exactly* `x.isLoading`; `isPending && !data` contains no `isLoading` and
passes cleanly (confirmed by the negative fixtures in
`mcp/noctusai/tests/test_lying_loading_state_detector.py:150-165`). The
2026-08-31 correction therefore needed **no detector change** — which is also
the honest statement of its limit: **Mode B is currently doc-enforced, not
gate-enforced.** The unmount shape is `if (loading) return <skeleton/>` where
`loading` traces through props or a hook's return value across files; catching
it needs cross-file dataflow, which this text-based scanner does not do. Treat
review and this document as the control for Mode B until that changes.
→ `KB § PATTERNS/common/gate-methodology-sync.md`

**🔴 Known drift — the keeper's own remediation text still prescribes the
superseded gate.** `compliance.py:8488` tells the engineer to
"Use `{query_expr}.isPending || {query_expr}.isFetching`", and
`compliance.py:8513` tells them to "Use `!X.isPending && !X.isFetching && …`".
Every time this detector fires it therefore pushes the reader straight into
Mode B. Those two strings must be corrected to the two-signal form
(`isPending && !data` for the skeleton branch; `!isPending` for the empty
branch) — the docstring and header comment above them were corrected on
2026-08-31, the message strings were left untouched because that edit fell
outside the documentation slice's write zone. Until they change, trust this
document over the finding text.

**Escape hatch:** `lying-loading-ok` in a same-line or up-to-3-preceding-line
comment (genuinely non-TanStack `isLoading`, e.g. a `Fake` test double).

**Wired into:** `check_all_products()` · `tools/noctus/dev/review.py::_detect()`
· CLI `python mcp/noctusai/cli.py --check-lying-loading-state` ·
`scripts/hooks/pre-commit` § 6f (advisory, never blocks) · regression tests
`mcp/noctusai/tests/test_lying_loading_state_detector.py`.

**Verified against real history:** clean on the fixed tree; **14** findings
against `ae9087ce` (matching `b0cb47b1`'s own count) and **18** against
`ae9087ce^`. It also found a previously-unknown live instance in
`products/therapy-platform/.../Scheduling.tsx:140` — it generalises beyond its
origin incident.

### Why the file is still named `lying-loading-state`

The name was audited on 2026-08-31 and deliberately kept. It is not narrower
than the widened rule: a skeleton rendered over data that exists is *also* a
lying loading state — the UI claiming it has nothing while holding everything.
Both modes are the same lie. The name additionally stays symmetric with the
keeper `check_lying_loading_state`, the CLI flag
`--check-lying-loading-state` and the `lying-loading-ok` escape-hatch token;
renaming the doc alone would split those and buy nothing.
→ `KB § PATTERNS/common/lossless-doc-refactor.md`

---

## Checklist — validate any TanStack Query loading UI

- [ ] No `.isLoading` anywhere in a render branch. (Mode A, unchanged.)
- [ ] Every skeleton / early-`return` gate reads `isPending && !data` — never a
      bare `|| isFetching` once data has landed once. (Mode B.)
- [ ] Every empty state is gated on `!isPending` (query resolved) **and** an
      actually-empty array — never over `undefined` data.
- [ ] `isFetching` appears only in a non-destructive indicator
      (`isFetching && !!data`), or scoped to the still-empty case as in
      `Funil.tsx:733`. It never removes DOM.
- [ ] Every `useQuery` whose key includes user-changeable state has
      `placeholderData: (prev) => prev` — **or** a comment stating why not
      (personal data / authorisation-scoped: see the LGPD refusal above).
- [ ] If a `loading` flag is computed in a hook or container, the two-signal
      form lives THERE, not repeated in each consumer.
- [ ] Regression tests assert **both** modes: skeleton over `data: undefined`
      (with `isFetching: false`), and content still mounted at
      `isPending: false, isFetching: true, data: present`.
- [ ] `--check-lying-loading-state` clean — and remember it only covers Mode A.

---

## Codification history

- **s4, 2026-07-22** — Mode A codified: detector + this doc +
  `scripts/hooks/pre-commit` § 6f + CLI flag, one commit.
- **s3, 2026-08-31** — Mode B added after the fleet audit (70 unmount sites,
  140 key-change-flicker sites). Fixes landed as `ca62b07b` (seed organs),
  `1e770842` (igig, at the hook layer), `d2726e13` (client card),
  `0c182a9b` (sw pages), `15c56505` (erp), `991848b1` (fleet
  `placeholderData`), `22ca3ac6` (sw components); the rule was rewritten to a
  decision procedure in the same wave. Two engineers flagged the
  doc-vs-reality contradiction independently and unprompted — the doc, not the
  detector, was the pusher.

→ `KB § PATTERNS/common/methodology-codification-pipeline.md`
