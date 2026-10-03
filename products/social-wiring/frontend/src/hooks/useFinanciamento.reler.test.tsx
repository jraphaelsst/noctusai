/** Re-read mutations: right routes, and the negociação/financiamento queries refresh. */
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

import { useFinanciamentoDocumentoExtracao } from "./useFinanciamento";

function setup() {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, ...renderHook(() => useFinanciamentoDocumentoExtracao("c1"), { wrapper }) };
}

describe("useFinanciamentoDocumentoExtracao re-read", () => {
  it("reler POSTs …/documentos/{id}/reler and invalidates financiamento + negociação", async () => {
    mockPost.mockResolvedValue({});
    const { result, spy } = setup();
    await act(async () => { result.current.reler.mutate("d1"); });
    await waitFor(() => expect(result.current.reler.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/c1/financiamento/documentos/d1/reler", {});
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(["sw", "clientes", "c1", "financiamento"]));
    expect(keys).toContain(JSON.stringify(["sw", "clientes", "c1", "negociacao"]));
  });

  it("relerTodos POSTs the card-level route", async () => {
    mockPost.mockResolvedValue({ relidos: 2, sem_arquivo: 0, em_andamento: 0, erros: 0 });
    const { result } = setup();
    await act(async () => { result.current.relerTodos.mutate(); });
    await waitFor(() => expect(result.current.relerTodos.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/c1/negociacao/documentos/reler", {});
  });
});
