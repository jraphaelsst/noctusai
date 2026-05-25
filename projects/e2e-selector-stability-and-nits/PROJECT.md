# e2e-selector-stability-and-nits — Project Document

> Filed 2026-05-23 to give durable form to post-green-batch nits **recovered from
> git after a /clear** lost the prior session's checkpoint shorthand. The act of
> filing this IS the remediation for [[feedback_checkpoint_shorthand_evaporates]].
> Symbol-first per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-23
- **Status:** ⏳ OPEN (low-priority hygiene; recovered, not yet actioned)
- **Owner:** joaoraphaelsst@gmail.com · architect

## 1 · Recovered items (with their evidence)

### 3e — E2E selector-coupling + seed `data-testid` (✅ recovered from committed code)
The E2E modernization (`origin/main` `e65c1d61` erp + `0fba2d05` core) got specs
green by retargeting to **Portuguese text/role/label selectors** — e.g.
`getByRole('button', {name:'Entrar'})`, `getByText('Esqueceu a senha?')`,
`getByRole('link', {name:'Esqueceu a senha?'})`. Seed FE ships **zero
`data-testid`** (verified: `grep -r data-testid seed/.../frontend/src` → none).
**The nit:** these tests are brittle — a copy / i18n change silently breaks the
suite (a coupling to user-visible strings, not a stable contract).
- **P1** — ✅ DONE 2026-05-25 (branching-methodology dogfood): selector-coupling tradeoff documented in `KB § PATTERNS/testing.md` (test-types → **Selector stability (Playwright)**). text/role = fast-green but copy-fragile; `data-testid` = stable but needs seeding. *(P2 testid-seeding + 3c keeper str→Path nit remain — P2 is a seed-FE-propagate change; 3c is `[A]`-leaning + collides on compliance.py.)*
- **P2** — add `data-testid` to the seed FE design-system components the E2E suites target (LoginForm, nav, key tables), then migrate the brittle text/role assertions to testids. Pilot-products-first (core + erp have E2E today). Seed FE change ⇒ goes through the seed→propagate cadence.

### 3c — keeper `str`→`Path` nit (🟡 partial recovery)
~8 keepers in `mcp/noctusai/tools/noctus/dev/compliance.py` extract the product
slug via the string idiom `relative.split("/", 2)[1]` rather than `Path` parts
(lines incl. 1226, 1566, 1826, 1906, 3497, 3620, 6971). Minor robustness/style:
a shared `_product_slug_from_rel(path)` helper using `Path` semantics would DRY
the idiom + harden against odd separators. Debatable value (input is already a
relative posix string) — triage `[A]`-leaning unless a bug surfaces.

## 2 · NOT recovered (logged honestly — see the lesson)
- **3b "transacoes comment"** — zero trace in commits/comments/stash/deleted-files/dangling-commits.
- **3d "review.py reg-q"** — zero trace; `review.py` has no recent touch or marker.
These were chat-checkpoint shorthand the prior session never persisted; their
meaning was lost at `/clear`. Captured as the lesson [[feedback_checkpoint_shorthand_evaporates]]. If the user recalls the specifics, reopen here.

## 3a · Seed-first analysis
3e/P2 is a seed concern (data-testid on shared design-system components → 0
per-product attribute code; E2E targets the seeded ids). 3c is a single-file MCP
helper. Both seed-first by construction.

## 11 · Change log
- 2026-05-23 — filed; 3e recovered from committed E2E diffs, 3c partial; 3b/3d unrecoverable (logged). Remediation for the checkpoint-shorthand lesson.
