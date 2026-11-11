# Accessibility — WCAG 2.2 AA for our stack, design-time first

> **What it is.** The accessibility contract for every NoctusAI screen: the WCAG 2.2 AA criteria that
> matter most for our UIs (dense CRM/ERP tables, forms, dialogs, dashboards, chat), the checks a
> designer runs on a mockup BEFORE code exists, the keyboard + screen-reader walkthrough protocol, the
> measured gaps in the seed and products today, the tooling targets, the Brazilian legal frame (LBI,
> ABNT NBR 17225, eMAG) and an audit report template. Owned by `product-designer`
> (`.claude/agents/product-designer.md`).
>
> **Why it exists.** One a11y commit in 4,035, zero a11y keepers, zero product FEs with
> `eslint-plugin-jsx-a11y`/axe (audit 2026-11-05, `archive/projects/2026-11-05/01-agent-refinement/audits/audit-missing-hires.md` §3).
> Measuring for this doc found worse than the audit said: the seed **removes every focus indicator
> globally** and the seed `Button` never adds one back, and most status-colour token pairs fail contrast
> (§3). Accessibility that is not designed in is retro-fitted at N× the cost, product by product.
>
> **How to use it.** Designer: run §4 on every mockup and §5 on every sign-off; file findings with §8.
> Frontend: the IMPLEMENTATION rules (semantic HTML, Radix primitives, ARIA, tests) live in
> `KB § PATTERNS/frontend/frontend-craft-canon.md` §7 (frontend-owned) — this doc does not restate them,
> it owns the criteria, the design-time checks, the audit and the legal frame. **The house mechanism
> wins**: when a seed organ already implements a pattern (Radix dialog, `Sidebar` `aria-current`,
> `QueryErrorState` `role="alert"`), consume it; never re-specify it per screen.

**Standard term ↔ house term**

| Standard (W3C · ABNT · gov.br) | House term / mechanism | Where |
|---|---|---|
| Success criterion (SC), level A/AA/AAA | "AA floor" — every screen meets A + AA | this doc §2 |
| Design tokens / colour pairs | `--<role>` + `--<role>-foreground` HSL triplets | `seed/lib/frontend/src/design-system/tokens.css:16-171` |
| Theme switch | `.dark` class on `<html>` via `useTheme` | `seed/lib/frontend/src/design-system/useTheme.ts:43` |
| Org brand theme | `BrandProvider` + validated `noctus.brand-tokens/v1` | `seed/lib/frontend/src/design-system/brand-tokens.ts:10-12` |
| Modal dialog (APG) | Radix `CardHubDialog*` · bare `Dialog` (focus in/trap/return, fixed 2026-11-05) | `ui/radix-dialog.tsx` · `ui/Dialog.tsx:110-160` |
| Navigation landmark + current page | `Sidebar` organ (`aria-current="page"`, `aria-expanded`) | `design-system/components/Sidebar.tsx:312`, `:341` |
| Status message (4.1.3) | `QueryErrorState`/`RetryableError` `role="alert"`; sonner toasts | `seed/lib/frontend/src/components/RetryableError.tsx` |
| Conformance evaluation (WCAG-EM) | a11y audit report (§8) attached to the mockup sign-off | `KB § PATTERNS/design/mockup-protocol.md` §7 |

---

## 1 · The legal and normative frame (Brazil)

- **Lei 13.146/2015 (LBI — Estatuto da Pessoa com Deficiência), art. 63** — accessibility is mandatory
  on websites kept by companies headquartered or with commercial representation in Brazil, or by
  government bodies, "for the use of people with disabilities", following internationally adopted
  best practices; §1 requires the sites to display an accessibility symbol prominently. Verified on
  planalto.gov.br 2026-11-05 (§Sources). ⇒ Store, the community portal, the white-label approval
  portal and noctusai.com are in scope; logged-in B2B tools are in scope too (they are websites run
  by a Brazilian company). Whether a given product's exposure creates enforcement risk is a legal
  question → agent `legal-advisor` (W2-S3) / an OAB lawyer, not this doc.
- **ABNT NBR 17225:2025 — "Acessibilidade em conteúdo e aplicações web — Requisitos"**, first edition
  2025-03-11, ABNT/CB-040. Its scope note states the international guideline it adopts is **WCAG 2.2**;
  Section 5 is built from the WCAG 2.2 success criteria, split into "requisito" and "recomendação",
  with levels A/AA/AAA, and calls AA "the recommended level for most web content". ⇒ Meeting WCAG 2.2
  AA is also how we meet the Brazilian technical standard. Verified from the PDF hosted by the Câmara
  dos Deputados (§Sources).
- **eMAG 3.1 (Modelo de Acessibilidade em Governo Eletrônico)**, April 2014, built on WCAG 2.0;
  mandatory for federal government sites (Portaria nº 3/2007). Not binding on us; useful for two
  Brazilian conventions users of gov.br sites expect: skip links to content / menu / search as the
  first links on the page (Recomendação 1.5), and no repeated `accesskey`. Treat it as a reference,
  not the floor (it predates WCAG 2.1/2.2).
- **Lei 15.263/2025 (Política Nacional de Linguagem Simples)** binds public administration, not us,
  but its art. 5 techniques are the best pt-BR plain-language checklist available, including "use
  language accessible to people with disabilities" → used in `KB § PATTERNS/design/design-craft-canon.md` §8.

**Floor:** WCAG 2.2 **Level AA** on every screen, light AND dark. AAA criteria are targets where cheap
(2.4.13 Focus Appearance is our ring spec, §2.3), never a gate.

---

## 2 · The criteria that matter most for our UIs

WCAG 2.2 (W3C Recommendation, 2023-10-05) added nine criteria; six are A/AA: 2.4.11 Focus Not
Obscured (Minimum) AA · 2.5.7 Dragging Movements AA · 2.5.8 Target Size (Minimum) AA · 3.2.6
Consistent Help A · 3.3.7 Redundant Entry A · 3.3.8 Accessible Authentication (Minimum) AA. 4.1.1
Parsing was removed. The table is ordered by how often our screens break them.

| SC (level) | What it requires (paraphrase) | Where our screens break it | Design-time check |
|---|---|---|---|
| 2.1.1 Keyboard (A) | all functionality operable by keyboard | product cards launched by `<div onClick>` — ✅ FIXED 2026-11-05: native stretched `<button>` (`products/core/frontend/src/pages/Dashboard.tsx:297-310`; test `Dashboard.launch.test.tsx`) | §4.6 walk the mockup with Tab only |
| 2.4.7 Focus Visible (AA) | a visible keyboard focus indicator | ✅ FIXED 2026-11-05: global reset replaced by a `:focus-visible` ring on `--ring` (`tokens.css:182-189`); seed `Button` has its own ring (`ui/Button.tsx:76`). Was: seed killed outlines globally | every interactive element in the mockup has a drawn focus state |
| 1.4.3 Contrast (Minimum) (AA) | text ≥ 4.5:1; large text (≥ 24 px, or ≥ 18.5 px bold) ≥ 3:1 | `muted-foreground` on any light surface 3.48-3.98; white on status colours 2.15-2.67 (§3) | §4.1 contrast table per token pair used |
| 1.4.11 Non-text Contrast (AA) | UI component boundaries, states, focus indicators and meaningful graphics ≥ 3:1 vs adjacent colours | `--border`/`--input` on card 1.32 (light) / 1.25 (dark) — an input whose border is its only identifier fails | §4.1 · inputs carry a visible label AND a 3:1 boundary |
| 1.4.1 Use of Color (A) | colour never the only signal | status chips, chart series, "DEV" badge | every state = colour + text/icon |
| 2.5.8 Target Size (Minimum) (AA) | pointer targets ≥ 24×24 CSS px, or spaced so 24 px circles don't overlap (exceptions: equivalent control, inline, UA-default, essential) | seed sizes are fine (`Button` `sm`/`icon` = 28 px, `md` = 32 px, `Button.tsx:52-56`); hand-rolled icon buttons in dense tables and the "x" close in `OrgPickerModal.tsx:160` are not | measure icons + row actions at 1× in the mockup |
| 2.4.11 Focus Not Obscured (Min) (AA) | a focused component is not entirely hidden by author content | sticky headers, sticky table headers, toasts at `top-right` (`seed/framework/frontend/src/app.tsx:525`) | scroll a long list with Tab in the mockup |
| 1.3.1 Info and Relationships (A) | structure conveyed visually is programmatic | unbound `<label>`s (canon §13.2); tables without `<th scope>`; headings by font size only | annotate headings (h1-h3), table headers, label↔field pairs on the mockup |
| 3.3.1 Error Identification (A) · 3.3.3 Error Suggestion (AA) | errors described in text; suggestion offered when known | generic copy (`ErrorBoundary.tsx:86-91`); raw server text (`OrgPickerModal.tsx:208`) | every error state in the mockup has the 3-part copy (canon §8) |
| 3.3.2 Labels or Instructions (A) | inputs have labels/instructions | placeholder-as-label | no placeholder-only field in a mockup |
| 4.1.2 Name, Role, Value (A) | name + role programmatically determinable | icon-only buttons without a name; repeated identical row buttons ("Registrar investimento" × 23, `PortaisTable.tsx:114-121`) | name every icon button; row actions say which row |
| 4.1.3 Status Messages (AA) | status messages reach AT without moving focus | loading text without `role="status"` (`OrgPickerModal.tsx:87-88`) | mark which messages are status (polite) vs alert |
| 1.4.10 Reflow (AA) | no 2-D scroll at 320 CSS px width (except data tables, maps, diagrams) | wide forms, side-by-side panels | mockup at 375 px and 320 px |
| 1.4.4 Resize Text (AA) · 1.4.12 Text Spacing (AA) | 200 % text, extra spacing without loss | fixed-height cards (`h-28` skeleton → real card), truncation without tooltip | zoom the mockup to 200 % |
| 2.5.7 Dragging Movements (AA) | every drag has a single-pointer alternative | kanban (`components/kanban/KanbanCard.tsx`), Twin timeline, file drop zones | every drag interaction has a menu/button equivalent |
| 3.3.7 Redundant Entry (A) | don't ask again for what the user already gave in the same process | multi-step wizards (contract generator, signup brand step) | carry values forward in the flow diagram |
| 3.3.8 Accessible Authentication (Min) (AA) | no cognitive test (memorise/transcribe) to log in, unless an alternative | 2FA code entry must allow paste; no CAPTCHA puzzles | login/2FA flow allows paste + password managers |
| 3.2.6 Consistent Help (A) | help mechanisms in the same relative order across pages | ⓘ formula tooltips, support links | help lives in the same place on every screen of a product |
| 2.4.3 Focus Order (A) | focus order preserves meaning | modals that leave focus behind; drawers appended at body end | annotate expected Tab order on complex screens |

### 2.1 Large text, exactly
"Large" = ≥ 18 pt regular (≈ 24 px) or ≥ 14 pt bold (≈ 18.5 px) (Understanding 1.4.3). With the
Tailwind default scale our products use (no custom `fontSize` in `tailwind.config.base.ts`): only
`text-2xl` (24 px) and up is large regular text; `text-xl` (20 px) counts as large ONLY if bold. Body
`text-sm` (14 px) and `text-xs` (12 px) always need 4.5:1. Thresholds are not rounded: 4.499 fails.

### 2.2 Non-text contrast, exactly
Applies to what identifies a control and its state (a checkbox outline, an input boundary that is the
only cue, a selected tab underline, a focus ring), and to graphic parts needed to understand content
(chart series, pie slices). Not to disabled controls, logos, or decoration (Understanding 1.4.11).

### 2.3 House focus-ring spec (meets 2.4.7 AA; aims at 2.4.13 AAA)
`focus-visible:ring-2 ring-ring ring-offset-2 ring-offset-background` — the exact classes the seed
`Input` already uses (`ui/Input.tsx:28`). 2 px ring ≥ the 2 CSS px perimeter of 2.4.13; `--ring` vs
card = 6.07:1 light, 4.02:1 dark (≥ 3:1 ✅). The offset keeps it visible on filled buttons.

---

## 3 · Measured gaps (2026-11-05 — re-measure before quoting)

### 3.1 Token contrast (computed from `tokens.css` HSL with the WCAG relative-luminance formula)

Method: each `--x` triplet → sRGB → relative luminance → (L1+0.05)/(L2+0.05). Script kept in the
session scratchpad; re-run on any token change (a seed keeper is the right home — §7).

| Pair (foreground on background) | Light | Dark | Verdict for body text (4.5) / UI (3.0) |
|---|---:|---:|---|
| `foreground` / `background` | 16.38 | 15.34 | ✅ |
| `muted-foreground` / `background` | **3.72** | 6.86 | 🔴 light fails body text (used for every hint, helper and empty-state line) |
| `muted-foreground` / `card` | **3.98** | 6.37 | 🔴 light fails |
| `muted-foreground` / `muted` | **3.48** | 5.45 | 🔴 light fails |
| `primary-foreground` / `primary` | 6.07 | **4.24** | 🔴 dark fails for `text-sm` button labels |
| `secondary-foreground` / `secondary` | 6.89 | **2.85** | 🔴 dark fails both |
| `success-foreground` / `success` | **2.15** | **2.02** | 🔴 fails both, both themes |
| `danger-foreground` / `danger` | **2.67** | **3.00** | 🔴 |
| `info-foreground` / `info` | **2.43** | **2.56** | 🔴 |
| `destructive-foreground` / `destructive` | **2.67** | **2.24** | 🔴 every seed `Button variant="destructive"` label (`Button.tsx:48-49`) |
| `destructive` as text / `card` | **2.67** | 7.60 | 🔴 light: error lines like `OrgPickerModal.tsx:94`, `:173` |
| `warning-foreground` / `warning` | 7.91 | 12.03 | ✅ |
| `border` or `input` / `card` | **1.32** | **1.25** | ⚠️ fails 1.4.11 wherever the border is the only cue |
| `ring` / `card` | 6.07 | 4.02 | ✅ (focus ring ≥ 3:1) |
| `sidebar-foreground` / `sidebar-background` | 14.62 | 15.99 | ✅ |

**What would pass (proposals for the owner — the pastel palette is an owner aesthetic, so this is a
decision, not a fix):** light `--muted-foreground` L ≤ 42 % (0 0% 42% passes on `muted` too); white
text on status fills needs L ≤ 37 % (success, S 40 %), ≤ 54 % (danger/destructive, S 60 %), ≤ 52 %
(info, S 60 %) — or keep the pastel fills and switch their `-foreground` to the dark `foreground`
(`warning` already does this and passes). Dark `--primary` L ≤ 48 % for white labels. Border-as-only-cue
needs L ≤ 58 % (light) / ≥ 41 % (dark) — or make inputs identifiable by label + a stronger boundary on
focus only. Route: owner decision → seed token slice (frontend/seed), pilots first (CLAUDE.md §1).

### 3.2 Focus indicators

- ✅ **FIXED 2026-11-05** (history): `tokens.css` had `*:focus, *:focus-visible { @apply outline-none ring-0; }` in `@layer base`; now `:focus-visible { outline: 2px solid hsl(var(--ring)); outline-offset: 2px }` (`tokens.css:182-189`) and `Button` carries `focus-visible:ring-2` (`ui/Button.tsx:76`). Palette untouched. The paragraph below describes the pre-fix state.
  Utilities win over base, so components that add `focus-visible:ring-*` (seed `Input`,
  `card-hub-button.tsx:31`) still show a ring; **everything else has no focus indicator at all**:
  native `<a>`, raw `<button>`s, `OrgPickerModal` rows (`:113-118`) and the seed `Button` itself
  (`ui/Button.tsx:70-79` — no focus classes). 🔴 Fails 2.4.7 on most screens of every product.
  Fix shape (seed, one place): delete the global reset and put the §2.3 ring into `Button` (and any
  primitive lacking it); a `:focus-visible` default ring in `tokens.css` catches the rest.

### 3.3 Non-native click targets (re-measured; brief said "54 div-onClick sites")

Count of `<div …>` opening tags whose attributes carry `onClick=` (multi-line aware, `.tsx`, tests
excluded, pure `e.stopPropagation()` wrappers excluded), 2026-11-05:

| Scope | `<div onClick>` | of which with `role=` |
|---|---:|---:|
| active product FEs (`core`, `social-wiring`, `agents`, `nosnolimiar`) | 21 (12 · 8 · 1 · 0) | 6 |
| all `products/*/frontend/src` (incl. asleep products) | 71 | 7 |
| `seed/lib/frontend/src` | 11 | 6 |

Not all are defects — three kinds, read each site before calling it:
- **Backdrop of a modal** (`seed/lib/frontend/src/design-system/ui/Dialog.tsx:116`, `SideDrawer.tsx:157`): a pointer convenience
  next to Esc — fine. When the backdrop belongs to a **hand-rolled** modal (`products/core/frontend/src/pages/admin/AdminPlans.tsx:176`,
  `social-wiring/.../Conexoes.tsx:243`, most core admin sites), the defect is the modal (no focus
  management), not the click — route to the Radix dialog.
- **Done right**: `role="button"` + `tabIndex={0}` + Enter/Space handler (`social-wiring/.../esteira/PostCardFace.tsx:49-58`,
  `seed/lib/frontend/src/components/card-hub/CardHubFace.tsx:93-102`) — accessible, though a native `<button>` would be simpler.
- **Mouse-only content** — ✅ both FIXED 2026-11-05 (native `<button>` with a stretched `::after`, click bubbles to the card handler; nested controls raised with `z-10`: `Dashboard.tsx:297-310`, `IntegrationCard.tsx:463-475`; tests `Dashboard.launch.test.tsx`, `IntegrationCard.test.tsx`). Were the real defects: `products/core/frontend/src/pages/Dashboard.tsx:250-261` (the product
  launcher card: no role, no tabIndex, no key handler — a keyboard user cannot open a product from the
  core dashboard) and `seed/lib/frontend/src/design-system/integrations/IntegrationCard.tsx:424-427` (`role="article"` + `onClick`
  opening the account modal). `seed/lib/frontend/src/components/kanban/KanbanCard.tsx:104-113` deliberately leaves Enter/Space
  to dnd-kit's keyboard drag; whether keyboard users can still OPEN a card needs a walkthrough (§5).
The earlier "25 sites in four active FEs" (frontend canon §7) and "54 in product FEs" (audit) used
different scopes and single-line greps; use this table and re-run before quoting.

### 3.4 Dialog focus management

✅ **FIXED 2026-11-05** (`ui/Dialog.tsx:110-160`): initial focus into the panel (first tabbable / panel), Tab trap with wrap, focus return to the opener on close; tests in `ui/Dialog.test.tsx` (user-event). Pre-fix description follows. The bare seed `Dialog` had `role="dialog"`/`aria-modal`/`aria-label` (on the
backdrop, `:116-118`) and Esc, but no initial focus, no Tab trap, no focus return (APG modal pattern).
It is the dialog of the **org picker every multi-org user sees on product entry**
(`OrgPickerModal.tsx:153`). The Radix one (`CardHubDialog*`) is complete. Seed follow-up is
frontend-owned (`frontend-craft-canon.md` §4.2, WE1); designers spec the APG behaviour (§4.7).

### 3.5 Other measured facts
- `<html lang="pt-BR">` in every product `index.html` checked (core, agents, nosnolimiar, commerce, igig …) ✅.
- `useTheme` defaults to light and ignores `prefers-color-scheme` (`useTheme.ts:29-32`) — not a WCAG
  failure; a design decision recorded in the canon §6.4.
- No product runs `eslint-plugin-jsx-a11y`, axe-core or `@axe-core/playwright` (frontend canon §7).

---

## 4 · Design-time checks (run on every mockup — before any code)

1. **Contrast table.** List every token pair the mockup uses (text on surface, icon on surface, border
   on surface, fill + label). Look each up in §3.1 (or compute). Anything below 4.5 (text) / 3.0 (UI)
   is a finding; a red pair from §3.1 is used only for large text or decoration, or the mockup shows
   the proposed passing value and flags it for the owner.
2. **Colour is never alone.** Every status, series and badge has text or an icon too (1.4.1).
   Charts: direct labels or a legend + pattern/shape; the seed chart palette (`tokens.css:89-100`) is
   categorical, not semantic.
3. **Target sizes.** Measure every icon button, row action, chip close and stepper at 1×: ≥ 24×24 px
   or spaced (2.5.8). Prefer the seed sizes (28/32 px).
4. **Focus is drawn.** Each interactive element shows its focus state in the mockup (the §2.3 ring),
   and nothing sticky covers a focused element (2.4.11).
5. **Labels and names.** Every field has a visible label (never placeholder-only); every icon-only
   control has a name written on the mockup annotation; repeated row actions name their row
   ("Registrar investimento — ZAP Imóveis").
6. **Keyboard map.** For each screen: Tab order (number it on complex screens), what Enter/Space/Esc/
   arrows do, where focus lands after open/close/save/delete/route change. A card that launches
   something is a link or button, not a clickable `div`.
7. **Dialogs and drawers** follow the APG modal pattern: initial focus (first field; or the title for
   long content; or the least destructive button for irreversible actions), Tab trapped, Esc closes
   (unless the dialog is a required gate — then an explicit way out, like the org picker's "Sair"),
   focus returns to the trigger, a visible title names it.
8. **Reading order** = visual order; headings h1 (one per page) → h2 → h3 annotated; landmarks:
   header, nav (`Sidebar`), main.
9. **States are announced.** Mark each message as status (polite: saved, N results, loading) or alert
   (errors without a focus move) (4.1.3). Don't make routine messages assertive.
10. **Reflow + zoom.** Check the mockup at 375 px and 320 px and at 200 % zoom; only data tables may
    scroll horizontally, inside their own container, with the first column sticky.
11. **Motion.** Any animation has a reduced-motion variant (`prefers-reduced-motion: reduce`);
    skeleton shimmer is subtle or off under reduce.
12. **Drag has an alternative** (2.5.7), **auth allows paste** (3.3.8), **no re-entry** (3.3.7),
    **help in a consistent place** (3.2.6).
13. **Both themes.** Repeat 1-4 in dark. A pair that passes in light can fail in dark (§3.1:
    `primary-foreground`, `secondary-foreground`).

W3C "Easy Checks" (page title, alt text, headings, contrast, resize, keyboard + visible focus,
forms/labels/errors, moving content, multimedia, basic structure) is the 15-minute version of this
list for reviewing an existing screen.

---

## 5 · Keyboard and screen-reader walkthrough protocol (before sign-off, and on shipped screens)

**Setup.** macOS VoiceOver (Cmd+F5) + Safari, and NVDA + Firefox or Chrome on Windows when available.
Browser zoom 100 % → 200 %. Close the mouse/trackpad from your mind: Tab, Shift+Tab, Enter, Space,
Esc, arrows only.

**Script (per primary task the screen exists for):**
1. Load the page. First Tab: is there a skip link or does focus land in a sensible first place? Is the
   page title (document `<title>` + h1) announced and specific?
2. Tab through the whole page. Record: every stop is visible (2.4.7), in a logical order (2.4.3),
   never hidden (2.4.11), no trap except inside a modal.
3. Do the task end-to-end with the keyboard (create, edit, filter, delete). Every control reachable
   and operable (2.1.1); custom widgets follow their APG keyboard pattern (tabs: arrows; menus:
   arrows + Esc; listbox/combobox: arrows + type-ahead).
4. With VoiceOver: each control announces name + role + state ("Organizações, botão, atual") (4.1.2);
   table headers are read with cells; form errors are read when they appear and are tied to their
   field; status messages ("Salvo", "3 resultados") are announced without focus moving (4.1.3).
5. Open and close every dialog/drawer: focus in, trapped, Esc, returned (APG).
6. Trigger every state: loading (announced? not "Nenhum…"), empty (next action reachable), error
   (cause + fix + retry reachable), success.
7. Zoom to 200 % and resize to 320 px: nothing lost, no 2-D scroll outside data tables.
8. Repeat 2-3 in dark mode for focus visibility and contrast.

**Record** each issue as a finding (§8): SC, severity, location (screen + element, file:line once code
exists), steps, expected, observed, fix shape, owner.

**Severity for a11y findings** uses the Nielsen 0-4 scale (`KB § PATTERNS/design/design-craft-canon.md`
§9.3) with one override: **a Level A/AA failure that blocks a task for a keyboard or screen-reader
user is 4 (catastrophe)** regardless of frequency — the user cannot work around it.

---

## 6 · Composition with the implementation side

| Concern | Owner | Pointer |
|---|---|---|
| Criteria, design-time checks, audits, legal frame, token proposals | product-designer | this doc |
| Semantic HTML, Radix primitives, ARIA wiring, form error wiring, test queries by role | frontend-engineer | `KB § PATTERNS/frontend/frontend-craft-canon.md` §6 · §7 · §10 |
| Seed fixes (focus reset, `Button` ring, bare `Dialog` focus, token values) | frontend-engineer / product-engineer slice, pilots first | canon §4.2 · WE1 |
| Automated a11y gates in CI / test harness | test-engineer (W2-S5) with frontend | §7 |
| Legal exposure (LBI art. 63, consumer complaints) | legal-advisor (W2-S3) | — |

---

## 7 · Tooling targets (implementation owned by frontend-engineer / test-engineer)

Automated tools catch a fraction: axe-core states it finds "on average 57% of WCAG issues
automatically" and reports the rest as "incomplete" for manual review; Playwright's own guide says
automated scans catch "some common" problems and must be paired with manual assessment. So: tools
are the floor, §4-§5 are the method.

| Layer | Target | Catches |
|---|---|---|
| Static (lint) | `eslint-plugin-jsx-a11y` in the **seed** ESLint config — `click-events-have-key-events`, `no-static-element-interactions`, `label-has-associated-control`, `alt-text`, `anchor-is-valid` | the `<div onClick>` class (§3.3), unbound labels |
| Component (vitest) | axe-core on rendered seed organs (`Button`, `Dialog`, `Sidebar`, `OrgPickerModal`, forms) | names, roles, ARIA misuse |
| E2E (Playwright) | `@axe-core/playwright` scan on each active product's smoke route, light + dark | contrast, landmarks, names in the real shell |
| Token gate (keeper candidate) | compute §3.1 pairs from `tokens.css` + brand tokens; ratchet: no new failing pair | contrast regressions, org brand themes with bad pairs (the brand ingestion "deterministic validation (contrast in code)" decided by the owner 2026-10-29 needs exactly this) |

Keeper candidates for the tech-lead's codification queue (s4, not shipped here): `check_token_contrast`
(ratchet on §3.1), `check_global_focus_reset` (forbid `outline-none` on `*:focus-visible` in tokens).

---

## 8 · Audit report template (WCAG-EM shaped)

WCAG-EM's five steps — define scope · explore · select a representative sample · evaluate · report —
and the W3C report template's sections map to this. One report per audited product or flow, stored
beside the mockup (`projects/<slug>/mockups/<screen>/a11y-audit.md`) or in the product's project folder.

```markdown
# A11y audit — <product> · <flow/screens> · <YYYY-MM-DD>
Auditor: product-designer · Standard: WCAG 2.2 AA (≡ ABNT NBR 17225:2025 requisitos A/AA)
## 1 Scope
- Product / routes (status_pagina keys) / roles audited (owner · admin · member) / themes (light, dark)
- Base URL or mockup path · excluded parts and why · browsers + AT (VoiceOver/Safari, NVDA/Chrome)
## 2 Sample
- Screens (list) · the task walked on each · states covered (loading/empty/error/success)
## 3 Method
- §4 design-time checks · §5 walkthrough · tools (axe version, lint) with output attached
## 4 Summary
- Pass/fail per SC group · top 3 risks · strengths worth keeping
## 5 Findings
| id | SC (level) | sev 0-4 | screen · element (file:line) | steps | expected | observed | fix shape (house mechanism) | owner |
## 6 Priorities and plan
- 4s before release · 3s next slice · seed-level fixes (one place, N products) vs product fixes
## 7 Not verified / limits
```

---

## 9 · Anti-patterns

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| Global `outline: none` "because the ring is ugly" (removed 2026-11-05; was `tokens.css:183-187`) | removes 2.4.7 for every element that does not opt back in | a designed ring (§2.3), `:focus-visible` only |
| Clickable `div`/card | no role, no focus, no Enter/Space (2.1.1, 4.1.2) | the card's title is a link/button; secondary controls are siblings, not nested |
| Pastel fill + white label | 2.0-2.7:1 (§3.1) | darker fill or dark label |
| Placeholder as label | disappears on input; low contrast (3.3.2, 1.4.3) | visible label above the field |
| Colour-only status ("the red ones are late") | 1.4.1 | colour + word/icon |
| Identical row buttons ("Editar" × 50) | AT users hear 50 identical names (4.1.2 context) | "Editar — <row name>" via `aria-label`, visible text unchanged |
| Toast as the only error for a form | not tied to a field; vanishes | inline error + summary; toast only for success/background events |
| Drag-only reorder/kanban | 2.5.7 | "Mover para…" menu |
| Modal for long or deep editing | hides context; focus traps big content | non-modal side panel for row editing (NN/g data tables) |
| "Accessibility pass" at the end | retro-fit cost × N products | §4 on the mockup |

---

## Sources

All URLs fetched 2026-11-05 unless marked.

| Title | URL | Supports |
|---|---|---|
| W3C — Web Content Accessibility Guidelines (WCAG) 2.2 | https://www.w3.org/TR/WCAG22/ | §2 SC texts and levels |
| W3C WAI — What's New in WCAG 2.2 | https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ | §2 nine new SC, 4.1.1 removed, 2023-10-05 |
| Understanding SC 1.4.3 Contrast (Minimum) | https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html | §2.1 ratios, large-text sizes, no rounding |
| Understanding SC 1.4.11 Non-text Contrast | https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html | §2.2 · §3.1 input boundary |
| Understanding SC 2.4.7 Focus Visible | https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html | §2 · §3.2 |
| Understanding SC 2.4.13 Focus Appearance | https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html | §2.3 ring spec |
| Understanding SC 2.5.8 Target Size (Minimum) | https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | §2 · §4.3 |
| Understanding SC 4.1.3 Status Messages | https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html | §2 · §4.9 |
| W3C WAI — Easy Checks: A First Review of Web Accessibility | https://www.w3.org/WAI/test-evaluate/preliminary/ | §4 |
| W3C WAI — WCAG-EM 2.0 (Group Note, 2026-07-23) | https://www.w3.org/TR/WCAG-EM/ | §8 five steps |
| W3C WAI — Accessibility evaluation report template | https://www.w3.org/WAI/test-evaluate/report-template/ | §8 sections |
| WAI-ARIA Authoring Practices Guide (APG) | https://www.w3.org/WAI/ARIA/apg/ | §4.6 · §5 |
| APG — Dialog (Modal) pattern | https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ | §3.4 · §4.7 |
| Lei 13.146/2015 (LBI) — art. 63 | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm | §1 |
| ABNT NBR 17225:2025 (PDF hosted by the Câmara dos Deputados) | https://www2.camara.leg.br/a-camara/estruturaadm/gestao-na-camara-dos-deputados/responsabilidade-social-e-ambiental/acessibilidade/pdfs/ABNTNBR17225AcessibilidadeDigitalparaWeb.pdf | §1 (cover, scope note, introduction read via pdftotext) |
| gov.br — Modelo de Acessibilidade (eMAG) | https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/acessibilidade-digital/modelo-de-acessibilidade | §1 eMAG 3.1, WCAG 2.0 basis, Portaria 3/2007 |
| eMAG 3.1 (full text) | https://emag.governoeletronico.gov.br/ | §1 Recomendação 1.5 skip links, accesskey |
| Lei 15.263/2025 (Linguagem Simples) | https://www.planalto.gov.br/ccivil_03/_Ato2023-2026/2025/Lei/L15263.htm | §1 |
| axe-core (Deque) | https://github.com/dequelabs/axe-core | §7 "57%" claim |
| eslint-plugin-jsx-a11y | https://github.com/jsx-eslint/eslint-plugin-jsx-a11y | §7 rules |
| Playwright — Accessibility testing | https://playwright.dev/docs/accessibility-testing | §7 |
| MDN — prefers-reduced-motion | https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion | §4.11 |
| NN/g — Data Tables: Four Major User Tasks | https://www.nngroup.com/articles/data-tables/ | §9 side panel |

**Not verified:** the exact eMAG→ABNT relationship (the gov.br page only links the NBR PDF);
ABNT's own catalogue page for NBR 17225 (not fetched — the Câmara-hosted PDF was read instead).

## Composes with
`KB § PATTERNS/design/design-craft-canon.md` · `KB § PATTERNS/design/mockup-protocol.md` ·
`KB § PATTERNS/frontend/frontend-craft-canon.md` (§7 implementation, frontend-owned) ·
agents `frontend-engineer` · `test-engineer` · `legal-advisor` · skill `noc-organ-consume-check`.
