/**
 * Tests for `usePautas` — the refetch-unmount + key-change-flicker
 * regression (fleet audit, 2026-08-31). `useCalendario` is the Category
 * A+B "compounding" case named in the brief: paging Calendário to the next
 * month changes `[inicio, fim]` (a new query key) AND used to gate on
 * `isPending || isFetching` — so a page turn wiped the whole grid.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet } }));

let queryState: Record<string, unknown> = {};
const { capturedOpts } = vi.hoisted(() => ({ capturedOpts: [] as Record<string, unknown>[] }));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn((opts: Record<string, unknown>) => {
    capturedOpts.push(opts);
    return queryState;
  });
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useCalendario } from "./usePautas";

beforeEach(() => {
  vi.clearAllMocks();
  capturedOpts.length = 0;
});

describe("useCalendario — loading formula", () => {
  it("REGRESSION: does not report loading while paging to a new month (new key, previous month's data present via placeholderData)", () => {
    queryState = {
      data: { inicio: "2026-08-01", fim: "2026-08-31", itens: [{ id: "p1" }] },
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, itens } = useCalendario("2026-09-01T00:00:00", "2026-09-30T23:59:59");
    expect(loading).toBe(false);
    expect(itens).toHaveLength(1);
  });

  it("is true on genuine first load", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(useCalendario("2026-08-01", "2026-08-31").loading).toBe(true);
  });
});

describe("useCalendario — placeholderData", () => {
  it("keeps the previous month's pautas on screen while the next month loads", () => {
    useCalendario("2026-08-01", "2026-08-31");
    const placeholderData = capturedOpts[0]?.placeholderData as (prev: unknown) => unknown;
    expect(placeholderData).toBeTypeOf("function");
    const previous = { inicio: "x", fim: "y", itens: [] };
    expect(placeholderData(previous)).toBe(previous);
  });
});
