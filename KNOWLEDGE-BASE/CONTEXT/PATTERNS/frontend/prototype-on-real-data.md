# Prototype first — a clickable mockup, on real data where it exists, then code

**Rule.** No UI is built before the owner has clicked through it. A new page or tool (a dashboard, an
admin view, a product screen, an editor) is first built as a **clickable mockup** on the noc pattern
(the seed tokens and app shell, never a vendor's look). It reads the **REAL database** wherever the
data exists. It is iterated with the owner until it is right, and only then written as product code.
Never code-first for a screen whose shape is still unknown.

Sample content is allowed in exactly one case: the real data **does not exist yet** (a feature that has
never run, such as an editor before its first video). It is then labelled as sample on the mockup and in
the report, and swapped for real data as soon as the data exists. Sample content never stands in for
data that exists but was not wired up.

Owner, 2026-11-04 (two statements the same day):
- *"the new dashboard page … it should consume real data from db so we have a real scenario. we'll use
  that to develop a page and funcs, validate, and then create code"*
- after the Twin editor mockup: *"let's implement the mockuping before building ui so we can easily
  modify it before building, so we gain time and speed"*

## 0 · Two kinds of screen

| Screen | What the mockup must prove | Data |
|---|---|---|
| **Data-display** (dashboard, report, list) | The numbers and their edge cases (empties, nulls, outliers) | Real, always (§ 2) |
| **Interaction-heavy** (editor, wizard, builder) | The flow, the controls and the states (loading, empty, error, done) | Real where it exists, else labelled sample |

Both are claude.ai artifacts (private), and both use the seed tokens
(`@noctusai/lib/design-system/tokens.css`) in light and dark. Every control the code will have is
there and clickable. A canvas artifact (the Design type, one artboard per screen) suits an
interaction mockup. First instance: the Twin video editor
(`products/social-wiring/projects/core-studio-build/specs/twin-editor-design.md`).

## 1 · Why

Mock data hides the cases that decide a page's design: empty windows, nulls, one session dwarfing the
rest, a metric that is always zero. Code-first spends a migration, an endpoint, a hook, tests and a
deploy on a layout the owner has not seen. A page on real data shows both within minutes, and the
validated page becomes the contract for the code.

## 2 · The three steps

1. **Data first, in its real home.** The tables the page needs exist in the real DB, through a normal
   migration (named in the product's README/MASTER-PROMPT), and real rows flow into them. A
   prototype never invents a side store the code would not use.
2. **Prototype page on that data.** A private claude.ai artifact page that reads the DB through the
   owner's Supabase connector (`mcp` capability, read-only SQL). Every number on it is a query the
   code will also run. The queries ARE the future endpoint's contract.
3. **Validate, then code.** The owner reviews the page against real numbers; changes land in the
   prototype until it is right. Then the page is built as product code: contract-first
   (`skill noc-contract-first`), the prototype's queries become the endpoint, its layout becomes the
   component built from canonical organs (`skill noc-organ-consume-check`). The prototype is retired
   or linked from the shipped page's docs, never left as a second source of truth.

## 3 · Guardrails

- Read-only. A prototype never writes to the DB; writes belong to the code that follows.
- Private by default. It shows real data, so share only with people allowed to see that data.
- Counts and aggregates over raw personal data; LGPD rules apply as in product code.
- When the prototype cannot reach data that exists (no connector, table not migrated yet), say so on
  the page and to the owner. Never fill it with sample numbers. Sample content only for data that does
  not exist yet (§ 0), labelled.
- The mockup is the owner's design surface: change it until it is right, because a change there costs
  minutes and a change in code costs a slice. Once it is validated, the code follows it; it does not
  re-decide it.

## 4 · First instance

The usage-evaluation dashboard (2026-11-04): `public.dev_telemetry_*` (core migration 097), fed by
`noctus.dev.usage_eval`, prototype page on the owner's claude.ai Supabase connector →
`KB § PATTERNS/devops/usage-evaluation.md`.
