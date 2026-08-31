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
| `feat/cat-c-erp-hooks` | ✅ **COMPLETE + pushed** | 20 |
| `feat/shape5-remaining-products` | ⚠️ **PARTIAL + pushed** | 2 (p-studio, adconnect) |
| `feat/shape5-social-wiring` | ❌ **NOT pushed — zero commits existed** | 0 |

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

## 3 · `feat/shape5-remaining-products` — PARTIAL

**Committed + pushed (2 commits):** p-studio and adconnect Shape-5 eliminated.

**Uncommitted at snapshot time:** 23 changed files, captured as
`shape5-remaining-products.uncommitted.patch` (29 KB) with `…status.txt` alongside.
Remaining products in its scope: **core, daily-life, personal-finance**
(measured pre-fix: core 1, daily-life 5, personal-finance 14).

**To resume on another machine:**
```bash
git fetch origin && git checkout feat/shape5-remaining-products
git apply project-history/session-snapshots/2026-08-31/shape5-remaining-products.uncommitted.patch
```
Then verify per product (`tsc` / `vitest` / `vite build`, exit codes via `rc=$?`) before committing.
**Review the patch before applying** — it is a point-in-time capture of an agent mid-edit, so it
may contain a half-finished file. Prefer re-doing a product cleanly over trusting a partial hunk.

---

## 4 · `feat/shape5-social-wiring` — NOT PUSHED, patch is the only durable copy

The engineer had made **zero commits** after ~45 minutes; all 35 changed files were uncommitted.
Captured as `shape5-social-wiring.uncommitted.patch` (84 KB) + `…status.txt`.

Its scope was: the 2 Mode-B sites (`pages/Equipe.tsx:91`, `pages/meta/AdDetalheModal.tsx:293` —
these were relayed from a run that could not be reproduced, so **verify them with the scanner
before assuming they are real**) plus 27 Shape-5 sites measured at `216daf12`.

**To resume:**
```bash
git fetch origin && git checkout -b feat/shape5-social-wiring origin/dev
git apply project-history/session-snapshots/2026-08-31/shape5-social-wiring.uncommitted.patch
```
Same caution as §3, and more of it — this work never reached a single commit, so nothing in it was
ever gate-checked. `products/social-wiring/frontend` has a ~996-test suite; run it fully.
**Do not weaken `pages/leads/*.test.tsx`** — those gained real Mode-A/Mode-B guards this session.

Honestly assessed: re-running this slice from scratch against the current `dev` may be cheaper and
safer than reconciling a 35-file uncommitted patch. The patch exists so the option is yours, not
so it must be used.

---

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
