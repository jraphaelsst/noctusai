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
 *   7. Validators (UUID / year / month / tipo / tier / date) — accept + reject.
 *   8. Malformed URL values (`?origem_id=senseys` — the previously-shipped
 *      slug bug) are dropped from state AND scrubbed from the URL, so the
 *      page hydrates clean instead of building a 422-triggering request.
 *   9. The "some filters were invalid" notice fires exactly once per
 *      hydration event, even when multiple `useLeadsFilters()` instances
 *      mount simultaneously (the real shape: `LeadsFilterBar` + the active
 *      subtab both read the same URL).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  buildLeadsQueryParams,
  parseLeadsFilters,
  parseLeadsFiltersDetailed,
  useLeadsFilters,
  EMPTY_FILTERS,
  isValidUuid,
  isValidYear,
  isValidMonth,
  isValidTipo,
  isValidTier,
  isValidDateStr,
} from "./useLeadsFilters";

vi.mock("sonner", () => ({
  toast: { warning: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const UUID_A = "11111111-1111-4111-8111-111111111111";
const UUID_B = "22222222-2222-4222-8222-222222222222";

function wrapper(initialEntries: string[]) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(MemoryRouter, { initialEntries }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── Validators ──────────────────────────────────────────────────────────────

describe("isValidUuid", () => {
  it("accepts a well-formed UUID", () => {
    expect(isValidUuid(UUID_A)).toBe(true);
    expect(isValidUuid(UUID_A.toUpperCase())).toBe(true);
  });

  it("rejects a slug (the exact shape the previous bug wrote: ?origem_id=senseys)", () => {
    expect(isValidUuid("senseys")).toBe(false);
  });

  it("rejects near-miss shapes (wrong segment lengths, missing dashes, empty)", () => {
    expect(isValidUuid("1111111-1111-4111-8111-111111111111")).toBe(false);
    expect(isValidUuid("111111111111411181111111111111")).toBe(false);
    expect(isValidUuid("")).toBe(false);
  });
});

describe("isValidYear", () => {
  it("accepts a plausible 4-digit year", () => {
    expect(isValidYear("2025")).toBe(true);
    expect(isValidYear("2000")).toBe(true);
    expect(isValidYear("2100")).toBe(true);
  });

  it("rejects non-numeric, wrong-length, and implausible years", () => {
    expect(isValidYear("abcd")).toBe(false);
    expect(isValidYear("25")).toBe(false);
    expect(isValidYear("1899")).toBe(false);
    expect(isValidYear("2101")).toBe(false);
    expect(isValidYear("")).toBe(false);
  });
});

describe("isValidMonth", () => {
  it("accepts 1..12", () => {
    for (const m of ["1", "6", "9", "10", "12"]) expect(isValidMonth(m)).toBe(true);
  });

  it("rejects 0, 13+, non-numeric", () => {
    expect(isValidMonth("0")).toBe(false);
    expect(isValidMonth("13")).toBe(false);
    expect(isValidMonth("abc")).toBe(false);
    expect(isValidMonth("")).toBe(false);
  });
});

describe("isValidTipo", () => {
  it("accepts the three backend enum values", () => {
    expect(isValidTipo("novo")).toBe(true);
    expect(isValidTipo("retorno")).toBe(true);
    expect(isValidTipo("desconhecido")).toBe(true);
  });

  it("rejects anything outside the enum", () => {
    expect(isValidTipo("Novo")).toBe(false);
    expect(isValidTipo("outro")).toBe(false);
    expect(isValidTipo("")).toBe(false);
  });
});

describe("isValidTier", () => {
  it("accepts the three backend enum values", () => {
    expect(isValidTier("simples")).toBe(true);
    expect(isValidTier("destaque")).toBe(true);
    expect(isValidTier("super_destaque")).toBe(true);
  });

  it("rejects anything outside the enum", () => {
    expect(isValidTier("premium")).toBe(false);
    expect(isValidTier("")).toBe(false);
  });
});

describe("isValidDateStr", () => {
  it("accepts strict YYYY-MM-DD real calendar dates", () => {
    expect(isValidDateStr("2026-01-01")).toBe(true);
    expect(isValidDateStr("2026-02-28")).toBe(true);
    expect(isValidDateStr("2024-02-29")).toBe(true); // leap year
  });

  it("rejects malformed shapes and impossible calendar dates", () => {
    expect(isValidDateStr("2026-1-1")).toBe(false); // no zero-padding
    expect(isValidDateStr("2026/01/01")).toBe(false);
    expect(isValidDateStr("2026-02-30")).toBe(false); // Feb has no 30th
    expect(isValidDateStr("2026-13-01")).toBe(false); // month 13
    expect(isValidDateStr("not-a-date")).toBe(false);
    expect(isValidDateStr("")).toBe(false);
  });
});

// ─── parseLeadsFilters / parseLeadsFiltersDetailed ─────────────────────────

describe("parseLeadsFilters", () => {
  it("reads repeatable params via getAll", () => {
    const params = new URLSearchParams(`ano=2025&ano=2026&origem_id=${UUID_A}`);
    const filters = parseLeadsFilters(params);
    expect(filters.ano).toEqual(["2025", "2026"]);
    expect(filters.origem_id).toEqual([UUID_A]);
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

  it("ignores unknown params instead of crashing", () => {
    const filters = parseLeadsFilters(new URLSearchParams("utm_source=newsletter&foo=bar"));
    expect(filters).toEqual(EMPTY_FILTERS);
  });

  it("drops a slug written into origem_id (the previously-shipped bug's exact shape)", () => {
    const filters = parseLeadsFilters(new URLSearchParams("origem_id=senseys"));
    expect(filters.origem_id).toEqual([]);
  });

  it("drops out-of-range ano/mes, invalid tipo/tier, and malformed de/ate — keeps the rest", () => {
    const filters = parseLeadsFilters(
      new URLSearchParams(
        `ano=1899&mes=13&tipo=bogus&tier=bogus&de=2026-02-30&ate=not-a-date&q=joao&${
          `origem_id=${UUID_A}`
        }`,
      ),
    );
    expect(filters.ano).toEqual([]);
    expect(filters.mes).toEqual([]);
    expect(filters.tipo).toEqual([]);
    expect(filters.tier).toEqual([]);
    expect(filters.de).toBeNull();
    expect(filters.ate).toBeNull();
    expect(filters.origem_id).toEqual([UUID_A]);
    expect(filters.q).toBe("joao");
  });

  it("does not validate empreendimento/regiao — free-text facets pass through", () => {
    const filters = parseLeadsFilters(new URLSearchParams("empreendimento=Residencial+Alfa&regiao=Zona+Sul"));
    expect(filters.empreendimento).toEqual(["Residencial Alfa"]);
    expect(filters.regiao).toEqual(["Zona Sul"]);
  });
});

describe("parseLeadsFiltersDetailed", () => {
  it("reports invalidKeys only for keys that had something dropped", () => {
    const { invalidKeys } = parseLeadsFiltersDetailed(
      new URLSearchParams(`origem_id=senseys&ano=2025&mes=13`),
    );
    expect(invalidKeys.sort()).toEqual(["mes", "origem_id"]);
  });

  it("reports no invalidKeys for a fully well-formed URL", () => {
    const { invalidKeys } = parseLeadsFiltersDetailed(
      new URLSearchParams(`origem_id=${UUID_A}&ano=2025&tipo=novo`),
    );
    expect(invalidKeys).toEqual([]);
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

// ─── useLeadsFilters (hook) ─────────────────────────────────────────────────

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
    act(() => result.current.toggleMulti("origem_id", UUID_A));
    expect(result.current.filters.origem_id).toEqual([UUID_A]);
  });

  it("toggleMulti removes a value already present", () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper([`/leads?origem_id=${UUID_A}&origem_id=${UUID_B}`]),
    });
    act(() => result.current.toggleMulti("origem_id", UUID_A));
    expect(result.current.filters.origem_id).toEqual([UUID_B]);
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

  it("a valid UUID hydrates correctly and round-trips to the URL", async () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper([`/leads?origem_id=${UUID_A}&corretor_id=${UUID_B}`]),
    });
    expect(result.current.filters.origem_id).toEqual([UUID_A]);
    expect(result.current.filters.corretor_id).toEqual([UUID_B]);
    expect(result.current.queryString).toContain(`origem_id=${UUID_A}`);
    expect(result.current.queryString).toContain(`corretor_id=${UUID_B}`);
    // No sanitization event for a clean URL.
    await waitFor(() => expect(toast.warning).not.toHaveBeenCalled());
  });
});

// ─── Self-healing malformed-URL hydration (the bricking bug) ───────────────

describe("useLeadsFilters — malformed URL self-heals", () => {
  it("?origem_id=senseys yields EMPTY origem_id state (not a 422-triggering request)", async () => {
    function useProbe() {
      const filtersHook = useLeadsFilters();
      const [params] = useSearchParams();
      return { ...filtersHook, rawSearch: params.toString() };
    }

    const { result } = renderHook(() => useProbe(), {
      wrapper: wrapper(["/leads?origem_id=senseys"]),
    });

    expect(result.current.filters.origem_id).toEqual([]);

    await waitFor(() => expect(result.current.rawSearch).not.toContain("senseys"));
    expect(result.current.rawSearch).not.toContain("origem_id");
  });

  it("scrubs only the invalid known key — unrelated params survive untouched", async () => {
    function useProbe() {
      const filtersHook = useLeadsFilters();
      const [params] = useSearchParams();
      return { ...filtersHook, rawSearch: params.toString() };
    }

    const { result } = renderHook(() => useProbe(), {
      wrapper: wrapper(["/leads?origem_id=badvalue&q=joao&utm_source=newsletter"]),
    });

    await waitFor(() => expect(result.current.rawSearch).not.toContain("origem_id"));
    expect(result.current.rawSearch).toContain("q=joao");
    expect(result.current.rawSearch).toContain("utm_source=newsletter");
    expect(result.current.filters.q).toBe("joao");
  });

  it("fires the invalid-filters notice exactly once per hydration event", async () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper(["/leads?origem_id=onlyonce&ano=1899&mes=99"]),
    });

    await waitFor(() => expect(result.current.filters.origem_id).toEqual([]));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledTimes(1));
  });

  it("fires the notice ONCE even when two hook instances hydrate the same bad URL simultaneously (LeadsFilterBar + the active subtab)", async () => {
    function useTwoInstances() {
      const a = useLeadsFilters();
      const b = useLeadsFilters();
      return { a, b };
    }

    const { result } = renderHook(() => useTwoInstances(), {
      wrapper: wrapper(["/leads?corretor_id=sharedbad"]),
    });

    await waitFor(() => expect(result.current.a.filters.corretor_id).toEqual([]));
    expect(result.current.b.filters.corretor_id).toEqual([]);
    await waitFor(() => expect(toast.warning).toHaveBeenCalledTimes(1));
  });

  it("does not fire the notice at all for a clean URL", async () => {
    const { result } = renderHook(() => useLeadsFilters(), {
      wrapper: wrapper([`/leads?origem_id=${UUID_A}&ano=2025`]),
    });
    expect(result.current.filters.origem_id).toEqual([UUID_A]);
    await waitFor(() => expect(toast.warning).not.toHaveBeenCalled());
  });
});
