# Mockup protocol — the procedure for drawing a mockup when the owner asks

> **What it is.** The step-by-step procedure that turns an owner's request for a mockup into a
> clickable HTML mockup the owner refines from, and a hand-off package the frontend applies. Owned by
> `product-designer` (`.claude/agents/product-designer.md`).
>
> **Rule change 2026-11-11 — mockups never gate a build.** owner 2026-11-11: "mockup rule shouldnt block. let's flexibilize the rule. mockups are brought for validation only when i ask for it. build should start right away, i'll use the mockup to refine, you change what i ask in-flight or later and redeploy if the frontend has already been created".
> A mockup is made ONLY when the owner asks for one; the build starts right away. This supersedes the
> 2026-11-04 mockup-first rule (owner 2026-11-04 ×2), whose procedure survives below for when a mockup is requested.
>
> **Why it exists.** The house look is the noc pattern, on real data where it exists (`CLAUDE/frontend.md` rule 1;
> `KB § PATTERNS/frontend/prototype-on-real-data.md`; memory `feedback-mockup-before-ui`). The RULE
> lives in prototype-on-real-data; the PROCEDURE did not exist, so each mockup was invented ad hoc by
> whoever drew it. This doc is that procedure.
>
> **How to use it.** When the owner asks for a mockup, run §1-§8 in order. Craft depth (what to put on the screen,
> copy, states, evaluation) is in `KB § PATTERNS/design/design-craft-canon.md`; accessibility checks in
> `KB § PATTERNS/design/accessibility.md`. **The house mechanism wins:** prototype-on-real-data
> (frontend-owned today; transfer to product-designer requested) is the contract this procedure
> implements; if they disagree, fix this doc.

**Standard term ↔ house term**

| Standard (NN/g · design practice) | House term | Where |
|---|---|---|
| Low-fidelity prototype / wireframe | **L1 mockup** (structure, greys, clickable) | §4 |
| High-fidelity prototype | **L2 mockup** — seed tokens, real data, all states (sign-off fidelity) | §4 · §5 |
| Prototype data | real DB via the owner's connector · labelled "AMOSTRA" only if the data does not exist yet | §3 |
| Stakeholder review / usability session | owner-guided walkthrough | §6 · canon §10.2 |
| Design sign-off | recorded owner phrase + mockup version | §7 |
| Design spec / hand-off | hand-off package → `noc-contract-first` step 0 | §8 · canon §12 |
| Published prototype | private claude.ai Artifact, published by the tech-lead | §5.4 |

---

## 1 · When it runs: on the owner's ask

**Only when the owner asks for a mockup** (or asks `product-designer` for a redesign, IA, copy or
accessibility review, or to refine a screen already built). A mockup NEVER gates a build: UI work starts
right away on the noc pattern (seed tokens, app shell, real data where it exists), contract-first for
BE↔FE. The owner uses the mockup, or the built screen, to refine; what they ask is applied in-flight or
as a follow-up, with a redeploy if the frontend already shipped. "No mockup" is never a reason to stop a
build or to escalate a decision (owner 2026-11-11). Accessibility checks (§5, `accessibility.md` §4)
run on the mockup when one exists, otherwise on the built screen.

## 2 · Inputs (gather before drawing)

1. **The owner's request in his words**, verbatim, with the date.
2. **Discovery answers** — the interview (canon §2.1); every open point asked, none assumed. As a
   subagent, return the question batch to the tech-lead; do not proceed on guesses.
3. **Discovery brief** (`BRIEF.md`, template below).
4. **The data**: tables/views, row counts, null rates, the outlier, the empty case — or "does not exist
   yet" (§3).
5. **Organ catalog** result (skill `noc-organ-consume-check`) and 1-2 sibling screens in our products
   that solve something similar (consistency, canon §8).
6. **Placement**: product, nav group, route, `status_pagina` key, roles (canon §3.2).
7. **References**: a reverse-engineering study, screenshots — for **structure and data only**, never
   visuals (memory `feedback-noc-pattern-not-vendor-look`). Images the owner pasted that a decision
   rests on are saved beside the mockup (memory `feedback_images_in_transcript_are_not_a_record`).

```markdown
# <Screen> — discovery brief (<YYYY-MM-DD>)
Request (owner, verbatim): "…"
Job: Quando <circunstância>, quero <progresso>, para <resultado>. Funcional · Social · Emocional: …
Users: <role(s), org scope, device, frequency>
User needs (≤7): Como <usuário>, preciso <…>, para <…>.
Success signal: <what the owner will check>
Scope: in … / out …
Placement: product · nav group · route · status_pagina key (initial: desenvolvimento) · roles
Data: <tables/views, counts, nulls, outliers> | "não existe ainda" → AMOSTRA
LGPD: <data categories on screen; masking>
Organs to consume: … · candidates: …
Open questions (for the owner): 1. … 2. …
Visual language: noc pattern (seed tokens, app shell). Never <vendor>'s look.
```

---

## 3 · Data — real where it exists, labelled sample where it doesn't

- **Real data is the default** for any data that exists (prototype-on-real-data §0, §2): the numbers,
  nulls and outliers decide the layout (PortalRoi's "23 of 24 portals have no spend" decided its whole
  design, `products/social-wiring/frontend/src/pages/PortalRoi.tsx:11-19`).
- **Route.** The designer subagent cannot reach the owner's claude.ai Supabase connector. It writes the
  read-only queries (`queries.sql`, one named query per data region, each the seed of a future
  endpoint), and the tech-lead either (a) publishes the mockup with the connector capability so the page
  reads live, read-only (prototype-on-real-data §2 step 2), or (b) runs the queries and hands the
  results back for the designer to embed with a provenance line ("dados reais, consulta X, 2026-11-05").
  The noctusai MCP has no read path to the owner's prod data for a designer — do not improvise one.
- **Sample content only when the data does not exist yet** (a feature that has never run), labelled
  **"AMOSTRA"** visibly on the mockup and in the notes, swapped for real data as soon as it exists.
  Never sample for data that exists but was not wired (prototype-on-real-data §3).
- **No data reachable for data that exists** ⇒ say so on the page and to the owner; never fill in
  numbers.
- **LGPD.** Prefer aggregates; show personal data only where the screen's job needs it, masked as the
  product would mask it. **Real personal data never goes into a committed file** — a real-data mockup
  lives in the session scratchpad / the private artifact only; the copy committed under `projects/`
  uses aggregates or AMOSTRA rows. Read-only, always.

---

## 4 · Fidelity levels

Fidelity varies on three axes — interactivity, visuals, content (NN/g — UX Prototypes: Low vs. High
Fidelity). Low fidelity suits early exploration and quick changes; high fidelity suits testing
workflows, specific components, visual hierarchy and realistic behaviour.

| Level | What | When | Sign-off? |
|---|---|---|---|
| **L0 — flow** | text/ASCII flow + screen list + state matrix in the brief | always, first | no |
| **L1 — structure** | clickable greyscale boxes on the app shell; real labels; nav as a clickable tree (tree test) | the shape is uncertain; 2 layout options to compare | no |
| **L2 — sign-off** | seed tokens light + dark, real data / AMOSTRA, every state, final pt-BR copy, 375 px + desktop, keyboard-operable markup | always before code | **yes** |

Skip L1 when the screen extends a known pattern (a new list like the existing lists). Never skip L2.

---

## 5 · HTML mockup rules (L2)

### 5.1 Shape
- **One self-contained `index.html`** per screen (or per flow), plus `queries.sql`, `NOTES.md`,
  `BRIEF.md`, `HANDOFF.md`, `a11y-audit.md`, `assets/` (§8). No build step.
- **Seed tokens, copied verbatim** from `seed/lib/frontend/src/design-system/tokens.css` (light block
  `:16-100`, dark block `:103-171`) as `--name: H S% L%` triplets, used as `hsl(var(--name))` — the same
  role names the product code uses, so every colour in the mockup maps 1:1 to a Tailwind class
  (`bg-card`, `text-muted-foreground`). No hex, no vendor palette, no new role (propose one in NOTES).
- **The app shell**: dark sidebar with the product's real nav groups (closed except the active one),
  header with the org name (and the acting-as banner if staff), content area — the noc pattern.
- **Type, space, radius** per canon §5 (system font stack, Tailwind default sizes, 4 px rhythm,
  `--radius` 0.5 rem); controls at seed sizes (28/32 px).
- **Icons**: inline SVG copied from lucide (the products use `lucide-react ^0.462.0`) or no icon; never a
  different icon family.
- **pt-BR final copy** everywhere (canon §9) — the copy deck is part of the mockup, not a later pass.

### 5.2 Must be clickable
- Every control the code will have, with its real outcome (open panel, filter, save → success state).
- A **state switcher** (a small fixed "Estado" control, outside the shell, labelled "controle do
  mockup") that flips each data region between: loading · empty (first use) · empty (filtered) ·
  error · partial · success · job running · no permission — whichever apply (canon §4.2).
- A **theme switch** (light/dark) in the same control, plus following the OS preference by default.
- A **width** preview: the page must work at 375 px (and 320 px without 2-D scroll except data tables);
  the owner checks it on his phone.

### 5.3 Accessible markup (the mockup is walked with the keyboard)
Real `<button>`/`<a>`/`<label for>`/`<table><th scope>`; a visible focus ring
(`box-shadow: 0 0 0 2px hsl(var(--background)), 0 0 0 4px hsl(var(--ring))` ≈ the house ring,
accessibility §2.3); dialogs that move focus in and return it; `role="status"`/`role="alert"` where the
product will announce. A mockup that cannot be walked by keyboard cannot pass accessibility §4.

### 5.4 Publishing contract (the tech-lead publishes; the designer writes to it)
Subagents have no Artifact tool: the designer writes the file; the tech-lead publishes it as a
**private** claude.ai Artifact and returns the link. Write the file so it publishes cleanly:
- `<title>` = a 2-4 word name ("ROI por portal"); `<html lang="pt-BR">`.
- Colours as tokens on `:root`; dark values under `@media (prefers-color-scheme: dark)` guarded by
  `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`; an explicit `body`
  background.
- External scripts only from cdnjs.cloudflare.com / cdn.jsdelivr.net/npm / unpkg.com /
  cdn.tailwindcss.com / code.jquery.com, each with an exact version; stylesheets only from Google
  Fonts; everything else inline. Prefer **no external script at all** (plain CSS + a few lines of JS).
- Phone width: 16 px side gutter, no horizontal page scroll.
- `localStorage` only for per-viewer conveniences (theme, last state), wrapped in try/catch.

```html
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ROI por portal</title>
<style>
:root{ /* light — verbatim from tokens.css :root */
  --background:0 0% 97%; --foreground:0 0% 10%; --card:0 0% 100%; --muted-foreground:0 0% 50%;
  --primary:220 10% 40%; --primary-foreground:0 0% 100%; --border:0 0% 88%; --ring:220 10% 40%;
  --sidebar-background:0 0% 10%; --sidebar-foreground:0 0% 92%; --radius:.5rem; /* … all roles … */ }
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){ /* .dark block verbatim */
  --background:0 0% 8%; --foreground:0 0% 92%; --card:0 0% 11%; --muted-foreground:0 0% 62%; /* … */ } }
:root[data-theme="dark"]{ /* same dark block again */ }
body{margin:0;background:hsl(var(--background));color:hsl(var(--foreground));
  font-family:ui-sans-serif,system-ui,sans-serif}
:focus-visible{outline:none;box-shadow:0 0 0 2px hsl(var(--background)),0 0 0 4px hsl(var(--ring))}
.num{text-align:right;font-variant-numeric:tabular-nums}
</style></head><body>
<!-- DATA: consulta "portal_roi_resumo" (queries.sql), dados reais 2026-11-05 — ou AMOSTRA -->
<script>const DATA = { /* … */ };</script>
<!-- app shell · page · state/theme switcher (controle do mockup) -->
</body></html>
```
(Only the token NAMES and VALUES above are house facts; layout markup is per screen.)

### 5.5 Where the designer may write
`Write` is for mockup HTML and its notes only — the session scratchpad directory the brief names, or
`projects/<slug>/mockups/<screen>/` (`products/<slug>/projects/<proj>/mockups/<screen>/` for
product-scoped projects). **Never** product or seed source code, KB docs outside a brief, or config.
The tech-lead commits durable copies (the designer has no git).

---

## 6 · Review loop with the owner

1. Self-review first: canon §14 "mockup review" checklist + accessibility §4. Fix before showing.
2. The tech-lead publishes and sends the link with **2-4 tasks** to try ("registre o investimento do
   ZAP de outubro"), not "what do you think?".
3. The owner clicks (think-aloud if he likes; canon §10.2). Feedback is captured verbatim in
   `NOTES.md` under a dated round: what he said · what changed · which earlier decision it replaced.
4. **Change the mockup, not code** — rounds are cheap by design (prototype-on-real-data §3). Each round
   bumps the mockup version (`v1`, `v2` … in the page footer and NOTES).
5. Contradictions with earlier rules or with live data are surfaced to him as a question, never
   silently resolved (memory `feedback-interview-never-assume-specs`).
6. Open decisions batch through skill `noc-questionnaire`; when the owner asks to decide later
   (e.g. the signup brand step he wants to co-design, memory `project-org-brand-identity-in-core`),
   the mockup shows the open point as open.

---

## 7 · Sign-off

- **Sign-off is the owner's words, recorded — never inferred.** The tech-lead relays the owner's
  explicit approval ("aprovado", "pode construir", "go"), and the designer records it in `NOTES.md`:
  `SIGN-OFF <date> · mockup vN (<path or artifact link>) · owner: "<verbatim>"`. Same discipline as the
  prod-exposure rule: an agent may RECORD a decision, never invent one (CLAUDE.md §1).
- **Blocks sign-off:** any severity-4 finding (canon §10.3; accessibility §5 — keyboard/AT blockers are
  4); a region without its states; unlabelled sample content; unanswered scope questions.
- **May be signed with:** listed 1-3 severity findings scheduled into the build; open questions that do
  not change the contract (copy tweaks), each named.
- Post-sign-off changes to layout, flow, data or states need a new round and a new sign-off; copy-only
  tweaks are logged.

---

## 8 · Where files go and what the frontend inherits

```
projects/<slug>/mockups/<screen>/           (or products/<slug>/projects/<proj>/mockups/<screen>/)
  index.html        L2 mockup (committed copy: aggregates/AMOSTRA only — §3 LGPD)
  BRIEF.md          discovery brief (§2)
  queries.sql       one named read-only query per data region → endpoint seeds
  NOTES.md          rounds, decisions, superseded defaults, SIGN-OFF line
  HANDOFF.md        the hand-off package (canon §12): states matrix, data reads, writes, copy deck,
                    organ map, nav + status_pagina, keyboard map, open questions
  a11y-audit.md     accessibility §8 template
  assets/           owner screenshots/refs a decision rests on, with a README mapping file → decision
```

**The frontend inherits** (via `noc-contract-first` step 0 → step 1): the signed-off mockup as the
visual and behavioural contract; the state matrix as acceptance; the queries as endpoint seeds (the
tech-lead/architect author the contract); the copy deck verbatim; the organ map (consume, extend by
named seam, or build the named candidate in the seed). The frontend does not re-decide layout or copy;
a needed deviation (technical limit, organ constraint) goes back to the designer and the owner as a
new round. After ship, the designer compares the shipped screen with the mockup and files deltas
(canon §12); the mockup is then retired or linked from the product docs — never a second source of
truth (prototype-on-real-data §2.3).

---

## 9 · Anti-patterns

| Anti-pattern | Instead |
|---|---|
| Code first "to see how it looks" | L2 mockup, then contract-first |
| Lorem ipsum / invented numbers for data that exists | real data via the connector route (§3) |
| Unlabelled sample | "AMOSTRA" on the page and in NOTES |
| Happy path only | state switcher with every state (§5.2) |
| Light only / desktop only | theme + width checks (§5.2) |
| Vendor screenshot restyled | structure only; noc pattern visuals |
| A `<div>`-soup mockup | real elements; keyboard-walkable (§5.3) |
| "Looks good" taken as sign-off of an unseen state | owner walks the tasks; explicit phrase recorded (§7) |
| Mockup edited after sign-off, code built from the old one | version + new round |
| Real CPF/phone in a committed mockup | aggregates / AMOSTRA in the repo copy (§3) |

---

## 10 · Checklist (copy into NOTES.md)

- [ ] Mandatory? (§1) — carve-out logged if not.
- [ ] BRIEF.md complete; open questions answered by the owner.
- [ ] Data: real (query + date) or AMOSTRA (labelled) or "no access — stated".
- [ ] L0 flow + state matrix; L1 if shape uncertain; L2 built.
- [ ] Tokens verbatim; app shell; nav + status_pagina placement; organs mapped.
- [ ] Every region × state; light + dark; 375 px + desktop; keyboard-walkable.
- [ ] pt-BR copy deck final; numbers/dates/nulls per canon §9.3.
- [ ] Self-review (canon §14) + accessibility §4 done; findings rated.
- [ ] Published by the tech-lead; rounds logged; SIGN-OFF line recorded.
- [ ] HANDOFF.md + a11y-audit.md written; tech-lead commits the durable copy.

---

## Worked example — the first two instances, read through this protocol

- **Usage-evaluation dashboard (2026-11-04)** — a data-display screen: tables `public.dev_telemetry_*`
  (core migration 097) fed by `noctus.dev.usage_eval`, prototype page on the owner's claude.ai Supabase
  connector (prototype-on-real-data §4; `KB § PATTERNS/devops/usage-evaluation.md`). In this protocol:
  data route §3(a), L2 directly (known dashboard shape), sign-off on real numbers.
- **Twin video editor (2026-11-04)** — an interaction-heavy screen whose data did not exist yet:
  `products/social-wiring/projects/core-studio-build/specs/twin-editor-design.md` starts "design draft for
  the owner interview. Nothing is decided and nothing is built", derives structure from a private study
  with "no vendor code, copy or assets", puts the flow first (§0.1 batch flow) and places the screen in
  the IA explicitly (§0.1b: one sidebar item, in-page subtabs, no new sidebar groups — the MENUS rule).
  The owner then ruled the visuals: "we'll keep the noc pattern" (memory `feedback-noc-pattern-not-vendor-look`).
  In this protocol: §2 brief = that spec's §0; data = AMOSTRA (no batch had ever run); L1/L2 on a
  canvas; the owner's "no we wont use their design" is a recorded decision superseding the study's look.

---

## Sources

| Title | URL | Supports | Accessed |
|---|---|---|---|
| NN/g — UX Prototypes: Low Fidelity vs. High Fidelity | https://www.nngroup.com/articles/ux-prototype-hi-lo-fidelity/ | §4 | 2026-11-05 |
| NN/g — Thinking Aloud: The #1 Usability Tool | https://www.nngroup.com/articles/thinking-aloud-the-1-usability-tool/ | §6 | 2026-11-05 |
| MDN — prefers-color-scheme | https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme | §5.2 · §5.4 | 2026-11-05 |

House sources (in tree): `KB § PATTERNS/frontend/prototype-on-real-data.md` · `CLAUDE/frontend.md`
rule 1 · `.claude/skills/noc-contract-first/SKILL.md` step 0 · `seed/lib/frontend/src/design-system/tokens.css` ·
the Artifact tool's publishing contract (harness, no public URL) for §5.4.

## Composes with
`KB § PATTERNS/design/design-craft-canon.md` · `KB § PATTERNS/design/accessibility.md` ·
`KB § PATTERNS/frontend/prototype-on-real-data.md` · `KB § PATTERNS/frontend/frontend-craft-canon.md` ·
skills `noc-contract-first` · `noc-organ-consume-check` · `noc-questionnaire` · `noc-reverse-engineer`.
