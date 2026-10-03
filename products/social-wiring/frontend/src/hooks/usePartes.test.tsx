/**
 * useAdicionarParte — PF/PJ body goes to POST …/compradores untouched, and
 * `reemitirCertidoes` chains the §1.2 emission against the CREATED party.
 */
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";

const { mockGet, mockPost, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: vi.fn(), delete: vi.fn() },
}));

import { useAdicionarParte, useAtualizarContratoParte, useParteLookup } from "./usePartes";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  mockGet.mockReset();
  mockPost.mockReset();
});

const parteJ = { tipo_pessoa: "PJ", empresa_id: "emp-1", cliente_id: null, parte_id: "p1" };

describe("useAdicionarParte", () => {
  it("PJ: posts the body verbatim, no emission unless asked", async () => {
    mockPost.mockResolvedValueOnce(parteJ);
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ cnpj: "11222333000181", razao_social: "X", lado: "vendedor" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/c1/compradores", {
      cnpj: "11222333000181",
      razao_social: "X",
      lado: "vendedor",
    });
  });

  it("reemitirCertidoes: chains POST …/certidoes/partes/empresa/{id}/emissao with tipos:null", async () => {
    mockPost
      .mockResolvedValueOnce(parteJ)
      .mockResolvedValueOnce({ consulta_id: "q1", resultados: [] });
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ empresa_id: "emp-1", reemitirCertidoes: true, atendimento_id: "at-1" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // reemitirCertidoes is a FE flag — never sent to the strict body.
    expect(mockPost.mock.calls[0][1]).toEqual({ empresa_id: "emp-1", atendimento_id: "at-1" });
    expect(mockPost.mock.calls[1]).toEqual([
      "/api/clientes/c1/certidoes/partes/empresa/emp-1/emissao",
      { tipos: null, atendimento_id: "at-1" },
    ]);
    expect(result.current.data?.emissao?.consulta_id).toBe("q1");
  });

  it("PF reused: emission goes to kind 'pessoa' with the created cliente_id", async () => {
    mockPost
      .mockResolvedValueOnce({ tipo_pessoa: "PF", cliente_id: "cli-9", empresa_id: null })
      .mockResolvedValueOnce({ consulta_id: "q2", resultados: [] });
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ cliente_id: "cli-9", reemitirCertidoes: true });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost.mock.calls[1][0]).toBe("/api/clientes/c1/certidoes/partes/pessoa/cli-9/emissao");
  });

  it("add succeeds but emission fails: the failure is returned, not swallowed", async () => {
    mockPost
      .mockResolvedValueOnce(parteJ)
      .mockRejectedValueOnce(new Error("[422] Informe o CPF/CNPJ da parte antes de solicitar certidões."));
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ empresa_id: "emp-1", reemitirCertidoes: true });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.emissao).toBeNull();
    expect(result.current.data?.emissaoErro).toContain("Informe o CPF/CNPJ");
  });

  it("an add failure (409) rejects the mutation and never reaches emission", async () => {
    mockPost.mockRejectedValueOnce(new Error("[409] Esta pessoa já é parte deste atendimento."));
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ cliente_id: "cli-9", reemitirCertidoes: true });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockPost).toHaveBeenCalledTimes(1);
  });
});

describe("useParteLookup", () => {
  it("is off without a documento; on with one, with the query string", async () => {
    const { result, rerender } = renderHook(
      ({ doc }: { doc: string | null }) => useParteLookup("c1", doc, "at-1"),
      { wrapper: wrapper(), initialProps: { doc: null as string | null } },
    );
    expect(mockGet).not.toHaveBeenCalled();
    mockGet.mockResolvedValueOnce({ documento: "52998224725", encontrado: null });
    rerender({ doc: "52998224725" });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(mockGet).toHaveBeenCalledWith(
      "/api/clientes/c1/partes/lookup?documento=52998224725&atendimento_id=at-1",
    );
  });
});

describe("useAtualizarContratoParte (migration 193)", () => {
  it("PATCHes only the keys sent to …/compradores/{parte_id}/contrato", async () => {
    mockPatch.mockResolvedValueOnce({ id: "p1", representa_parte_id: "pj1" });
    const { result } = renderHook(() => useAtualizarContratoParte("c1"), { wrapper: wrapper() });
    result.current.mutate({ parteId: "p1", patch: { representa_parte_id: "pj1" } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/c1/compradores/p1/contrato", {
      representa_parte_id: "pj1",
    });
  });
});
