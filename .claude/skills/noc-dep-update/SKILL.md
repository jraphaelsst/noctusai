---
name: noc-dep-update
description: Use for ANY npm dependency change — triggers "bump X", "update dependency", "dependabot PR", "CVE / security alert", "this PR can't go green", "migrate to vN", "pin this version", "upgrade react-router / postcss / vite". Four decision gates that stop the two recurring traps — freezing the fleet with an exact `overrides` pin, and mistaking a self-inflicted block for upstream incompatibility.
version: 1.0.0
---

# noc-dep-update — how to change a dependency without freezing the fleet

🔴 **Two traps, both evidenced 2026-08-11:**
- **The CVE fix creates the freeze.** postcss, ws and react-router were each pinned to an EXACT version in `overrides` by a security cleanup. All three froze the whole fleet — the seed copies `overrides` into 12 products + the template, so **one pin becomes 14**.
- **"Upstream incompatibility" that is actually ours.** Dependabot's `react-router-dom@7` PR could never go green because *our own* `peerDependencies: ^6.0.0` and `overrides: 6.30.4` contradicted it. The real migration was package.json-only and needed **zero** source edits.

## The one fact that decides most of this

> **`package-lock.json` is already the freeze.** CI builds with `npm ci`, which installs the lockfile **exactly**. Nothing floats at build time whether you declare `^8.5.18` or `8.5.18`.

Proof: converting all 20 exact overrides to carets produced **zero lockfile change** across 14 manifests. So an exact `overrides` pin adds **no** reproducibility and removes **all** upgradeability — strictly dominated, not a tradeoff. When someone proposes pinning "for safety", ask where the lockfile is first.

## The three declaration sites — they must never contradict

| Site | Says | Owner |
|---|---|---|
| `seed/{lib,framework}/frontend` `peerDependencies` | the **contract** (`^7.0.0`) | seed |
| `products/<slug>/frontend` `dependencies` | the **request** | product |
| `package-lock.json` | the **resolution** (`7.18.2`, exact) | product |

`overrides` is the odd one out: it **wins over all three**, silently, fleet-wide. That is why it is gated.

## Gate 1 — adding/raising a constraint (a CVE, a needed feature)

1. Prefer the **direct dependency**. Only reach for `overrides` when the vulnerable package is **transitive** and no direct bump pulls the fix.
2. If you must use `overrides`: **write a RANGE, never an exact version.** `"^8.5.18"` holds the CVE floor AND pins the major. `"8.5.18"` blocks every future patch.
3. Change the seed `peerDependencies` in the **same commit** if the major moved — a peer range that contradicts the override is the bug.
4. `npm install --package-lock-only` in each affected package, then commit the lockfiles.

Gated by `check_override_is_range` (severity `high`; pre-commit when an npm manifest is staged + the `check_all_products()` aggregate). Genuine freeze ⇒ add a `pin-ok` / `deliberate-freeze` rationale comment; it is an escape hatch, not a default.

## Gate 2 — a dependabot PR that will not go green

**Check OUR constraints before concluding upstream incompatibility.** In order:

1. `grep -n '"<pkg>"' seed/*/frontend/package.json products/*/frontend/package.json` — do `peerDependencies` / `overrides` / `dependencies` **agree** with the proposed version? A single-package PR cannot fix a three-site contradiction, so it will fail forever.
2. Is the failing job even about this dep? Most red dependabot PRs here are **stale-base** failures (Trivy / MCP Toolkit / Bandit) that pass on current `dev`. Rebase before diagnosing.
3. Only after 1–2 come back clean is it genuinely upstream.

**Majors are coordinated migrations, not bumps** — `.github/dependabot.yml` ignores react-router semver-majors for exactly this reason. Do them by hand (Gate 3).

## Gate 3 — a MAJOR migration (measure before you size it)

1. **Measure the real API surface** — from `src/` only:
   ```
   # QUOTE the --include globs: zsh expands a bare *.tsx and the command dies
   # with "no matches found" before grep ever runs.
   grep -rho "import[^;]*from ['\"]<pkg>['\"]" --include="*.tsx" --include="*.ts" \
     seed/lib/frontend/src seed/framework/frontend/src products/*/frontend/src \
     | grep -o "{[^}]*}" | tr -d '{}' | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sort -u
   ```
   🔴 **Never grep with `node_modules` in scope** — it reports symbols the vendor uses internally, not ours. That is how `FutureConfig` looked like a blocker when our source never touched it.
2. Read the upstream breaking-change list and intersect. react-router v6→v7 was 11 symbols, all unchanged ⇒ zero source edits. A "major" is often a non-event for a declarative subset.
3. Move **all three sites together**, carets not exacts.
4. Regenerate every lockfile, then verify with the commands **CI actually runs**:
   - `npm run check` in `seed/lib/frontend` + `seed/framework/frontend` (tsc --noEmit, strict)
   - `npm run build` for each live product (`deploy/fleet/build-scope.txt`)
   - `npx vitest run` for products that have suites
5. **Diff the lockfiles.** No change ⇒ no image change ⇒ no redeploy needed. Say so instead of deploying for nothing.

## Gate 4 — one product needs to lag

**No new mechanism.** Pin in that product's **own `dependencies`** — scoped to one product, visible where reviewers look, cannot leak to the other 11. `check_override_is_range` deliberately does **not** flag this.

Do **not** "solve" it by giving each product an independent version set: the seed's peer range is what guarantees a *single* React/router instance at runtime, and diverging there produces the two-copies-of-React class of bug. **One contract, many resolutions.**

## Guardrails

- A `seed/**` edit scopes the build to the **active set** (`deploy/fleet/build-scope.txt`), not the whole fleet — expect ~6 images, not 11.
- Runtime routing/render breakage is **not** covered by any automated gate (`/api/health` is backend; the edge returns 200 for a broken bundle). After a routing/UI-library change, verify the real page: deep-link 200s + fetch the JS bundle + grep for a version marker.
- Never `--no-verify` to get past the override gate.

## Depth

`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md § Fourth axis` (why an exact override is a fleet freeze; the lockfile-is-the-freeze proof) · `KB § PATTERNS/architect/seed-canonical-defaults.md` (an exact version is never a canonical answer) · skill `noc-ship` (promote/deploy once the change warrants it).
