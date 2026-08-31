/**
 * Tests for `useMarca` — the refetch-unmount regression (fleet audit,
 * 2026-08-31). `useMarcas`/`useRepertorio`/`useAcessos` all back Category A
 * page gates (`Marca.tsx:114`, `RepertorioSidebar.tsx:79`, `Marca.tsx:250`)
 * — this is the user's literal complaint: "edit one field and a whole
 * block of UI vanishes." None are in the Category B key-change list, so no
 * `placeholderData` is added here.
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

import { useAcessos, useMarcas, useRepertorio } from "./useMarca";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useMarcas — loading formula", () => {
  it("REGRESSION: does not report loading right after useAtualizarMarca invalidates the list — the 'block vanishes on edit' bug", () => {
    queryState = {
      data: [{ id: "m1", nome: "Sol Pães", tom_de_voz: "Caloroso" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, marcas } = useMarcas("cliente-1");
    expect(loading).toBe(false);
    expect(marcas).toHaveLength(1);
  });
});

describe("useRepertorio — loading formula", () => {
  it("REGRESSION: does not report loading while the persistent sidebar's data refetches", () => {
    queryState = {
      data: { cliente_nome: "Padaria Sol", marca_nome: "Sol Pães" },
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, repertorio } = useRepertorio("cliente-1");
    expect(loading).toBe(false);
    expect(repertorio?.marca_nome).toBe("Sol Pães");
  });
});

describe("useAcessos — loading formula", () => {
  it("REGRESSION: does not report loading right after useCriarAcesso/useRemoverAcesso invalidate the cofre", () => {
    queryState = {
      data: {
        cofre_configurado: true,
        itens: [{ id: "a1", rotulo: "Meta Business", tem_senha: true }],
      },
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, acessos } = useAcessos("cliente-1");
    expect(loading).toBe(false);
    expect(acessos).toHaveLength(1);
  });
});

describe("useAcessos — cofreConfigurado", () => {
  it("is null before the client's vault has ever loaded", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(useAcessos("cliente-1").cofreConfigurado).toBeNull();
  });

  it("is read off the wrapper, independent of whether itens is empty", () => {
    queryState = {
      data: { cofre_configurado: false, itens: [] },
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    };
    const { cofreConfigurado, acessos } = useAcessos("cliente-1");
    expect(cofreConfigurado).toBe(false);
    expect(acessos).toHaveLength(0);
  });
});
