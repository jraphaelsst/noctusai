# Prototype on real data — page first, validated, then code

**Rule.** A new page (a dashboard, an admin view, a product screen) is first built as a **prototype page
that reads the REAL database**, validated with the owner on real numbers, and only then written as
product code. Never a mock-data prototype, never code-first for a page whose shape is still unknown.

Owner, 2026-11-04: *"the new dashboard page … it should consume real data from db so we have a real
scenario. we'll use that to develop a page and funcs, validate, and then create code"* — declared a
methodology change the same day.

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
- When the prototype cannot reach the data (no connector, table not migrated yet), say so on the page
  and to the owner. Never fill it with sample numbers.

## 4 · First instance

The usage-evaluation dashboard (2026-11-04): `public.dev_telemetry_*` (core migration 097), fed by
`noctus.dev.usage_eval`, prototype page on the owner's claude.ai Supabase connector →
`KB § PATTERNS/devops/usage-evaluation.md`.
