/**
 * useLeadsFilters.test.ts — unit tests for the shared Leads filter state
 * (§5.1 of leads-module-PROJECT.md), mirrored to the URL query string.
 *
 * Covers:
 *   1. parseLeadsFilters reads repeatable (`getAll`) vs single params correctly.
 *   2. buildLeadsQueryParams round-trips multi-value dims as REPEATED params
 *      (never comma-joined) — the wire shape the contract requires.
 *   3. Empty/absent filters produce no params (no constraint).
 *   4. useLeadsFilters — reads initial state from the URL.
 *   5. toggleMulti adds/removes a value and writes back to the URL.
 *   6. clearAll wipes every param.
 */
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import {
  buildLeadsQueryParams,
  parseLeadsFilters,
  useLeadsFilters,
  EMPTY_FILTERS,
} from "./useLeadsFilters";

function wrapper(initialEntries: string[]) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(MemoryRouter, { initialEntries }, children);
}

describe("parseLeadsFilters", () => {
  it("reads repeatable params via getAll", () => {
    const params = new URLSearchParams("ano=2025&ano=2026&origem_id=abc");
    const filters = parseLeadsFilters(params);
    expect(filters.ano).toEqual(["2025", "2026"]);
    expect(filters.origem_id).toEqual(["abc"]);
  });

  it("reads single params + needs_review boolean + q", () => {
    const params = new URLSearchParams("de=2026-01-01&ate=2026-06-30&needs_review=true&q=joao");
    const filters = parseLeadsFilters(params);
    expect(filters.de).toBe("2026-01-01");
    expect(filters.ate).toBe("2026-06-30");
    expect(filters.needs_review).toBe(true);
    expect(filters.q).toBe("joao");
  });

  it("absent params parse to empty/null", () => {
    const filters = parseLeadsFilters(new URLSearchParams());
    expect(filters).toEqual(EMPTY_FILTERS);
  });
});

describe("buildLeadsQueryParams", () => {
  it("encodes multi-value dims as repeated params, never comma-joined", () => {
    const params = buildLeadsQueryParams({
      ...EMPTY_FILTERS,
      ano: ["2025", "2026"],
      tipo: ["novo"],
    });
    expect(params.getAll("ano")).toEqual(["2025", "2026"]);
    expect(params.toString()).not.toContain("2025,2026");
    expect(params.getAll("tipo")).toEqual(["novo"]);
  });

  it("omits absent/empty filters entirely", () => {
    const params = buildLeadsQueryParams(EMPTY_FILTERS);
    expect(params.toString()).toBe("");
  });

  it("includes needs_review only when set (not null)", () => {
    const withFlag = buildLeadsQueryParams({ ...EMPTY_FILTERS, needs_review: true });
    expect(withFlag.get("needs_review")).toBe("true");

    const withoutFlag = buildLeadsQueryParams(EMPTY_FILTERS);
    expect(withoutFlag.has("needs_review")).toBe(false);
  });
});

describe("useLeadsFilters", () => {
  it("reads initial filters from the URL", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads?ano=2025&tipo=novo&tipo=retorno"]),
    });
    expect(result.current.filters.ano).toEqual(["2025"]);
    expect(result.current.filters.tipo).toEqual(["novo", "retorno"]);
    expect(result.current.activeCount).toBe(3);
  });

  it("toggleMulti adds a value not yet present", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads"]),
    });
    act(() => result.current.toggleMulti("origem_id", "src-1"));
    expect(result.current.filters.origem_id).toEqual(["src-1"]);
  });

  it("toggleMulti removes a value already present", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads?origem_id=src-1&origem_id=src-2"]),
    });
    act(() => result.current.toggleMulti("origem_id", "src-1"));
    expect(result.current.filters.origem_id).toEqual(["src-2"]);
  });

  it("clearAll wipes every filter", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads?ano=2025&q=joao&needs_review=true"]),
    });
    act(() => result.current.clearAll());
    expect(result.current.filters).toEqual(EMPTY_FILTERS);
    expect(result.current.isActive).toBe(false);
  });

  it("setDateRange writes both de/ate", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads"]),
    });
    act(() => result.current.setDateRange("2026-01-01", "2026-06-30"));
    expect(result.current.filters.de).toBe("2026-01-01");
    expect(result.current.filters.ate).toBe("2026-06-30");
  });
});
