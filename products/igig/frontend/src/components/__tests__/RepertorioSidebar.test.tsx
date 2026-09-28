/**
 * RepertorioSidebar — render-level regression test for the refetch-unmount
 * bug (fleet audit, 2026-08-31). This IS the user's literal complaint: the
 * sidebar is "ambient chrome on a work screen" (see the module docstring)
 * that must never blank out — but `useAtualizarMarca` invalidates
 * `["igig","repertorio"]` on EVERY field save, and the old
 * `isPending || isFetching` gate replaced the whole card with
 * "Carregando repertório…" on every one of those saves.
 *
 * Mocks `@tanstack/react-query` itself so the real `useRepertorio()`/
 * `useMarcas()` run — this is not a stub of either hook's return shape. The
 * mock is QUERY-KEY-AWARE (the sidebar now calls `useQuery` twice — once for
 * the marca switcher's list, once for the chosen marca's repertório —
 * achado 2's "let the user pick" fix) so each call gets the shape it expects.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
}));

const { mockUseQuery } = vi.hoisted(() => ({ mockUseQuery: vi.fn() }));
vi.mock("@tanstack/react-query", () => {
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery: mockUseQuery, useMutation, useQueryClient };
});

import { RepertorioSidebar } from "../RepertorioSidebar";
import type { Marca, Repertorio } from "@/hooks/useMarca";

const MARCA: Marca = {
  id: "marca-1",
  org_id: "org-1",
  cliente_id: "cliente-1",
  nome: "Sol Pães",
  logo_url: null,
  paleta: [{ nome: "primária", hex: "#f97316" }],
  tom_de_voz: "Caloroso e direto.",
  termos_proibidos: null,
  nivel_formalidade: "informal",
  linhas_editoriais: [],
  personas: [],
};

const REPERTORIO: Repertorio = {
  cliente_nome: "Padaria Sol",
  marca_id: "marca-1",
  marca_nome: "Sol Pães",
  logo_url: null,
  paleta: [{ nome: "primária", hex: "#f97316" }],
  tom_de_voz: "Caloroso e direto.",
  termos_proibidos: null,
  nivel_formalidade: "informal",
  linhas_editoriais: [],
};

/** Route each `useQuery` call by its key's second segment — "marcas" or
 * "repertorio" — to the fixture that call is actually for. */
function mockarQueries(estado: {
  marcas?: { data?: Marca[]; isPending?: boolean; isFetching?: boolean };
  repertorio?: { data?: Repertorio; isPending?: boolean; isFetching?: boolean };
}) {
  mockUseQuery.mockImplementation((opts: { queryKey: unknown[] }) => {
    const chave = opts.queryKey[1];
    const base = { isError: false, error: null, isPending: false, isFetching: false };
    if (chave === "marcas") return { ...base, data: [MARCA], ...estado.marcas };
    if (chave === "repertorio") return { ...base, data: REPERTORIO, ...estado.repertorio };
    throw new Error(`unexpected queryKey in test: ${JSON.stringify(opts.queryKey)}`);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RepertorioSidebar — persistent chrome must not blank on a background refetch", () => {
  it("keeps the tom de voz on screen while `useAtualizarMarca` invalidates it (isFetching, data present)", () => {
    mockarQueries({ repertorio: { isFetching: true } });

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Caloroso e direto.")).toBeInTheDocument();
    expect(screen.queryByText("Carregando repertório…")).not.toBeInTheDocument();
  });

  it("shows the loading copy only on genuine first load (no data yet)", () => {
    mockarQueries({
      repertorio: { data: undefined, isPending: true, isFetching: true },
    });

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Carregando repertório…")).toBeInTheDocument();
    expect(screen.queryByText(/Sol Pães/)).not.toBeInTheDocument();
  });

  it("degrades quietly to 'indisponível' — never an error banner — once settled with no repertório", () => {
    mockarQueries({ repertorio: { data: undefined } });

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Repertório indisponível.")).toBeInTheDocument();
  });

  it("shows a switcher instead of picking a marca silently once the cliente carries N (achado 2)", () => {
    const segunda: Marca = { ...MARCA, id: "marca-2", nome: "Sol Café" };
    mockarQueries({
      marcas: { data: [MARCA, segunda] },
      repertorio: { data: undefined },
    });

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByLabelText("Escolher marca")).toBeInTheDocument();
    expect(
      screen.getByText("Este cliente tem mais de uma marca — escolha qual repertório ver acima."),
    ).toBeInTheDocument();
  });
});
