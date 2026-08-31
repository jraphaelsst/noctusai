/**
 * Tests for `useClientes` — the refetch-unmount + key-change-flicker
 * regression (fleet audit, 2026-08-31). Mocks `@tanstack/react-query`
 * itself so the hook's real `loading` formula and `placeholderData` option
 * are exercised, not stubbed.
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

import { useClientes } from "./useClientes";

beforeEach(() => {
  vi.clearAllMocks();
  capturedOpts.length = 0;
  queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
});

describe("useClientes — loading formula", () => {
  it("is true on first load", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(useClientes().loading).toBe(true);
  });

  it("REGRESSION: is false while a filtered refetch is in flight but the previous page's data is present", () => {
    // busca/status keyed queries land here on every keystroke: isPending
    // false (placeholderData keeps `data` populated), isFetching true.
    queryState = {
      data: { itens: [{ id: "c1", nome: "Padaria Sol" }], total: 1 },
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, clientes } = useClientes({ busca: "pad" });
    expect(loading).toBe(false);
    expect(clientes).toHaveLength(1);
  });
});

describe("useClientes — placeholderData", () => {
  it("passes placeholderData so a busca/status key change keeps the previous page on screen", () => {
    useClientes({ busca: "a" });
    expect(capturedOpts[0]?.placeholderData).toBeTypeOf("function");
    const placeholderData = capturedOpts[0]?.placeholderData as (prev: unknown) => unknown;
    const previous = { itens: [], total: 0 };
    expect(placeholderData(previous)).toBe(previous);
  });
});

describe("useClientes — empty branch guard", () => {
  it("never reports a non-null-looking clientes array as the FIRST-load signal — total/clientes stay empty defaults while pending", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    const { loading, clientes, total } = useClientes();
    // `loading` is what the page actually gates the empty-state on; this
    // guards against a future change that flips `loading` to false while
    // `data` is still undefined (which is exactly the class of bug that
    // rendered "Sem dados" over 28 brokers / 12,177 leads on 2026-07-21).
    expect(loading).toBe(true);
    expect(clientes).toEqual([]);
    expect(total).toBe(0);
  });
});
