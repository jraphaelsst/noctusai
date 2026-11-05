# Audit — `.claude/agents/frontend-engineer.md` → master-level upgrade

Read-only audit, 2026-11-05. Repo: /Users/rapha/Documents/repository/NoctusAI/noctusai. Nothing edited.
(Note: the PostToolUse "new dirt" warning during this audit refers to the two untracked paths that were already in the session-start git status — `products/academia-de-reciclagem/projects/content/05 - Indicadores….docx` and `projects/real-estate-agent/` — not created by this audit.)

## 1 · Verdict

**A strong *house-rules* executor, a thin *craft* executor.** The L1 encodes ~20 hard-won NoctusAI incident lessons (loading lies, cache writes, silent refusals, status_pagina RLS parity, org-admin gate, service worker, consent routes) — each with a keeper and a KB pointer. That is genuinely excellent and should be kept. But almost nothing a world-class FE engineer would treat as baseline craft is codified anywhere it owns: **zero** coverage of accessibility (WCAG/APG), forms (react-hook-form + zod used by 18 of 19 product FEs), query-key architecture, the React "you might not need an effect" model, TypeScript strictness, i18n/Intl formatting, performance/Core Web Vitals, XSS/CSP, Testing Library query priority, or UX writing for empty/error states. It is also **one rule stale** against the 2026-11-04 mockup-first owner rule ("Never mock data" vs "sample content allowed, labelled").

Leanness: 67 lines (target 45–65). Bloat sources: two lines restating universal/protocol rules, a redundant "Owned KB depth" pattern line, two pairs of lines that should merge, an over-long loading-state line that inlines dates + incident counts, and a misowned SVG line.

## 2 · Strengths to keep

- Every domain rule = rule + why + keeper + `→ KB §` — exact house shape (`frontend-engineer.md:36-57`).
- Loading-state two-signal rule (`:46`) is better than most public guidance; aligns with TanStack v5 `isPending`/`isFetching` semantics and the `placeholderData` "keep previous" idiom.
- Cache-writes rule (`:47`) + `useCacheWriteMutation` seed primitive + ratchet keeper = a mechanised version of TanStack's optimistic-update guide.
- Silent-refusal (`:48`) = error-before-empty ordering, a real UX-correctness invariant.
- Seed factories own ErrorBoundary + Suspense (`seed/framework/frontend/src/app.tsx:238-250`) — the L1 rightly says "never hand-wire".
- Org-admin gate is labelled "UX only, the server enforces" (`:49`) — correct security posture.
- Skills it leans on are tight and procedural (`noc-cache-writes` 53 lines, `noc-organ-consume-check` 71, `noc-wiring-audit` 26).

## 3 · Gaps ranked (evidence)

1. **Stale against mockup-first rule (correctness, HIGH).** L1 `:40` "New page ⇒ prototype on REAL data first … Never mock data." The canon now is mockup-first, real data where it exists, *labelled sample* where data doesn't exist yet (`CLAUDE/frontend.md` rule 1; `KB PATTERNS/frontend/prototype-on-real-data.md:1-12`, commit `1fcdb1c60`). A dispatched FE agent would refuse the Twin-editor style mockup.
2. **TypeScript strictness off fleet-wide (HIGH).** `"strict": false` in every active product FE and in the scaffold: `products/seed/frontend/tsconfig.json:14`, `products/core/frontend/tsconfig.json:18` (also `noImplicitAny: false`), `products/social-wiring/frontend/tsconfig.json:14`, agents, monica. Only the seed lib is strict (`seed/lib/frontend/tsconfig.json`). Lint downgrades `no-explicit-any` to warn citing "react-hook-form `as any` workarounds" (`seed/framework/frontend/eslint.config.js`). Seed-level root fix (strict-by-default in scaffold + per-product ratchet), not per-product.
3. **Accessibility: no rule, no tooling (HIGH).** 0 KB hits for WCAG/a11y in owned docs; 0 product FEs with `eslint-plugin-jsx-a11y`, axe-core, or Playwright a11y checks. 54 `<div … onClick>` sites in product FEs; e.g. hand-rolled modal `products/core/frontend/src/pages/admin/AdminPlans.tsx:176` (no focus trap/Esc/aria-modal) though the seed ships Radix `Dialog` (`seed/lib/frontend/src/design-system/ui/Dialog.tsx`, `radix-dialog.tsx`). Brazil adds legal weight (LBI art. 63 requires accessible sites — law URL not verified this pass; eMAG is the gov reference).
4. **Lying value in the canonical formatter (HIGH, same family as lying-loading).** `seed/lib/frontend/src/utils.ts:26-31` `formatCurrency(null) → "R$ 0,00"` — a missing value renders as a real zero (the "all-zeros dashboard" shape). Plus 246 ad-hoc `toLocaleString(`/`new Intl.` sites in product FEs vs a canonical formatter → DRY + inconsistency (no `formatNumber`/`formatPercent`/relative-time helpers).
5. **Contradiction inside owned KB (MED).** `PATTERNS/frontend/frontend.md:40` "`invalidateQueries` — invalidate by matching keys after mutations" contradicts the never-invalidate-only rule (`mutation-cache-writes.md`, L1 `:47`).
6. **Query-key architecture uncodified (MED).** 1,259 inline `queryKey: [` literals vs 38 files using a key factory. Prefix-matching cache writes (`seed/lib/frontend/src/cache-writes.ts:70` "`[resource]` reaches each `[resource, filters]`") only work if keys are hierarchical — a factory makes that correct by construction.
7. **Forms uncodified (MED).** react-hook-form + zod in 18/19 product package.json; 0 KB mention. No rule on schema-from-contract, inline error association (`aria-describedby`/`aria-invalid`), pending-state submit, pt-BR messages.
8. **Effects discipline only half-there (MED).** `frontend.md:69-71` covers "useMemo isn't a side-effect channel" but prescribes `useEffect` as the fix; react.dev's guidance is mostly *derive during render / handle in the event*. 316 `useEffect(` sites in products — no review lens.
9. **Stale/misowned owned docs (MED).** `CONTEXT/frontend/01-CORE.md:8` says core uses "React Router v6 … no TanStack Query"; reality: `react-router-dom ^7`, `useQuery` in 10 core files. `02-ERP`, `03-PF`, `04-THERAPY` describe products that are **asleep** (`deploy/fleet/active-scope.txt:18`); there is **no** FE domain doc for active social-wiring / agents / monica. `svg-render-mode.md` is a *Python* seed adapter (`noctusai_lib.integrations.svg_render`, :12) with zero `.ts/.tsx` consumers — it belongs to backend-engineer; L1 `:52` "not hand-rolled `<svg>` strings in components" isn't what the doc says.
10. **Performance not owned (MED-LOW).** No LCP/INP/CLS budget, no bundle budget (no size-limit / no visualizer), `lazyWithReload` exists in seed lib but isn't in any FE rule (25 product files use lazy). `noc-perf-probe` / `noc-fast-responses` exist but aren't pointed from L1.
11. **Testing craft uncodified (MED-LOW).** Testing Library + user-event in seed lib devDeps, Playwright in 3 products, MSW in 0. No rule on role/label-first queries, user-visible assertions, or network-level mocking; the "dual-React gap" (L1 `:56`) is noted but has no remediation pointer.
12. **XSS/CSP brief missing (LOW).** 2 `dangerouslySetInnerHTML` sites: JSON-LD in `products/core/frontend/src/website/components/FaqAccordion.tsx:43` (`JSON.stringify` doesn't escape `</script>` — safe only while content is static) and `erp-imobiliario/.../chart.tsx:70` (shadcn chart CSS, asleep). No rule.
13. **Open follow-up never closed.** `frontend.md:73` "ts-morph is NOT in the seed FE base devDeps" — still absent from `seed/lib/frontend/package.json` and `seed/framework/frontend/package.json`, yet L1 `:55` mandates ts-morph AST-first. Fix-on-contact candidate.
14. **CI lint covers only an asleep product (flag only — COLLISION ZONE).** `.github/workflows/test.yml:497-498` is the only `npm run lint` step, and it targets erp-imobiliario (asleep). Do not edit here; route to the git/CI redesign session.

## 4 · Team-shape: missing UX/product-design + a11y specialist?

**Yes — one gap is real.** The mockup-first rule (`CLAUDE/frontend.md` rule 1, `prototype-on-real-data.md` §0) makes "author a clickable mockup on seed tokens, iterate with the owner" a **mandatory phase with no owning agent**; frontend-engineer is a Sonnet executor that commits code, architect is system-level. Recommendation: a read-only **`product-designer`** advisor (owns mockup authoring on claude.ai artifacts / the Design type, UX writing pt-BR, heuristic + WCAG audits, the design-token/organ visual contract), and fold the *executor-side* a11y floor into frontend-engineer's L1 + canon. A separate a11y agent is premature (N=0 a11y incidents recorded); put an a11y lens in `compliance-reviewer`'s review checklist instead. Before creating the agent, run `noc-triage` (recurrence: Twin editor + usage dashboard = N=2 mockups in 1 day).

## 5 · Proposed new / replaced L1 one-liners

Canon doc = `KB § PATTERNS/frontend/frontend-craft-canon.md`.

- **(replace :40) Mockup before UI.** No UI before the owner clicks a mockup on seed tokens; real data where it exists, labelled sample only where it doesn't — the validated mockup is the contract. → `KB § PATTERNS/frontend/prototype-on-real-data.md`
- **Accessible by construction (WCAG 2.2 AA).** Interactive = native element or seed Radix primitive (never `div onClick`); every control has a name, visible focus and keyboard path; modals = seed `Dialog`. → `KB § PATTERNS/frontend/frontend-craft-canon.md` (§A11y)
- **Derive, don't sync.** Compute from props/state in render, handle user actions in the event handler; `useEffect` only to sync with an external system. → canon (§React model)
- **Query keys come from the entity's key factory** (`xKeys.all/list(f)/detail(id)` in `hooks/useX.ts`) — hierarchical keys are what make prefix cache-writes and invalidation reach every list. → canon (§Server state)
- **Forms = react-hook-form + zod schema mirrored from the contract;** errors inline, tied to the field (`aria-invalid` + `aria-describedby`), pt-BR copy, submit shows pending. → canon (§Forms)
- **Format through seed Intl helpers (pt-BR, BRL); a missing value renders "—", never 0.** → canon (§i18n)
- **Copy that helps:** empty state = what's here + the next action; error = what happened + how to fix, in plain pt-BR (never "Algo deu errado"). → canon (§UX writing)
- **Tests read like a user:** `getByRole`/`getByLabelText` first, assert what's on screen, mock at the network edge. → canon (§Testing)
- **Ship fast pages:** route-level `lazyWithReload`, no heavy dep without a bundle check, keep INP low (transition non-urgent renders). → canon (§Performance) · skill `noc-perf-probe`
- **No raw HTML:** no `dangerouslySetInnerHTML` except escaped JSON-LD / sanitized output; markdown via `react-markdown` without raw HTML. → canon (§Security)

## 6 · Lossless trim plan (L1 → ~64 lines)

| Line(s) | Action | Where the content lives (lossless) |
|---|---|---|
| :36 Cache-first discovery | DELETE | CLAUDE.md §1 "Cache-first search" (auto-loaded) — duplication anti-pattern per agent-context-architecture |
| :57 Heavy runs / hw gate | DELETE | `engineer-seed.md` standing protocol (already referenced at :30; hw_admission present there) |
| :41 + :42 Core URL + cross-product nav | MERGE to one line | both already in `core-url-routing.md` |
| :43 + :44 status_pagina nav + RLS parity | MERGE to one line | `status-pagina-dev-visibility.md`, `product-internal-wiring.md` |
| :46 loading-state | SHORTEN: drop dates, "70 sites", keeper-severity prose | all in `lying-loading-state.md` §Both incidents / §detector |
| :47 cache writes | SHORTEN: drop "orbity ~2 s, 2026-10-21" | `mutation-cache-writes.md` §Why |
| :52 SVG | DELETE + move `svg-render-mode.md` to backend-engineer owns_kb | doc is a Python seed adapter |
| :63 "Frontend patterns →" depth line | DELETE | every path is already pointered in a domain rule (keeper leg 1b satisfied) |
| :64 domain line | KEEP, update to active products | see §7 |
| :55 AST-first | SHORTEN to the FE-specific half (outline-corpus coupling); AST-first is §1 | CLAUDE.md §1 + `ast.md` |
| :56 prod-shape | KEEP; add pointer for the dual-React gap remediation if one exists | `dev-prod-parity.md` |
| :59-60 Commit ownership | **FLAG ONLY — merge-flow, collision zone**; leave until the git redesign lands | engineer-seed protocol |

Net ≈ −8 lines, +7 new → ~64–66.

KB-side cleanups (not L1): fix `frontend.md:40` (point to cache-writes); move `frontend.md:69-73` useMemo section into canon §React model; `lying-loading-state.md:279-463` (~185 lines of detector internals) could split to a keeper doc but is acceptable depth.

## 7 · Frontmatter issues

- `owns_kb` includes `PATTERNS/frontend/svg-render-mode.md` (Python/backend) → transfer to backend-engineer.
- `CONTEXT/frontend/02-ERP.md`, `03-PF.md`, `04-THERAPY.md` = asleep products; `01-CORE.md` stale (RR v6 / no TanStack). Mark asleep docs as such or archive via `noc-archive-absorb`; refresh 01-CORE; add `CONTEXT/frontend/05-SOCIAL-WIRING.md` (+ agents, monica) when touched.
- Add `PATTERNS/frontend/frontend-craft-canon.md` to owns_kb (keeper leg 1b requires a body pointer — the new rules provide it).
- `description` omits accessibility, forms, mockup; suggest: "…React pages/components, forms, accessible design-system usage, TanStack Query hooks, all four states, vite build + vitest…".
- `tools` lacks `WebFetch` — optional; useful for checking primary docs (react.dev/TanStack) when a canon rule is ambiguous.
- `model: sonnet` fine for an executor; mockup/design judgment argues for the advisor in §4 rather than upgrading this model.

## 8 · Craft-canon KB doc — `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend/frontend-craft-canon.md`

Outline (each section: principle → house mechanism (seed export / keeper) → do/don't → checklist → sources):
0. How to use (decision checklist for any UI slice; links to house rules it complements, not duplicates)
1. React model — thinking in React (component hierarchy, minimal state, where state lives), purity / Rules of React, derive-don't-sync, effects only for external systems, keys & identity, Suspense + transitions (`useTransition` for non-urgent updates), error boundaries (seed-owned; when a local boundary is warranted), React Compiler readiness
2. State architecture — server vs client vs URL vs form state; Zustand scope; URL as state for filters/pagination (react-router search params)
3. Server state (TanStack v5) — important defaults (staleTime 0, retry 3, refetchOnWindowFocus — and the seed's overrides in `query-client.ts`), key factories, `select` + structural sharing render optimisations, `enabled`, `placeholderData`, polling (`jobPolling`), mutations → pointer to cache-writes; anti-patterns (copying query data into state, `useEffect` fetches)
4. Component architecture & design system — atoms/organs mapping to Atomic Design, compound components, headless (Radix) + tokens, named seams, when to promote to seed (`noc-organ-consume-check`)
5. TypeScript — strict ratchet plan, `noUncheckedIndexedAccess`, types from the contract (no `as any` on payloads), discriminated unions for states, `satisfies`
6. Forms — RHF + zodResolver, schema shared with contract, server-error mapping to fields, inclusive-form rules (labels, instructions, error identification/suggestion, no placeholder-as-label), pending/disabled
7. Accessibility (WCAG 2.2 AA) — semantic HTML first, APG patterns (dialog, menu, tabs, combobox) via Radix, focus management/visible focus, target size 2.5.8, contrast via tokens, live regions for toasts/async, reduced motion; tooling: jsx-a11y, axe in vitest/Playwright; eMAG/LBI note
8. i18n & pt-BR — Intl.NumberFormat/DateTimeFormat/RelativeTimeFormat/PluralRules, BRL, timezone (America/Sao_Paulo) and DATE-only parsing (already in `formatDate`), null ≠ 0, CPF/CNPJ/phone masks (`phone.ts`, `identificador.ts`)
9. Performance — CWV thresholds (LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1), route-level splitting (`lazyWithReload`), bundle budget, image sizing/CLS, list virtualisation, avoiding render cascades; measure with `noc-perf-probe`
10. Testing — trophy (static → unit → integration-heavy → few E2E), Testing Library priority + user-event, MSW at the network edge, Playwright (role locators, a11y scan), the in-flight cache assertion, the dual-React harness gap
11. Security — React auto-escaping and its exits (`dangerouslySetInnerHTML`, `href="javascript:"`, markdown raw HTML), JSON-LD escaping, CSP posture, no secrets in `VITE_*`, authorisation is server-side
12. UX writing & heuristics — Nielsen's 10 applied to empty/error/loading/success, pt-BR voice, error-message guidelines
13. Review checklist (one page) + anti-pattern gallery with in-tree file:line examples
14. Sources

### Worked examples (grounded)

**WE1 — Hand-rolled modal → seed Dialog (a11y + organ consumption).** `products/core/frontend/src/pages/admin/AdminPlans.tsx:176` renders `<div className="fixed inset-0 …" onClick={() => setShowModal(false)}>` with an inner `stopPropagation` div. Missing: focus moves into the dialog and is trapped, Esc closes, `role="dialog"` + `aria-modal` + labelled title, focus returns to the trigger. Fix: consume `Dialog` from `@noctusai/lib/design-system` (Radix — implements the APG modal-dialog pattern). Test: `await user.click(getByRole('button', {name: /novo plano/i}))`; `expect(getByRole('dialog', {name: /novo plano/i})).toBeInTheDocument()`; `await user.keyboard('{Escape}')`; assert focus back on the trigger. Shows §4, §7, §10 together.

**WE2 — `formatCurrency(null) → "R$ 0,00"` (lying value).** `seed/lib/frontend/src/utils.ts:26-31`. A KPI tile with no data yet shows "R$ 0,00", indistinguishable from a real zero — the all-zeros-dashboard shape the wiring audit hunts. Canon fix (seed-level, pilots first): `formatCurrency(v, { empty: '—' })` default "—" for null/undefined, keep `0 → R$ 0,00`; cache the `Intl.NumberFormat` instance; add `formatNumber/formatPercent/formatRelative`; then a recurrence sweep of the 246 ad-hoc `toLocaleString`/`new Intl.` sites in product FEs. Shows §8 + the server-state family "never lie".

**WE3 — Key factory makes cache writes correct by construction.** 1,259 inline `queryKey: [` literals across product FEs vs 38 factory files. `useCacheWriteMutation` prefix targets (`cache-writes.ts:70`) only reach every filtered list if all list keys share the prefix. Canon shape in `hooks/useLeads.ts`:
```ts
export const leadKeys = {
  all: ['leads'] as const,
  lists: () => [...leadKeys.all, 'list'] as const,
  list: (f: LeadFilters) => [...leadKeys.lists(), f] as const,
  detail: (id: string) => [...leadKeys.all, 'detail', id] as const,
};
// mutation target: { queryKey: leadKeys.lists(), match: 'prefix' }
```
A typo'd literal (`['lead', f]`) silently escapes the write — the factory removes the class. Shows §3 + ties to `mutation-cache-writes.md`. (Candidate keeper later: `queryKey` literal outside `hooks/` — triage at N.)

(Optional WE4 — strict ratchet: `products/seed/frontend/tsconfig.json:14` strict false ⇒ every scaffolded product inherits it; flip in scaffold + baseline-ratchet per product, pilots first.)

## 9 · Sources (all URLs returned HTTP 200 on 2026-11-05)

| Title | URL | Supports |
|---|---|---|
| Thinking in React | https://react.dev/learn/thinking-in-react | §1 hierarchy, minimal state |
| You Might Not Need an Effect | https://react.dev/learn/you-might-not-need-an-effect | derive-don't-sync rule |
| Rules of React | https://react.dev/reference/rules | purity, hooks rules |
| `<Suspense>` | https://react.dev/reference/react/Suspense | §1 suspense |
| useTransition | https://react.dev/reference/react/useTransition | INP / non-urgent renders |
| Error boundaries (Component ref) | https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary | §1 boundaries |
| React Compiler | https://react.dev/learn/react-compiler | §1 readiness |
| TanStack Query — Important Defaults | https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults | §3 defaults |
| TanStack Query — Query Keys | https://tanstack.com/query/latest/docs/framework/react/guides/query-keys | key-factory rule |
| TanStack Query — Optimistic Updates | https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates | cache-writes alignment |
| TanStack Query — Render Optimizations | https://tanstack.com/query/latest/docs/framework/react/guides/render-optimizations | `select`, structural sharing |
| Effective React Query Keys (TkDodo) | https://tkdodo.eu/blog/effective-react-query-keys | key factories |
| Practical React Query (TkDodo) | https://tkdodo.eu/blog/practical-react-query | server vs client state |
| TSConfig `strict` | https://www.typescriptlang.org/tsconfig/#strict | §5 strict ratchet |
| TSConfig `noUncheckedIndexedAccess` | https://www.typescriptlang.org/tsconfig/#noUncheckedIndexedAccess | §5 |
| WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | a11y floor |
| Understanding 2.5.8 Target Size (Minimum) | https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | §7 |
| WAI-ARIA APG | https://www.w3.org/WAI/ARIA/apg/ | §7 patterns |
| APG Dialog (Modal) pattern | https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ | WE1 |
| W3C WAI Forms Tutorial | https://www.w3.org/WAI/tutorials/forms/ | §6 inclusive forms |
| Radix Primitives — Accessibility | https://www.radix-ui.com/primitives/docs/overview/accessibility | seed primitives satisfy APG |
| eslint-plugin-jsx-a11y | https://github.com/jsx-eslint/eslint-plugin-jsx-a11y | static a11y lint |
| axe-core | https://github.com/dequelabs/axe-core | automated a11y checks |
| Playwright — Accessibility testing | https://playwright.dev/docs/accessibility-testing | E2E a11y scan |
| Playwright — Best practices | https://playwright.dev/docs/best-practices | role locators, user-visible |
| eMAG (Modelo de Acessibilidade em Governo Eletrônico) | https://emag.governoeletronico.gov.br/ | BR a11y reference |
| Web Vitals | https://web.dev/articles/vitals | LCP/INP/CLS thresholds |
| Interaction to Next Paint | https://web.dev/articles/inp | INP |
| Optimize LCP | https://web.dev/articles/optimize-lcp | LCP |
| Cumulative Layout Shift | https://web.dev/articles/cls | CLS |
| Rendering performance | https://web.dev/articles/rendering-performance | render cost |
| Vite — dynamic import | https://vite.dev/guide/features.html#dynamic-import | code splitting |
| React Hook Form — useForm | https://react-hook-form.com/docs/useform | §6 |
| Zod | https://zod.dev/ | §6 schema |
| Testing Library — Guiding Principles | https://testing-library.com/docs/guiding-principles | §10 |
| Testing Library — Query priority | https://testing-library.com/docs/queries/about/#priority | role/label first |
| The Testing Trophy (Kent C. Dodds) | https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications | §10 test mix |
| Compound components with hooks (KCD) | https://kentcdodds.com/blog/compound-components-with-react-hooks | §4 |
| Atomic Design ch.2 | https://atomicdesign.bradfrost.com/chapter-2/ | §4 atoms/organs |
| MSW docs | https://mswjs.io/docs/ | network-edge mocking |
| MDN Intl.NumberFormat | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat | WE2 |
| MDN Intl.DateTimeFormat | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat | §8 |
| OWASP XSS Prevention Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html | §11 |
| OWASP CSP Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html | §11 |
| NN/g 10 Usability Heuristics | https://www.nngroup.com/articles/ten-usability-heuristics/ | §12 |
| NN/g Error-Message Guidelines | https://www.nngroup.com/articles/error-message-guidelines/ | §12 UX writing |

Not cited (failed verification): gov.br eMAG model page (404); planalto LBI 13.146 (timeout) — re-verify before citing art. 63.

## 10 · Merge-flow lines (collision zone — flag, don't edit)

- `frontend-engineer.md:59-60` "Commit ownership — Worktree off `origin/dev`; commit ONLY `feat/<your-branch>` … The tech-lead merges."
- `frontend-engineer.md:3` description tail "Works in an isolated worktree; commits ONLY its own branch."
- `frontend-engineer.md:30` engineer-seed protocol bullet list (stay-in-worktree · commit-own-branch-only).
- `frontend-engineer.md:57` mentions `task_branch` integrate as self-gating.
- `.github/workflows/test.yml:497-498` only FE lint step targets asleep erp-imobiliario — hand to the CI redesign session.
