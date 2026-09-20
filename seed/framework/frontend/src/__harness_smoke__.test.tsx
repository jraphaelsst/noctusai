// Harness smoke test — proves this product's FE vitest stack (vitest + jsdom +
// @testing-library/react, single React instance) actually RUNS in CI. Born from
// the unenforced-gate lesson (KB § branching-and-merging §0.2a): social-wiring
// shipped FE tests that COULD NOT run (missing deps) and nobody noticed because
// no product ran FE vitest in CI. This minimal test gates that the harness itself
// is healthy; augment with real component tests as the product grows them.
//
// SEED-OWNED (absorbed 2026-09-20 — was byte-identical across 3 products'
// local copies, N≥3 recurrence rule). A product consumes this exactly like
// `vite.config.ts`/`vitest.config.ts` consume their seed factories: a thin
// local file that imports the shared implementation —
//   // products/<slug>/frontend/src/__harness_smoke__.test.tsx
//   import "../../../../seed/framework/frontend/src/__harness_smoke__.test";
// Lives under `src/`, NOT `seed/framework/frontend/tests/`, so it is never
// picked up twice by the seed's own vitest suite (whose `include` is scoped
// to `tests/**`) — it only runs when a product's local shim imports it.
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";

afterEach(() => cleanup());

describe("FE harness smoke", () => {
  it("vitest executes", () => {
    expect(1 + 1).toBe(2);
  });

  it("jsdom + testing-library render a single-React tree", () => {
    const { getByText } = render(<div>noctus-harness-ok</div>);
    expect(getByText("noctus-harness-ok")).toBeTruthy();
  });
});
