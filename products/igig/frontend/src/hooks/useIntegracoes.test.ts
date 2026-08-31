/**
 * Tests for `useIntegracoes` — the refetch-unmount regression (fleet
 * audit, 2026-08-31). Category A only (static query key) — no
 * `placeholderData` needed, just the `loading` formula.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet } }));

let queryState: Record<string, unknown> = {};

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(() => queryState);
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useIntegracoes } from "./useIntegracoes";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useIntegracoes — loading formula", () => {
  it("REGRESSION: does not report loading mid-refetch once the channel list is on screen", () => {
    // e.g. right after useConectarCanal/useDesconectarCanal invalidate.
    queryState = {
      data: [{ canal: "instagram", conectado: true }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, integracoes } = useIntegracoes();
    expect(loading).toBe(false);
    expect(integracoes).toHaveLength(1);
  });

  it("is true on first load", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(useIntegracoes().loading).toBe(true);
  });
});

describe("useIntegracoes — cofreConfigurado", () => {
  it("is null before the list has ever loaded — never a false 'not configured' flash", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(useIntegracoes().cofreConfigurado).toBeNull();
  });

  it("reads the flag off the loaded list (one key encrypts every channel)", () => {
    queryState = {
      data: [{ canal: "instagram", conectado: false, cofre_configurado: true }],
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    };
    expect(useIntegracoes().cofreConfigurado).toBe(true);
  });

  it("surfaces false so the page can warn before a save fails", () => {
    queryState = {
      data: [{ canal: "instagram", conectado: false, cofre_configurado: false }],
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    };
    expect(useIntegracoes().cofreConfigurado).toBe(false);
  });
});
