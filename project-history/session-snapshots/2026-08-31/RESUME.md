# RESUME — 2026-08-31 session 3, snapshot taken mid-flight

> Taken because the owner needed to disconnect while three engineers were still
> running. **Subagents live inside the session process: when that session ended,
> they died.** Everything below is what survived, and how to pick it up.
>
> Read `HANDOFF-NEXT-SESSION.md` first for the full session record. This file
> covers ONLY the in-flight work at snapshot time.

---

## 1 · What is safe on `origin` (travels to any machine)

| branch | state | commits ahead of `dev` |
|---|---|---|
| `feat/cat-c-erp-hooks` | ✅ **COMPLETE + pushed**, gates green | 20 |
| `feat/shape5-remaining-products` | ✅ **COMPLETE + pushed**, gates green | 5 |
| `feat/shape5-social-wiring` | ⚠️ **PARTIAL + pushed** — Mode B committed, Shape 5 uncommitted | 1 |
| `feat/tech-lead-session-wrap` | ✅ handoff + this file + the patch | — |

All three worktrees also still exist on the original machine under
`.claude/worktrees/<slug>/`, but that does NOT travel. Only the pushed branches do.

---

## 2 · `feat/cat-c-erp-hooks` — DONE, ready to integrate

The engineer finished and reported clean gates: **tsc rc=0, vitest rc=0 (94/94),
vite build rc=0**, working tree clean, rebased onto `origin/dev` (`6f1d0067`) mid-session.

**What it contains (~85 files, 20 commits):**
- **Zero-over-data sweep** — 17 pages, ~55 card/value sites. A false `R$ 0,00` reads as a
  real answer, which makes it worse than an empty state or a skeleton. Built
  `components/ui/summary-value.tsx` at N≥8 recurrence, distinguishing `data === undefined`
  (not arrived → skeleton) from `data.field === 0` (real zero → renders `0`). Mutation-proved
  on Impostos, Comissoes and BI independently.
- **Shape 5 sweep** — ~110 sites across 65 files.
- **Additive hook widening** — `useIsAdmin()` now also returns `isPending`/`isFetching`/`roleData`,
  keeping `isLoading` for its 8 legitimate non-render consumers. All 12 consumers checked first.
- `entity-link.tsx` fixed internally; its 4 consumers' contract is unchanged.

**To land it:** `noctus.dev.task_branch action='integrate' slug='cat-c-erp-hooks' confirm=True`
(rebase onto the then-current `origin/dev` first if it has moved).

### 🔴 The important finding from this branch — the detector can report a FALSE CLEAN

`check_lying_loading_state`'s taint tracking matches the **literal token `isLoading`**
(property access, or a bare object-destructured identifier). It does **not** resolve a
further-renamed local:

```tsx
const { isLoading: loadingConfig } = useConfig();
if (loadingConfig) return <Skeleton/>;   // ← genuine Shape 5, NOT detected
```

Confirmed with a minimal repro that produced **0 findings against a textbook Shape-5 bug**.

Consequence: the engineer's first "detector says 0" was a false clean. It did not stop there —
it grepped every remaining `isLoading` in the product, traced each to its origin, and fixed the
renamed-alias sites by hand (`loadingConfig`, `feedsLoading`, `isLoadingProfiles`,
`isLoadingRole`, …). The final zero is corroborated by that manual sweep, **not by the tool alone**.

**So "detector reports 0" is NOT a sufficient acceptance criterion** — that was my instruction to
four engineers and it was wrong. Until the alias-resolution gap is closed, pair every scan with a
manual `isLoading` grep. Closing the gap is filed work: extend the ts-morph taint tracking to
follow renamed destructuring bindings.

---

## 2b · 🔴 THE DETECTOR HAS TWO CONFIRMED BLIND SPOTS — "0 findings" IS NOT CLEAN

**Two engineers found this independently, in different products, with separate repros.** Treat it
as established.

`mcp/noctusai/node/lying_loading_scan.mjs` misses two whole shapes:

**Gap 1 — renamed destructuring binding.** The occurrence collector is name-hardcoded
(`scanTaint(sourceFile, "isLoading", false)`), so a renamed binding never produces a read of the
literal identifier and the taint pass never starts:
```tsx
const { isLoading: contaLoading } = useConta();
if (contaLoading) return <Skeleton/>;   // single-hop early return — NOT detected
```
Repro'd in isolation on `personal-finance/pages/ContaDetalhes.tsx` → `[]`.

**Gap 2 — negation.** `climb()` has no `SyntaxKind.PrefixUnaryExpression` case, so a negated
occurrence hits the catch-all and stops instead of climbing through the `!` into the `&&`/ternary:
```tsx
!isLoading && rows.length === 0 ? <Empty/> : <List/>   // Shape-2 empty-over-data — NOT detected
```
Repro'd in isolation on `adconnect/pages/Orders.tsx` → `[]`.

### Why this matters more than any single fix
1. **"detector reports 0" was the acceptance criterion I gave four engineers. It was wrong.**
   Two of them caught it anyway and hand-grepped; the others' clean results are therefore
   **unverified, not verified**.
2. Products reported clean this wave — **therapy-platform, orbity, igig, dev-team,
   knowledge-extractor** — were measured with this tool. Their zeros may be false cleans.
3. The counts in §5 are **floors, not totals**. Every "extra" fix in §3's table
   (adconnect 3→7, core 1→2, personal-finance 13→18) is a site the detector could not see.

### The fix (filed, not done)
Extend `lying_loading_scan.mjs`:
- **(a)** add a `PrefixUnaryExpression` case to `climb()` that continues through `!` — noting that
  a no-data guard sitting beside a *negated* occurrence means the opposite thing, so the
  `NO_DATA_GUARD_RE` sibling-match must be interpreted inverted there;
- **(b)** track the LOCAL bound name of a renamed destructure as an additional taint name,
  symmetric with the existing one-hop alias tracking for `const carregando = isPending || isFetching`.

**Then re-run the fleet scan** — it will very likely surface new sites in products already marked
clean this wave. Until it lands, pair every scan with a manual `grep -rn isLoading` and read
through each hit.

### Related, out of everyone's scope this wave
`seed/lib/frontend/src/design-system/ai/DigestCard.tsx:102` gates its whole body on a bare
`isLoading` **prop**, and three products pass their hook's `isLoading` straight through
(`core/pages/admin/AdminAuditDigest.tsx`, `daily-life/components/WeeklyReviewCard.tsx`,
`personal-finance/components/MonthlyNarrativeCard.tsx`). Safe today — none of those three has a
user-changeable query key — but it is a canonical organ whose contract is a landmine for the next
consumer with a dynamic key. Route to whoever owns `seed/lib/frontend`: widen the prop contract to
`isPending`/`data` (or `isFetching`/`refreshing`) rather than a raw `isLoading` boolean.

---

## 3 · `feat/shape5-remaining-products` — DONE, ready to integrate

Finished after the first snapshot. **5 commits, one per product, clean tree, all gates green.**

| product | reported | fixed | detector after | tests |
|---|---:|---:|---:|---|
| p-studio | 9 | 9 | 0 | 5 files / 108 tests ✅ |
| adconnect | 3 | **7** | 0 | 1 file / 2 tests (thin — stated honestly) |
| core | 1 | **2** | 0 | 4 files / 16 tests ✅ |
| daily-life | 5 | 5 | 0 | 3 files / 7 tests ✅ |
| personal-finance | 13 | **18** | 0 | 19 files / 55 tests ✅ |

`tsc` / `vitest` / `vite build` all rc=0 per product. Note the fixed counts EXCEED the reported
ones — that difference is §2b, and it is the most important thing in this file.

`placeholderData` added where the key genuinely varies (p-studio's `incluirInativos`/date-range/
status-filter hooks, personal-finance's `useFluxoCaixa`), and **deliberately refused** on
route-param detail queries where a fresh skeleton on navigating between IDs is the correct
behaviour. No shared component's contract changed.

**To land it:** `noctus.dev.task_branch action='integrate' slug='shape5-remaining-products' confirm=True`

## 4 · `feat/shape5-social-wiring` — PARTIAL, pushed

**Committed + pushed (1 commit, `04ae9a27`):** *"close Mode-B unmount-over-data at Equipe +
AdDetalheModal"* — so the two Mode-B sites WERE real and are now fixed. That answers the open
question about whether they existed.

**Uncommitted at final snapshot:** 32 files, captured as
`shape5-social-wiring.uncommitted.patch` (74 KB) + `…status.txt`. This is the Shape-5 sweep for
social-wiring (27 sites measured at `216daf12`), interrupted mid-flight.

**To resume:**
```bash
git fetch origin && git checkout feat/shape5-social-wiring
git apply project-history/session-snapshots/2026-08-31/shape5-social-wiring.uncommitted.patch
```
**Review before applying** — a point-in-time capture of an agent mid-edit may contain a
half-finished file, and none of it was ever gate-checked. `products/social-wiring/frontend` has a
~996-test suite; run it in full. **Do not weaken `pages/leads/*.test.tsx`** — those gained real
Mode-A/Mode-B guards this session.

Given §2b, re-running this slice cleanly against current `dev` is a defensible alternative to
reconciling the patch — and it would pick up the alias/negation sites the detector misses anyway.

## 5 · Per-product Shape-5 state (measured at `216daf12`, before these branches landed)

| product | sites | covered by |
|---|---:|---|
| erp-imobiliario | 61 | `feat/cat-c-erp-hooks` ✅ done |
| social-wiring | 27 | `feat/shape5-social-wiring` ❌ patch only |
| personal-finance | 14 | `feat/shape5-remaining-products` ⚠️ patch |
| p-studio | 9 | `feat/shape5-remaining-products` ✅ committed |
| daily-life | 5 | `feat/shape5-remaining-products` ⚠️ patch |
| adconnect | 3 | `feat/shape5-remaining-products` ✅ committed |
| core | 1 | `feat/shape5-remaining-products` ⚠️ patch |
| therapy-platform · orbity · igig · dev-team · knowledge-extractor | 0 | clean |

Remember §2: these counts come from a tool with a known alias-resolution blind spot, so they are
**floors, not totals**.

---

## 6 · First five minutes of the next session

1. `/contextualize`, then read `HANDOFF-NEXT-SESSION.md`.
2. **Restart the MCP server** — it does not hot-reload tool modules, and the divergence-loop fix
   (`8c0af23e`) only takes effect in a fresh process. Until then `task_branch cleanup` runs the
   old code path.
3. Sync the primary (an agent is forbidden from doing this by self-branching mode):
   ```bash
   git checkout -- KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md && git pull --ff-only origin dev
   ```
4. Integrate `feat/cat-c-erp-hooks` — it is complete and gate-green.
5. Decide on the two partial branches per §3 / §4.
6. Still outstanding from the session proper: cache refresh (kb- + code-embeddings are stale),
   worktree teardown, and the promotion decision — `dev` is 42+ commits ahead of `main`/`prod`,
   which remain at `7765cbee`.

---

## 7 · Worktrees left on the original machine

`cat-c-erp-hooks` · `shape5-social-wiring` · `shape5-remaining-products` · `shape5-therapy-orbity` ·
`cat-c-orbity` · `cat-c-therapy` · `sw-chartcard-test-coverage` · `mcp-rc0-and-dupe-tools` ·
`lying-loading-mode-b-keeper` · `remediation-marker-hygiene` · `igig-cofre-declare-and-ui` ·
`dependabot-backlog-drain` · `salvage-push-divergence-rootcause` · `ci-provision-mcp-node-deps` ·
`tech-lead-session-wrap`

All except the three above are integrated and safe to tear down with
`task_branch action='cleanup' slug='<slug>' confirm=True` — **after** the MCP server restart, so
the salvage-push fix is actually in effect. Doing it before that will strand a ledger commit in
the primary (that is the whole bug that was fixed).
