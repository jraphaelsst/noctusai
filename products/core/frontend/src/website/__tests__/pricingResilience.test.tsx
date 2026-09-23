import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { planFeatureList } from "../lib/api";
import { SectionErrorBoundary } from "../components/SectionErrorBoundary";

describe("planFeatureList — plans.features is JSONB (default {}), not an array", () => {
  it("returns [] for the live shape {}", () => {
    expect(planFeatureList({})).toEqual([]);
  });
  it("keeps string/number items of an array", () => {
    expect(planFeatureList(["A", 2, null, { x: 1 }])).toEqual(["A", "2"]);
  });
  it("maps an object to true-keys and key: value pairs", () => {
    expect(planFeatureList({ sso: true, beta: false, storage: "10 GB", seats: 5 })).toEqual([
      "sso",
      "storage: 10 GB",
      "seats: 5",
    ]);
  });
  it("returns [] for null / scalars", () => {
    expect(planFeatureList(null)).toEqual([]);
    expect(planFeatureList("x")).toEqual([]);
  });
});

describe("SectionErrorBoundary — one failing section never blanks the page", () => {
  function Boom(): never {
    throw new Error("boom");
  }
  it("hides only the failing section and reports it loudly", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <div>
        <p>outside</p>
        <SectionErrorBoundary name="pricing">
          <Boom />
        </SectionErrorBoundary>
      </div>,
    );
    expect(screen.getByText("outside")).toBeTruthy();
    expect(spy.mock.calls.some((c) => String(c[0]).includes('section "pricing" failed'))).toBe(true);
    spy.mockRestore();
  });
});
