/**
 * RepertorioSidebar — render-level regression test for the refetch-unmount
 * bug (fleet audit, 2026-08-31). This IS the user's literal complaint: the
 * sidebar is "ambient chrome on a work screen" (see the module docstring)
 * that must never blank out — but `useAtualizarMarca` invalidates
 * `["igig","repertorio"]` on EVERY field save, and the old
 * `isPending || isFetching` gate replaced the whole card with
 * "Carregando repertório…" on every one of those saves.
 *
 * Mocks `@tanstack/react-query` itself so the real `useRepertorio()` runs —
 * this is not a stub of the hook's return shape.
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

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn();
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useQuery } from "@tanstack/react-query";
import { RepertorioSidebar } from "../RepertorioSidebar";
import type { Repertorio } from "@/hooks/useMarca";

const mockUseQuery = vi.mocked(useQuery);

const REPERTORIO: Repertorio = {
  cliente_nome: "Padaria Sol",
  marca_nome: "Sol Pães",
  logo_url: null,
  paleta: [{ nome: "primária", hex: "#f97316" }],
  tom_de_voz: "Caloroso e direto.",
  termos_proibidos: null,
  nivel_formalidade: "informal",
  linhas_editoriais: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RepertorioSidebar — persistent chrome must not blank on a background refetch", () => {
  it("keeps the tom de voz on screen while `useAtualizarMarca` invalidates it (isFetching, data present)", () => {
    mockUseQuery.mockReturnValue({
      data: REPERTORIO,
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Caloroso e direto.")).toBeInTheDocument();
    expect(screen.queryByText("Carregando repertório…")).not.toBeInTheDocument();
  });

  it("shows the loading copy only on genuine first load (no data yet)", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Carregando repertório…")).toBeInTheDocument();
    expect(screen.queryByText(/Sol Pães/)).not.toBeInTheDocument();
  });

  it("degrades quietly to 'indisponível' — never an error banner — once settled with no repertório", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);

    render(<RepertorioSidebar clienteId="cliente-1" />);

    expect(screen.getByText("Repertório indisponível.")).toBeInTheDocument();
  });
});
