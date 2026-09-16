/**
 * useMembros hook tests — community-m1-contract.md §Endpoints#Membros.
 *
 * Asserts against the contract's own shapes verbatim: `{items,total,resumo}`
 * for the list, the dedicated `/status` endpoint for status changes (not a
 * PATCH field edit), and `DELETE` for cancel.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: mockDelete },
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const MEMBRO = {
  id: "m-1",
  nome: "Ana",
  email: "ana@x.com",
  telefone: "+5511999999999",
  status: "ativo" as const,
  plano_id: "p-1",
  plano_nome: "Círculo",
  origem: "aplicacao" as const,
  tags: ["fundadora"],
  user_id: null,
  observacoes: null,
  entrou_em: "2026-09-16T20:00:00+00:00",
  created_at: "2026-09-16T20:00:00+00:00",
  updated_at: "2026-09-16T20:00:00+00:00",
};

const RESUMO = { pendente: 1, ativo: 10, atrasado: 2, pausado: 0, cancelado: 3 };

beforeEach(() => vi.clearAllMocks());

describe("useMembros", () => {
  it("fetches /api/membros carrying items+total+resumo", async () => {
    mockGet.mockResolvedValue({ items: [MEMBRO], total: 1, resumo: RESUMO });
    const { useMembros } = await import("@/hooks/useMembros");
    const { result } = renderHook(() => useMembros({ status: "ativo,atrasado" }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/membros", { status: "ativo,atrasado" });
    expect(result.current.data?.resumo).toEqual(RESUMO);
    expect(result.current.data?.items[0].plano_nome).toBe("Círculo");
  });
});

describe("useCreateMembro", () => {
  it("posts to /api/membros", async () => {
    mockPost.mockResolvedValue(MEMBRO);
    const { useCreateMembro } = await import("@/hooks/useMembros");
    const { result } = renderHook(() => useCreateMembro(), { wrapper: wrapper() });

    result.current.mutate({ nome: "Ana", email: "ana@x.com", origem: "convite" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/membros", { nome: "Ana", email: "ana@x.com", origem: "convite" });
  });
});

describe("useChangeMembroStatus", () => {
  it("posts to /api/membros/{id}/status — a dedicated endpoint, never a PATCH field edit", async () => {
    mockPost.mockResolvedValue({ ...MEMBRO, status: "pausado" });
    const { useChangeMembroStatus } = await import("@/hooks/useMembros");
    const { result } = renderHook(() => useChangeMembroStatus(), { wrapper: wrapper() });

    result.current.mutate({ id: "m-1", status: "pausado", motivo: "férias" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/membros/m-1/status", { status: "pausado", motivo: "férias" });
    expect(mockPatch).not.toHaveBeenCalled();
  });
});

describe("useCancelMembro", () => {
  it("DELETEs /api/membros/{id} — sets status=cancelado, never a hard delete", async () => {
    mockDelete.mockResolvedValue(undefined);
    const { useCancelMembro } = await import("@/hooks/useMembros");
    const { result } = renderHook(() => useCancelMembro(), { wrapper: wrapper() });

    result.current.mutate("m-1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith("/api/membros/m-1");
  });
});
