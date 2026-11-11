# Design craft canon — the product designer's textbook, mapped onto this house

> **What it is.** The general product-design craft (discovery, jobs-to-be-done, information
> architecture, interaction design, visual design on tokens, dark mode, data display, design-system
> governance, pt-BR UX writing, usability evaluation, hand-off) written once and mapped onto NoctusAI's
> seed mechanisms, with in-tree examples. Owned by `product-designer` (`.claude/agents/product-designer.md`).
>
> **Why it exists.** From 2026-11-04 to 2026-11-11 every new screen started as an owner-validated clickable mockup; since 2026-11-11 a mockup is made only when the owner asks and never gates a build ('mockup rule shouldnt block', owner)
> (`KB § PATTERNS/frontend/prototype-on-real-data.md`, memory `feedback-mockup-before-ui`). Nobody owned
> that step: the tech-lead designed by hand and frontend-engineer built in worktrees (audit 2026-11-05,
> `archive/projects/2026-11-05/01-agent-refinement/audits/audit-missing-hires.md` §3). The DESIGN side of a screen — what it is
> for, what is on it, in what words, in which states, and whether people can use it — had no canon.
>
> **How to use it.** §0 is the decision checklist for any design task; open the section your task
> touches. The procedure for producing a mockup is `KB § PATTERNS/design/mockup-protocol.md`; the
> accessibility criteria and audit are `KB § PATTERNS/design/accessibility.md`. **The house mechanism
> wins over the general canon** — when this doc and a house pattern disagree, the house pattern is the
> contract and this doc is the bug (fix on contact). **Design side vs implementation side:** this doc
> decides WHAT the screen is and says; `KB § PATTERNS/frontend/frontend-craft-canon.md`
> (frontend-owned) decides HOW it is built (React, TanStack, Radix, tests). Its §7 (a11y implementation)
> and §12 (copy for the four states) are the implementation half of §9-§11 here — not restated.

**Standard term ↔ house term**

| Standard (Design Council · NN/g · GOV.UK · W3C) | House term / mechanism | Where |
|---|---|---|
| Discover / Define (Double Diamond) | owner interview → discovery brief | memory `feedback-interview-never-assume-specs` · skill `noc-questionnaire` |
| User need / job story | JTBD line in the discovery brief | §2 |
| Prototype (lo-fi / hi-fi) | **clickable mockup** on seed tokens, real data | `KB § PATTERNS/design/mockup-protocol.md` |
| Stakeholder review / usability test | owner-guided walkthrough + sign-off | mockup-protocol §6-§7 |
| Design system | `@noctusai/lib/design-system` (tokens + `ui/*` + organs) | `seed/lib/frontend/src/design-system/` |
| Design tokens | `tokens.css` HSL triplets + `tailwind.config.base.ts` roles | `design-system/tokens.css:16-171` · `tailwind.config.base.ts:31-103` |
| Theming / white-label | org brand identity (`BrandProvider`, `noctus.brand-tokens/v1`) | `design-system/brand-tokens.ts:1-30` · memory `project-org-brand-identity-in-core` |
| Organism / component | **organ** (registered with `.organ.yaml`) | `KB § PATTERNS/architect/products-consume-canonical-organs.md` |
| Template / app shell | `createProductLayout` + `AppShell` + `Sidebar` | `design-system/components/AppShell.tsx` · `Sidebar.tsx` |
| Site map / navigation | `NAV_GROUPS` + `status_pagina` gate | `seed/lib/frontend/src/page-status.ts:75-125` |
| Content design / microcopy | pt-BR UX writing (§9) | frontend canon §12 for state copy |
| Design hand-off / spec | mockup sign-off package → `noc-contract-first` step 0 | §12 · `.claude/skills/noc-contract-first/SKILL.md` |
| Vendor look-alike | forbidden: structure from studies, visuals from the noc pattern | memory `feedback-noc-pattern-not-vendor-look` |

**Facts this doc is written against (2026-11-05, re-check before relying on them):** Tailwind
`^3.4.17-19` with the default type scale and `font-sans` system stack (no `fontSize`/`fontFamily`
extension in `tailwind.config.base.ts`); `lucide-react ^0.462.0` icons; dark mode by `.dark` class
(`tailwind.config.base.ts:20`, `useTheme.ts:43`); active products `agents · core · nosnolimiar ·
social-wiring` (+ `seed`) per `deploy/fleet/active-scope.txt`.

---

## 0 · How to use — the decision checklist for any design task

1. **Is the need understood?** Owner interviewed; every spec point asked, none assumed; JTBD + user
   needs written (§2). Unknown ⇒ ask (skill `noc-questionnaire`), never invent.
2. **Where does it live?** Product, nav group, route, `status_pagina` key, roles that see it, org
   context (§3). In-page tab vs new page decided by the MENUS rules.
3. **What already exists?** Organ catalog checked (skill `noc-organ-consume-check`), sibling screens
   in other products looked at, the data in the real DB located (§8, prototype-on-real-data §2).
4. **What are the flows and states?** Flow diagram + the state matrix (loading · empty-first-use ·
   empty-filtered · error · partial · success · permission) for every region (§4).
5. **Mockup** per `KB § PATTERNS/design/mockup-protocol.md`: seed tokens, light + dark, real data or
   labelled sample, all states clickable, 375 px and desktop.
6. **Words** — pt-BR copy deck: labels, buttons, empty/error/loading/success, numbers and dates (§9).
7. **Accessible by design** — design-time checks in `KB § PATTERNS/design/accessibility.md` §4.
8. **Evaluated** — heuristic review with Nielsen severity + owner-guided walkthrough (§10).
9. **Signed off and handed off** — the hand-off package into `noc-contract-first` (§12).

---

## 1 · Process — the Double Diamond, house-sized

**Principle.** Design alternates two divergent/convergent passes: **Discover** (understand the problem,
spending time with the people affected, rather than assuming it) → **Define** (frame the challenge from
those insights) → **Develop** (generate a range of answers, co-designing) → **Deliver** (test at small
scale, drop what fails, improve what works) (Design Council — The Double Diamond, 2003, popularised by
the Design Council).

**Here.**

| Phase | House step | Output | Gate |
|---|---|---|---|
| Discover | owner interview (+ the real data, + any reverse-engineering study for STRUCTURE only) | interview notes, data facts (row counts, nulls, outliers) | owner answered every open point |
| Define | discovery brief: JTBD, user needs, scope, success signal, constraints | `projects/<slug>/mockups/<screen>/BRIEF.md` (mockup-protocol §2) | owner confirms the brief in his words |
| Develop | lo-fi flow → hi-fi clickable mockup iterations | mockup HTML + notes | owner clicked every state |
| Deliver | sign-off → contract-first build → walkthrough on the shipped screen | sign-off record, hand-off package, post-ship check | `noc-contract-first` step 0 satisfied |

**Anti-patterns.** Jumping to Develop with an unstated job ("make a dashboard"); converging on the
first idea (show 2 layout options when the shape is uncertain); treating Deliver as "code it" — Deliver
includes checking the shipped screen against the signed-off mockup.

---

## 2 · Discovery — interview the owner, write the job, never assume a spec

### 2.1 The owner interview (house rule)

**Rule.** For specs AND design rules, interview — never guess, assume or infer, even where a default
looks obvious; mirror the owner's thinking back and flag where his rules collide with each other or
with live data; once he restates a rule, it replaces any default proposed earlier, and you say which
(memory `feedback-interview-never-assume-specs`, 2026-10-05 and 2026-10-14).

**How.**
- Batch questions (≤ 4 per round; several rounds fine); present observed facts (what the data shows,
  what a studied app does) as **options, never decisions**; long free-text answers in plain chat with a
  compact reply format (`1a 2c 3b`) — a cancelled question form loses what he typed (same memory).
- Use skill `noc-questionnaire` to run the never-assume interview and record answers.
- As an ADVISOR subagent you cannot ask the owner directly: return the question batch to the
  tech-lead, who asks and relays. Never fill a gap with your preference and label it a decision.
- Check rules against live data and show collisions ("this rule makes the 23 portals with no spend
  show 'R$ 0,00' — intended?").

**Interview script (adapt).** Who uses this screen (role, org, frequency, device)? What were they doing
right before, and what do they do right after? What do they do today instead (spreadsheet, WhatsApp,
another app)? What would make them say "this saved me time"? Which numbers do they check first? What
is the worst mistake they could make here? What must never happen (privacy, money, sending to a
client)? Which words do they use for each thing?

### 2.2 Jobs-to-be-done

**Principle.** People "hire" a product to make **progress in a particular circumstance**; the job has
functional, social and emotional dimensions, and the circumstance is part of its definition
(Christensen, Hall, Dillon, Duncan — *Competing Against Luck* / HBR 2016; definition as summarised in
secondary sources, see Sources). Ulwick's Outcome-Driven Innovation adds a solution-free job statement
and a **job map** of eight steps — Define · Locate · Prepare · Confirm · Execute · Monitor · Modify ·
Conclude — useful to find where a screen helps (Strategyn — JTBD).

**Here — the job line in every brief:**
`Quando <circunstância>, quero <progresso>, para <resultado>.` plus *funcional / social / emocional*
in one line each. Example (PortalRoi, from its header quote, `products/social-wiring/frontend/src/pages/PortalRoi.tsx:4-6`):
*Quando fecho o mês de marketing, quero comparar o investimento de cada portal com os leads e vendas
que ele trouxe, para cortar o que não paga.* Functional: compare ROI. Social: justify spend to the
partners. Emotional: stop feeling the money disappears.

Walk the job map for the screen: does it help **Locate** inputs (where does the spend come from?),
**Confirm** (is the data complete — "não informado" visible?), **Monitor** (trend), **Modify** (register
spend inline)? Gaps on the map are features; steps nobody performs are scope to cut.

### 2.3 User needs (GOV.UK format)

`Como <tipo de usuário>, preciso <fazer algo>, para <motivo>.` Written in the user's words; **no
solutions disguised as needs** ("preciso de um lembrete", not "preciso de um e-mail"); needs come from
research, not opinion (a non-user's opinion is a hypothesis to test); include atypical users and people
who support others; keep the list short (GOV.UK Service Manual — Start by learning user needs).

**Our users** (name them in every brief): the **owner** (platform operator, also a business owner);
**org admins/owners** of client orgs; **org members** (role per org — owner in A can be viewer in B,
`OrgPickerModal.tsx:13-15`); **platform staff** acting in a client org (`ActingAsBanner`);
**end customers** on public surfaces (Store, community portal, noctusai.com website, consent pages).

### 2.4 Discovery checklist
- [ ] Every open spec point asked; answers recorded with date; earlier defaults marked superseded.
- [ ] JTBD line + 3 dimensions; job-map steps the screen serves.
- [ ] User needs (≤ 7) per user type, in their words.
- [ ] Real data located: tables, row counts, null rates, the outlier; or "does not exist yet" stated.
- [ ] Success signal (what the owner will check to say it works).
- [ ] Constraints: LGPD category of the data, roles, org scope, devices (mobile?), volume.

---

## 3 · Information architecture and navigation

**Principle.** IA is the structure (content + functionality and how they relate: organisation,
labelling, controlled vocabulary); navigation is the UI "tip of the iceberg" over it (NN/g — IA vs
Navigation). Card sorting **generates** groupings; tree testing **evaluates** a hierarchy without any
visual design (NN/g — Tree Testing).

**Here.**

### 3.1 Products, groups, pages, tabs
- Each product has a `Sidebar` (`seed/lib/frontend/src/design-system/components/Sidebar.tsx`) fed by
  `NAV_GROUPS`, nested up to 4 levels; groups start **closed by construction** — only the active
  route's group auto-expands, the rest is the user's persisted choice (`Sidebar.tsx:51-66`; CLAUDE/frontend.md).
- Grouping rules approved 2026-10-05 (`products/social-wiring/projects/core-studio-build/MENUS.md:3-8`):
  no single-item groups (the item joins its closest group); **in-page tabs stay in-page** (moving a tab
  into the menu changes pages, not menus); small products that already read well are left alone;
  regrouping never renames, adds or removes an item.
- New screen ⇒ decide: new page (own route + nav item) vs in-page tab vs side panel vs dialog. A
  sub-view of one entity is a tab or panel; a different job is a page.

### 3.2 `status_pagina` — the visibility gate the design must declare
- A page is visible only if its route key has a `status_pagina` row: `producao` ⇒ everyone,
  `desenvolvimento` ⇒ dev/owner roles with a "DEV" badge, `desativado`/missing ⇒ hidden
  (`page-status.ts:75-84`, `:117`). An unlisted page is hidden with no error anywhere — PortalRoi's
  header warns about exactly this (`PortalRoi.tsx:20-24`).
- The gate has two halves (RLS returns the row; FE renders it) that must name the same roles
  (`KB § PATTERNS/frontend/status-pagina-dev-visibility.md`).
- ⇒ **Every mockup brief lists, per new page: route, `status_pagina` key, initial status
  (`desenvolvimento` until the owner promotes), nav group and position, roles.** Prod exposure is the
  owner's decision (CLAUDE.md §1).

### 3.3 Org context — the picker and the acting banner
- On every entry into a product, a user with ≥ 2 eligible orgs (and platform staff) picks the org in
  `OrgPickerModal` (`design-system/components/OrgPickerModal.tsx:1-18`): required on entry
  (non-dismissible, with its own "Sair" so nobody is trapped, `:176-179`), dismissible from "Trocar org";
  member view keeps server order, names the role per org and marks the current org "Atual"
  (`:113-127`); staff see client orgs first and "Entrar como NoctusAI (minha org)" last (`:133-150`).
- Owner decision (2026-10-29): switching org/brand is instant with no reload (memory
  `project-org-brand-identity-in-core`). A design that shows org-scoped data must make the current org
  visible (header) and never mix orgs on one screen except in an explicit consolidated view.
- Org brand identity: **one identity per org**, worn by core and every product of the selected org;
  no per-product override; fallback = the NOC standard tokens (same memory). Design screens against the
  NOC standard AND check them with a sample brand (§6.3).

### 3.4 Labels
Use the user's words for things (imóvel, lead, certidão, matrícula, permuta), not table names
(`lead_sources`) or vendor names; one name per concept across products (controlled vocabulary). An
existing menu label is not renamed in a redesign without the owner (MENUS rule).

### 3.5 IA research, house-sized
Card sort with the owner + 1-2 real users when a product's nav is being regrouped; tree-test the
proposed tree as a plain clickable list in the mockup ("onde você clicaria para registrar o
investimento do ZAP?") before any visual design.

**Checklist.** [ ] page vs tab vs panel justified · [ ] route + `status_pagina` key + status + roles ·
[ ] nav group per MENUS rules · [ ] org context visible · [ ] labels in user words, consistent.

---

## 4 · Interaction design and flows

### 4.1 Flows first
Draw the flow (entry → steps → exits, incl. cancel and error exits) as a list or ASCII diagram in the
brief before any screen (the Twin editor spec does this well,
`products/social-wiring/projects/core-studio-build/specs/twin-editor-design.md` §0.1). Each step names
its trigger, the data read/written, and where focus goes.

### 4.2 The state matrix (every data region, every screen)

| State | What the screen shows | Rule |
|---|---|---|
| Loading (first) | skeleton shaped like the content (< 10 s) or a spinner for one module (2-10 s); percent-done + cancel ≥ 10 s | never "Nenhum…" while loading (NN/g — Empty States; Skeleton Screens; Progress Indicators) · two-signal loading (`KB § PATTERNS/frontend/lying-loading-state.md`) |
| Refreshing | previous data stays; small indicator | no layout jump |
| Empty — first use | what will be here + why + the action that fills it | NN/g: status · learning cue · direct pathway |
| Empty — filtered | "Nenhum resultado para estes filtros" + "Limpar filtros" | differs from first use |
| Empty — no permission | what the user can't see and who can grant it | never a fake empty |
| Error | what happened + why (if known) + how to fix + retry; input kept | error before empty (`KB § PATTERNS/frontend/silent-refusal.md`) |
| Partial | the part that loaded + a scoped error for the rest | one failed tile ≠ a failed page |
| Success | the data; writes confirm specifically ("Investimento registrado") | cache writes, no flash (`mutation-cache-writes.md`) |
| Job running | stage + progress; can leave and come back | jobs hand off to polling (`noc-cache-writes`) |
| Unsaved draft | says it is unsaved; guards leaving | `UnsavedChanges` organ |

### 4.3 Response time and feedback
0.1 s feels instant; up to 1 s keeps flow (no indicator needed); past 1 s signal work; past 10 s show
percent-done and a way to cancel, and expect the user to leave (NN/g — Response Times: 3 Limits). The
house budget for server responses is in skill `noc-fast-responses`; the design never hides a slow
response behind a fake-instant UI that later reverts.

### 4.4 Destructive actions
Confirm only serious/irreversible actions, with a specific question and outcome-labelled buttons
("Excluir cliente" / "Manter"), no default on the destructive option; prefer **undo** where possible
(NN/g — Confirmation Dialogs). Seed: `ConfirmProvider` in the shell (`seed/framework/frontend/src/app.tsx:508`).

### 4.5 Forms
Validate on submit (not on blur, not while typing — except fields people commonly get wrong); keep
every answer; show an error summary at the top and an inline message at each field; move focus to the
summary (GOV.UK Design System — Validation; Error message). Server validation always (the contract
mirrors it, frontend canon §6). Long or multi-step: carry values forward (WCAG 3.3.7), show progress.

### 4.6 Editing records in data-heavy screens
In-place editing for narrow tables; a **non-modal side panel** for a row's details/edit (keeps the table
visible); modal only for short, focused tasks; batch actions via row checkboxes + a toolbar
(NN/g — Data Tables). Seed: `SideDrawer`, `card-hub` organs.

### 4.7 Keyboard map
Every screen's brief lists what Tab, Enter, Space, Esc and arrows do and where focus goes after open /
close / save / delete / route change (accessibility.md §4.6).

**Anti-patterns.** Spinner for 30 s with no stage; "Salvo!" toast while the list still shows the old
value; modal-on-modal; a required gate with no way out; a "Cancelar" that discards without warning.

---

## 5 · Visual design on seed tokens

### 5.1 Colour — roles, never hex
Use the **roles** (`background`, `card`, `popover`, `primary`, `secondary`, `muted`, `accent`,
`success`, `warning`, `danger`/`destructive`, `info`, `border`, `input`, `ring`, `sidebar-*`,
`chart-1..8`), each with its `-foreground` pair (`tokens.css:16-100`; `tailwind.config.base.ts:31-98`).
The NOC palette is neutral achromatic with a lead-grey primary and a dark sidebar against a light
content area (`tokens.css:11-12`). A mockup never introduces a hex value; a new role is a seed proposal
(§8).
⚠️ Several pairs fail contrast today (muted text on light surfaces; white on every pastel status fill;
dark-mode primary/secondary labels) — `KB § PATTERNS/design/accessibility.md` §3.1 has the measured
table and the passing values. Until the owner decides, mockups use the passing alternatives
(status = pastel `-light` fill + dark `foreground` text + icon) and flag the token change.

### 5.2 Typography
System font stack (Tailwind `font-sans`: `ui-sans-serif, system-ui, sans-serif, …`) — no web font is
loaded by the seed. Default scale (size/line-height): `text-xs` 12/16 · `text-sm` 14/20 · `text-base`
16/24 · `text-lg` 18/28 · `text-xl` 20/28 · `text-2xl` 24/32 · `text-3xl` 30/36 (Tailwind v3 docs).
House usage: page title `text-2xl font-semibold tracking-tight` (`PortalRoi.tsx:69`); section title
`text-base`/`text-lg font-semibold`; body and table cells `text-sm`; meta/hints `text-xs`
`text-muted-foreground` (⚠️ contrast). Max ~3 sizes per screen; hierarchy by weight and space before
size. Numbers in tables and KPIs use `tabular-nums` (`PortaisTable.tsx:88`). Org brands may set
heading/body/ui families (`brand-tokens.ts:15`, slots `heading · body · ui`) — design must survive a
wider or narrower font.

### 5.3 Space, radius, layout
Tailwind's 4 px spacing scale; house rhythm: page padding `p-6`, vertical rhythm `space-y-6` between
sections, `gap-4` in grids (`PortalRoi.tsx:67`, `:134`). Radius from `--radius` 0.5 rem → `lg`/`md`/`sm`
(`tailwind.config.base.ts:99-103`). Container max `1400px` at `2xl` (`:23-28`). Mobile-first
(CLAUDE/frontend.md): design 375 px first, then 768 and 1440.

### 5.4 Density for CRM/ERP screens
Our heaviest screens are tables and boards (leads, imóveis, certidões, admin lists). Rules:
- **Control heights** are compact by design: `Button` 28 px (`sm`/`icon`) and 32 px (`md`), `Input`
  32 px (`ui/Button.tsx:52-56`, `ui/Input.tsx:26`) — dense but above the 24 px target floor.
- **Tables:** first column = the human identifier (name, not id); columns ordered by importance;
  **numeric columns right-aligned with `tabular-nums`** and right-aligned headers (GOV.UK Design
  System — Table); sticky header and first column when the table outgrows the screen; zebra or hover to
  keep the row; filters visible with an "active filters" indicator; column hide/reorder for wide tables
  (NN/g — Data Tables). Row height ~40 px comfortable, ~32 px compact — pick one per table, don't mix.
- **Missing values** render "—" or "não informado", never 0 (`PortalRoi.tsx:11-14`; frontend canon §8.2).
- **KPIs** as `StatTile`/`StatTileRow` organs with label, value and a short hint/period
  (`PortalRoi.tsx:83-111`).
- Don't trade density for legibility: `text-xs` only for meta; 14 px for data.

### 5.5 Iconography and imagery
`lucide-react` icons, decorative icons `aria-hidden`; meaning never by icon alone. A product's icon is
a REAL registered icon rendered through `ProductIcon` — never its name as text
(`KB § PATTERNS/frontend/product-icon-registry.md`, frontend-owned; transfer requested). Org logos come
in `logo_light`/`logo_dark` variants (`brand-tokens.ts:26-32`) — show the right one per theme.

### 5.6 Motion
Short (≈ 200 ms, the seed collapsible/accordion timings `tailwind.config.base.ts:125-130`), functional
(show where something went), and removed or reduced under `prefers-reduced-motion` (MDN).
Landing-page animation (Motion) enters only via `@noctusai/lib/marketing`, whose provider carries
reduced-motion → `KB § PATTERNS/frontend/marketing-organs-and-motion.md`.

**Checklist.** [ ] roles only, no hex · [ ] ≤ 3 type sizes, `tabular-nums` on numbers · [ ] numbers
right-aligned · [ ] seed control sizes · [ ] "—"/"não informado" for nulls · [ ] 375 / 768 / 1440.

---

## 6 · Dark mode

### 6.1 Mechanism
`.dark` on `<html>` swaps every token (`tokens.css:103-171`; `tailwind.config.base.ts:20`), toggled
by `useTheme` (`useTheme.ts:42-45`), optionally persisted to the user profile (`onPersist`). The
sidebar is dark in both themes (`--sidebar-background` 10 % / 6 %).

### 6.2 Design rules
- Every mockup ships both themes and every state in both (mockup-protocol §4). A pair can pass in
  light and fail in dark (`primary-foreground` 6.07 → 4.24; accessibility §3.1).
- Elevation in dark comes from lighter surfaces (`card` 11 % over `background` 8 %), not shadows;
  status fills use the darker `-light` variants (14 % L) in dark.
- Charts use the dark chart palette (`tokens.css:160-170`) via `useChartTheme`, never hardcoded.
- Images, logos and illustrations need dark variants (logo_dark) or must work on both.

### 6.3 Light default, dark offered
Evidence summary (NN/g literature review): light mode (positive polarity) generally gives better
reading performance for people with normal vision, more so at small sizes; some low-vision users read
better in dark; users rarely change defaults ⇒ don't default to dark, do offer it, keep it consistent
across screens and follow the OS preference where an API exists (NN/g — Dark Mode vs. Light Mode).
House state: `useTheme` defaults to light and **ignores `prefers-color-scheme`** (`useTheme.ts:29-32`).
Following the OS preference on first visit (before any saved choice) is a seed proposal for the owner,
not a mockup decision.

### 6.4 Brand themes
Org identities include a **derived dark mode** (owner 2026-10-29); the brand ingestion validates
contrast in code. Design reviews of a brand check the same pairs as §3.1 of accessibility.md in both
derived themes.

---

## 7 · Data display and visualisation (pointer)

- **Use the seed chart organs** — `StatTile`, `StatTileRow`, `ChartCard`, `LineChart`, `AreaChart`,
  `BarChart`, `DonutChart`, `Heatmap`, `FilterBar`, colours via `useChartTheme`
  (`seed/lib/frontend/src/design-system/charts/`, each with an `.organ.yaml`). A new chart type is an
  organ proposal (§8).
- **Pick the form from the question:** trend over time ⇒ line/area; compare categories ⇒ bars
  (sorted); part of a whole with ≤ 5 parts ⇒ donut, else bars; distribution over two dimensions ⇒
  heatmap; a single number that matters ⇒ a stat tile with its comparison (period, target). A table is
  often the honest answer for few rows with many attributes (PortalRoi chose table + tiles over a
  chart on day one, `PortalRoi.tsx:13-14`).
- **Honest values:** missing ≠ zero; label the period; start bar axes at zero; no dual axes; direct
  labels over legends where possible; colour is categorical (`chart-1..8`), never the only encoding
  (accessibility §4.2).
- When the session has the `dataviz` skill (harness skill, not in-repo), the tech-lead loads it for
  chart-heavy mockups; its palette guidance yields to the seed `chart-*` tokens.
- Gamification visuals stay subtle, with a ⓘ explaining the formula (CLAUDE/frontend.md; `KB § 07-GAMIFICATION.md`).

---

## 8 · Design-system governance

**Principle.** Atomic Design's five levels — atoms, molecules, organisms, templates, pages — describe
how an interface is assembled; pages are templates filled with realistic content and are where the
system is tested (Brad Frost — Atomic Design ch. 2).

**Here (house vocabulary — frontend canon §4.1 maps it in code):** atoms/molecules = `ui/*` on
`tokens.css`; organisms = **organs** with `.organ.yaml`; templates = `createProductLayout` + `AppShell`
+ `Sidebar`; pages = the product's `pages/` — and **the mockup on real data is the "page" test**.

**Rules.**
1. **Consume before you draw.** Skill `noc-organ-consume-check` before designing any component; a
   mockup that redraws an existing organ differently is a fork in disguise
   (`KB § PATTERNS/architect/products-consume-canonical-organs.md`). Extend via a **declared named
   seam** (slot, prop, adapter) — the mockup notes name it.
2. **Promote to the seed** when another product will need it (build shared from day one); N=2 triage,
   N≥3 must formalise (CLAUDE.md §1 DRY). The designer flags organ candidates in the hand-off; the
   architect/frontend decide the seam.
3. **No vendor look-alikes.** Reverse-engineered apps give structure, flows and data; colours, shapes,
   motion and copy follow the noc pattern; state it at the top of any design derived from a study
   (memory `feedback-noc-pattern-not-vendor-look`; Twin editor 2026-11-04). Material 3 and Apple HIG are
   **references for reasoning**, never a visual source.
4. **Tokens are the API.** A new colour/size/radius is a token proposal to the seed, never a one-off
   value. The W3C Design Tokens Community Group format (2025.10, "Final Community Group Report":
   tokens are objects with `$value` and an optional/inherited `$type`, groups, `{group.token}` aliases,
   composite types like `typography` and `shadow`) is the exchange format to target if tokens are ever
   exported to a design tool or a brand pipeline; today `tokens.css` + `noctus.brand-tokens/v1`
   (HSL triplets, radius, font slots — `brand-tokens.ts:10-25`) are the source of truth.
5. **One identity per org**, decided in core, worn everywhere; brand work targets core + a seed organ,
   never a product (memory `project-org-brand-identity-in-core`). The owner wants to co-design the
   brand step of signup — don't finalise that UX alone (same memory).
6. **Pilots first** for any seed visual change (CLAUDE.md §1): mock it on 3 pilot screens before fan-out.

---

## 9 · UX writing in pt-BR

### 9.1 Voice
Plain, direct, specific, calm. Address the user as "você"; the system takes responsibility for its
failures ("Não conseguimos…", not "Você errou"). Brazilian plain-language technique list (Lei
15.263/2025 art. 5 — binding on public administration only, used here as the best pt-BR checklist):
direct order and short sentences; one idea per paragraph; common words; explain or replace jargon;
avoid uncommon foreign words; full name before an acronym; lists and tables where they help; **most
important information first**; active voice; verbs instead of nouns; cut redundancy; avoid vague
words; language accessible to people with disabilities; test that the audience understands. GOV.UK
adds measurable limits: split sentences over 25 words, ≤ 5 sentences per paragraph, short familiar
words, explain a specialist term the first time (GOV.UK — Use clear language). Front-load titles and
labels with the keyword (NN/g — Microcontent).

### 9.2 Microcopy rules
- **Buttons** = verb + object, outcome-named: "Salvar cliente", "Registrar investimento", "Excluir
  conexão" — not "OK"/"Confirmar"/"Sim". Destructive confirmations: "Excluir" / "Manter".
- **Labels** = nouns the user uses; sentence case for new labels ("Valor das vendas"); existing menu
  labels are not renamed without the owner (MENUS rule).
- **Hints** under the label say format/constraint once ("Somente números, com DDD").
- **Errors** (field): say what to do — "Informe o CPF do comprador", "O CEP tem 8 números" — reuse the
  label's words; no "inválido"/"inválida" alone, no blame ("você esqueceu"), no humour, no raw server
  text or codes (codes only in a diagnostic detail) (GOV.UK — Error message; NN/g — Error-Message
  Guidelines). Page/region errors: what happened + why if known + what to do + retry (frontend canon §12).
- **Empty states**: what will be here + why it is empty + the action ("Nenhuma origem de lead
  configurada ainda. Cadastre suas origens para acompanhar o ROI." + button) — first-use ≠ filtered ≠
  no-permission (NN/g — Empty States).
- **Loading**: never claims emptiness; long jobs say the stage ("Gerando 3 de 10 vídeos…").
- **Success**: specific and short ("Cliente cadastrado"); background events are notifications, not
  toasts (`KB § PATTERNS/frontend/notification-classes.md`).
- **Sample content** in a mockup is labelled "AMOSTRA" (prototype-on-real-data §0).

### 9.3 Numbers, money, dates, people
| Value | Format | Note |
|---|---|---|
| Money | `R$ 1.234,56` (`Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'})`) | null ⇒ "—"/"não informado", never "R$ 0,00" — the seed `formatCurrency(null)` returns "R$ 0,00" today (`seed/lib/frontend/src/utils.ts:26-31`, PROJECT §6 follow-up 4) |
| Integers | `1.234` | `tabular-nums` |
| Percent | `12,5%` (Intl `style:'percent'`) | say the base ("de conversão") |
| Multiples | `3,2×` ROI | define in a ⓘ |
| Date | `05/11/2026`; relative for recent events ("há 5 min") with the absolute in a tooltip | timestamps in the org's zone (frontend canon §8.3) |
| CPF / CNPJ / phone | masked display per LGPD context; phone `(11) 91234-5678` | frontend canon §8.4 |
| Plural | "1 lead" / "2 leads" — never "lead(s)" | `Intl.PluralRules` |

### 9.4 Domain glossary (keep consistent)
organização (org) · marca · produto · imóvel · lead · origem/portal · cliente · contato · certidão ·
matrícula · permuta · contrato · agente. Write the glossary for a new domain into the brief.

---

## 10 · Usability evaluation

### 10.1 Heuristic evaluation
Nielsen's 10 heuristics (1994, reviewed 2024): visibility of system status · match between system and
the real world · user control and freedom · consistency and standards · error prevention · recognition
rather than recall · flexibility and efficiency of use · aesthetic and minimalist design · help users
recognise, diagnose and recover from errors · help and documentation (NN/g). Frontend canon §12 maps
them onto the four states.

**Method (NN/g — How to Conduct a Heuristic Evaluation), house-sized:** scope one task/flow; **3-5
independent evaluators** ideally — here the designer + one of `frontend-engineer`/`compliance-reviewer`
(+ the owner in the walkthrough); each passes once to learn and once to note violations with a
heuristic and a fix; then consolidate (group duplicates, agree severity, short- vs long-term fix).
A single evaluator misses problems — say so when you are the only one.

### 10.2 Owner-guided walkthroughs (the 5-user test, adapted)
Nielsen: ~5 users find most problems in one study, and several small iterative rounds beat one large
one (NN/g — Why You Only Need to Test with 5 Users). Thinking aloud: representative users,
representative tasks, then **stay quiet** — prompts bias behaviour (NN/g — Thinking Aloud).
Adapted here: round 1 = the owner clicks the mockup doing 2-4 real tasks while thinking aloud
(the tech-lead relays the session); round 2+ = the owner plus 1-4 real users of the product (an org's
staff) on the revised mockup or the shipped screen. Never lead ("clique no botão azul"); ask "o que
você faria agora?". Record task, success, time, quotes, problems.

### 10.3 Severity
Nielsen's 0-4: **0** not a problem · **1** cosmetic, fix if time · **2** minor, low priority · **3**
major, high priority · **4** catastrophe, fix before release; rated on **frequency, impact,
persistence** and market impact (NN/g — Severity Ratings). House override: an accessibility failure
that blocks a task for keyboard/AT users is **4** (accessibility.md §5).

### 10.4 Findings format
`id · heuristic/SC · sev 0-4 · screen · element (file:line once code exists) · evidence (quote, step) ·
fix shape (house mechanism) · owner`. 4s block sign-off; 3s are fixed in the next mockup iteration.

---

## 11 · Accessibility (pointer)

WCAG 2.2 AA is the floor in light and dark; Brazilian frame LBI art. 63 + ABNT NBR 17225:2025 (built on
WCAG 2.2). Design-time checks, measured gaps (global focus reset, failing token pairs, mouse-only
cards, the bare seed `Dialog`), walkthrough protocol and audit template:
`KB § PATTERNS/design/accessibility.md`. Implementation: frontend canon §7.

---

## 12 · Hand-off to frontend — into `noc-contract-first`

`noc-contract-first` step 0 says the owner-validated mockup comes first and "its controls and states
become the FE contract, and its data reads become the endpoints" (`.claude/skills/noc-contract-first/SKILL.md`).
The **hand-off package** (one folder beside the mockup, mockup-protocol §8):

1. Sign-off record (owner phrase + date, mockup version/link).
2. Screen inventory + flow diagram + keyboard map.
3. **State matrix** per region (§4.2) — becomes the FE acceptance list.
4. **Data reads** — each query the mockup ran (or the sample it stands in for), named after the future
   endpoint; null/empty semantics stated ("`investimento` null ⇒ 'não informado'"). These seed the
   contract skeleton (step 1); the architect/tech-lead authors the contract, not the designer.
5. **Writes and their outcomes** — what each action changes and what the screen shows after (feeds the
   stateful legs of step 2: side-effects, error taxonomy → user-facing message).
6. **Copy deck** (pt-BR, every string incl. errors/empties) and the domain glossary.
7. **Organ map** — organs consumed (with seams) and organ candidates for the seed.
8. Nav placement + `status_pagina` key + roles (§3.2).
9. Accessibility annotations + the audit (accessibility.md §8).
10. Open questions — anything not decided by the owner, explicitly.

After ship, the designer compares the shipped screen to the signed-off mockup (Deliver) and files
deltas as findings; the mockup is then retired or linked from the docs, never a second source of truth
(prototype-on-real-data §2.3).

---

## 13 · Anti-patterns

| Anti-pattern | Why it hurts | Instead |
|---|---|---|
| Designing from an assumed spec | the owner's rules contradict it later; rework | interview (§2.1) |
| Mock numbers where real data exists | hides nulls, outliers, empties that decide the layout | real data via the connector (mockup-protocol §3) |
| Copying a vendor's look from a study | brand dilution; legal and owner rule | noc pattern (§8.3) |
| A new component that redraws an organ | fork; drift | consume + named seam (§8.1) |
| Hex values / ad-hoc colours | breaks dark mode and org brands | roles (§5.1) |
| Only the happy path designed | empty/error/loading invented during build, inconsistently | state matrix (§4.2) |
| Light-only mockup | dark failures found in prod | both themes (§6.2) |
| Dashboard with a chart for every number | noise; slow | tiles + table first, chart where a trend matters (§7) |
| "R$ 0,00" for unknown | lies | "—"/"não informado" (§9.3) |
| Clickable cards with nested toggles | keyboard-inaccessible; mis-clicks | title link + sibling controls (WE1) |
| Generic error/empty copy | no recovery | 3-part copy (§9.2) |
| New nav item without a `status_pagina` row | silently hidden page | §3.2 |

---

## 14 · Checklists

**Discovery** — §2.4.

**Mockup review (before showing the owner):**
- [ ] Brief matches the mockup (job, users, scope); noc pattern; no vendor visuals.
- [ ] Real data or labelled "AMOSTRA"; no PII in committed files.
- [ ] Every region × every state clickable; light + dark; 375 px + desktop.
- [ ] Organs consumed; candidates named; tokens only.
- [ ] Copy deck pt-BR complete; numbers/dates formatted; nulls honest.
- [ ] accessibility.md §4 run; failing pairs flagged.

**Sign-off:** owner walked the tasks; 4-severity findings fixed; open questions answered or listed;
sign-off phrase recorded (mockup-protocol §7).

**Hand-off:** the 10 items of §12.

---

## Worked examples

### WE1 — Core dashboard: product launcher cards (keyboard + nested controls)

**Evidence.** `products/core/frontend/src/pages/Dashboard.tsx:250-261`: each product is a `<div>` with
`cursor-pointer` and `onClick={() => { if (!inactive) launchProduct(product); }}` — no role, no
`tabIndex`, no key handler. Inside it, admins get `DeployScopeToggle` + `StatusToggle` wrapped in a
`div` that stops propagation (`:272-288`); inactive products render dimmed `opacity-50` with a dashed
border (`:253-255`); non-admins see a "dev" pill whose meaning lives in a `title` tooltip (`:291-297`).

**Findings.**
| # | Issue | Heuristic / SC | Sev |
|---|---|---|---|
| 1 | A keyboard user cannot open any product from the core home | WCAG 2.1.1, 4.1.2 | 4 |
| 2 | Interactive toggles nested inside a clickable card: two targets in one; a mis-click launches the product | H5 error prevention | 3 |
| 3 | "Inactive" conveyed by opacity + dashed border; `opacity-50` text drops below 4.5:1 | 1.4.1, 1.4.3 | 2 |
| 4 | "dev" pill explained only by a hover `title` (no keyboard/touch access) | H6, 1.3.1 | 2 |

**Redesign (shape, for the mockup).** The card is a container; its **title is the link** ("Abrir
Social Wiring") covering the card visually via a pseudo-element, so the whole card stays clickable for
the mouse and is one Tab stop for the keyboard; admin toggles sit in a footer row **outside** the link,
each a labelled switch ("Ativo", "Publicado em produção"); inactive state = a text badge "Inativo" +
the disabled link replaced by a reason ("Produto inativo — reative para abrir"); the "dev" pill reads
"Em desenvolvimento" with the explanation as visible helper text on focus/hover and in the accessible
name. States in the mockup: loading (card skeletons), no products licensed (empty with "Fale com o
administrador da sua organização"), error (retry).

### WE2 — The org picker: a required gate done mostly right

**Evidence.** `seed/lib/frontend/src/design-system/components/OrgPickerModal.tsx`: four states
(loading `:85-90`, error with retry `:91-97`, empty `:98-103`, list `:104-151`); member rows name org +
role and mark "Atual" with `aria-current` (`:113-127`); required mode is non-dismissible but carries
"Sair" so nobody is trapped (`:176-179`, rationale `:9-11`); it renders in the bare seed `Dialog`
(`:153`).

**What to keep.** Explicit states; role-per-org; the escape hatch on a required gate (H3 user control);
server order with last-active first (recognition over recall).

**Findings.**
| # | Issue | Heuristic / SC | Sev |
|---|---|---|---|
| 1 | Bare `Dialog`: focus not moved in, not trapped, not returned — on the first screen every multi-org user sees | 2.4.3, APG | 3 |
| 2 | No visible focus on the org rows (global reset, plain `<button>` without ring) | 2.4.7 | 4 (keyboard users cannot see where they are) |
| 3 | Error text `text-destructive` on light background = 2.67:1 (`:94`, `:173`) | 1.4.3 | 3 |
| 4 | Choose error shows `err.message` raw (`:208`) | H9; copy §9.2 | 2 |
| 5 | Loading line not a status message (`:87-88`) | 4.1.3 | 1 |
| 6 | Empty state has no next step beyond "Sair" ("Nenhuma organização com licença ativa…") | NN/g empty states | 2 |
| 7 | Close control is a literal "x" character with `aria-label` (`:160`) — small target, inconsistent icon | 2.5.8, H4 | 1 |

**Mockup asks.** Radix dialog behaviour (initial focus on the first org; Esc only when dismissible);
the §2.3 focus ring; error copy "Não foi possível entrar em <org>. Tente de novo ou fale com o
suporte." with the server reason class in a detail; empty state "Sua conta não tem acesso a <produto>
em nenhuma organização. Peça acesso ao administrador da sua organização." + "Sair"; lucide `X` icon at
28 px. Seed-level change ⇒ one fix, every product.

### WE3 — ROI por Portal: honest data on a dense screen

**Evidence.** `products/social-wiring/frontend/src/pages/PortalRoi.tsx` and
`components/portal-roi/PortaisTable.tsx`. The header documents the design decision: on day one 23 of 24
portals have leads but zero recorded spend, so rendering "não informado", never "R$ 0,00", **is the
feature**, and the day-one action is "Registrar investimento" per row, not a chart (`PortalRoi.tsx:11-19`).
States in the right order: error → loading → empty → success (`:75-81`); "empty" means no lead sources
at all, NOT "sources without spend" (`:16-19`, `:60`); KPI tiles with hints (`:83-111`); `tabular-nums`
cells (`PortaisTable.tsx:88-108`).

**What to keep.** Honest nulls; the empty/zero distinction decided from real data; tiles + table
before charts; job-first copy in the subtitle (`:70-72`).

**Findings.**
| # | Issue | Heuristic / SC | Sev |
|---|---|---|---|
| 1 | Numeric columns and their headers are left-aligned (`PortaisTable.tsx:65-76`, `:88-108`) — magnitudes hard to compare | H8; GOV.UK table | 2 |
| 2 | Action column header is empty (`:76`) | 1.3.1 | 2 |
| 3 | "Registrar investimento" repeated on ~23 rows with the same accessible name (`:114-121`) | 4.1.2 / 2.4.6 | 2 |
| 4 | Empty state names "Configuração de Leads" but offers no link/button to it (`PortalRoi.tsx:164-167`) | NN/g empty: direct pathway | 2 |
| 5 | Error state says nothing about why or what else to do (`:144-155`) | H9 | 1 |
| 6 | `text-muted-foreground` subtitle and hints at 3.72-3.98:1 | 1.4.3 | 2 (token-level, fleet-wide) |

**Mockup asks.** Right-aligned numeric columns and headers; "Ações" header (visually hidden if
desired); row button accessible name "Registrar investimento — <portal>"; empty state button
"Configurar origens" linking to the leads configuration; error copy with retry + "Se persistir, avise o
suporte"; tiles keep "não informado". These are design deltas — the frontend implements them through
the contract and the organs.

---

## Sources

All URLs fetched 2026-11-05 unless marked.

| Title | URL | Supports |
|---|---|---|
| Design Council — The Double Diamond | https://www.designcouncil.org.uk/our-resources/the-double-diamond/ | §1 |
| GOV.UK Service Manual — Start by learning user needs | https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs | §2.3 |
| HBR — Know Your Customers' "Jobs to Be Done" (Christensen, Hall, Dillon, Duncan, Sept 2016) | https://hbr.org/2016/09/know-your-customers-jobs-to-be-done | §2.2 authorship (page body paywalled; definition not readable there) |
| Strategyn — Jobs-to-be-Done (Ulwick, ODI, job map) | https://strategyn.com/jobs-to-be-done/ | §2.2 job map, solution-free job statement |
| NN/g — IA vs. Navigation | https://www.nngroup.com/articles/ia-vs-navigation/ | §3 |
| NN/g — Tree Testing | https://www.nngroup.com/articles/tree-testing/ | §3 · §3.5 |
| NN/g — Designing Empty States | https://www.nngroup.com/articles/empty-state-interface-design/ | §4.2 · §9.2 |
| NN/g — Skeleton Screens 101 | https://www.nngroup.com/articles/skeleton-screens/ | §4.2 |
| NN/g — Progress Indicators | https://www.nngroup.com/articles/progress-indicators/ | §4.2 |
| NN/g — Response Times: The 3 Important Limits | https://www.nngroup.com/articles/response-times-3-important-limits/ | §4.3 |
| NN/g — Confirmation Dialogs | https://www.nngroup.com/articles/confirmation-dialog/ | §4.4 |
| NN/g — Data Tables: Four Major User Tasks | https://www.nngroup.com/articles/data-tables/ | §4.6 · §5.4 |
| GOV.UK Design System — Validation | https://design-system.service.gov.uk/patterns/validation/ | §4.5 |
| GOV.UK Design System — Error message | https://design-system.service.gov.uk/components/error-message/ | §4.5 · §9.2 |
| GOV.UK Design System — Table (numeric alignment) | https://design-system.service.gov.uk/components/table/ | §5.4 |
| GOV.UK — Use clear language | https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/ | §9.1 |
| Tailwind CSS v3 — Font size | https://v3.tailwindcss.com/docs/font-size | §5.2 |
| Tailwind CSS v3 — Font family | https://v3.tailwindcss.com/docs/font-family | §5.2 |
| MDN — prefers-color-scheme | https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme | §6.3 |
| MDN — prefers-reduced-motion | https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion | §5.6 |
| MDN — Intl.NumberFormat | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat | §9.3 |
| NN/g — Dark Mode vs. Light Mode | https://www.nngroup.com/articles/dark-mode/ | §6.3 |
| Atomic Design, ch. 2 (Brad Frost) | https://atomicdesign.bradfrost.com/chapter-2/ | §8 |
| Design Tokens Format Module 2025.10 (DTCG) | https://www.designtokens.org/tr/2025.10/format/ | §8.4 |
| Lei 15.263/2025 — Política Nacional de Linguagem Simples, art. 5 | https://www.planalto.gov.br/ccivil_03/_Ato2023-2026/2025/Lei/L15263.htm | §9.1 |
| NN/g — Microcontent: headlines, titles, subject lines | https://www.nngroup.com/articles/microcontent-how-to-write-headlines-page-titles-and-subject-lines/ | §9.1 |
| NN/g — Error-Message Guidelines | https://www.nngroup.com/articles/error-message-guidelines/ | §9.2 |
| NN/g — 10 Usability Heuristics (1994, reviewed 2024) | https://www.nngroup.com/articles/ten-usability-heuristics/ | §10.1 |
| NN/g — How to Conduct a Heuristic Evaluation | https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/ | §10.1 |
| NN/g — Why You Only Need to Test with 5 Users | https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/ | §10.2 |
| NN/g — Thinking Aloud: The #1 Usability Tool | https://www.nngroup.com/articles/thinking-aloud-the-1-usability-tool/ | §10.2 |
| NN/g — Severity Ratings for Usability Problems | https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/ | §10.3 |
| Steve Krug — Don't Make Me Think, Revisited (3rd ed., 2014) | https://sensible.com/dont-make-me-think/ | further reading only — the page lists no principles to cite |

**Not verified (reference only — do not quote as authority):**
- The JTBD **definition wording** ("progress … in a particular circumstance"; functional/social/emotional)
  comes from secondary summaries of *Competing Against Luck* (2016); the Christensen Institute pages
  returned HTTP 403 and HBR's body is paywalled. Treat §2.2's definition as attributed, not quoted.
- Material Design 3 (https://m3.material.io/) and Apple HIG (https://developer.apple.com/design/human-interface-guidelines/)
  are JavaScript-rendered; WebFetch returned only titles. Named as references for reasoning only; no
  claim in this doc rests on them.
- GOV.UK "reading age 9" — appears only in mirrors of an older GOV.UK page; the live "Use clear
  language" page does not state it. Not used.

## Composes with
`KB § PATTERNS/design/mockup-protocol.md` · `KB § PATTERNS/design/accessibility.md` ·
`KB § PATTERNS/frontend/frontend-craft-canon.md` · `KB § PATTERNS/frontend/prototype-on-real-data.md` ·
`KB § PATTERNS/frontend/status-pagina-dev-visibility.md` · `KB § PATTERNS/frontend/product-icon-registry.md` ·
`KB § PATTERNS/architect/products-consume-canonical-organs.md` · skills `noc-contract-first` ·
`noc-organ-consume-check` · `noc-questionnaire` · `noc-reverse-engineer` (structure only) ·
agents `frontend-engineer` · `architect` · `compliance-reviewer`.
