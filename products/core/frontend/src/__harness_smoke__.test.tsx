// Harness smoke test — proves this product's FE vitest stack (vitest + jsdom +
// @testing-library/react, single React instance) actually RUNS in CI. Born from
// the unenforced-gate lesson (KB § branching-and-merging §0.2a): social-wiring
// shipped FE tests that COULD NOT run (missing deps) and nobody noticed because
// no product ran FE vitest in CI. This minimal test gates that the harness itself
// is healthy; augment with real component tests as the product grows them.
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
