/**
 * F88 — Salvar on "Termos da negociação" must refresh the estruturada
 * aggregate (valor negociado) as well as the negociação row.
 */
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";

vi.mock("@noctusai/seed/infra", () => ({
  api: { patch: vi.fn(async () => ({ id: "n1" })), get: vi.fn() },
}));
vi.mock("@/hooks/useCardHub", () => ({ invalidateExtracaoDependentes: vi.fn() }));

import { useNegociacaoMutation } from "./useNegociacao";

describe("useNegociacaoMutation", () => {
  it("invalidates the estruturada cache after the PATCH", async () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);
    const { result } = renderHook(() => useNegociacaoMutation("c1"), { wrapper });
    await act(async () => {
      result.current.mutate({} as never);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({
      queryKey: ["sw", "clientes", "c1", "negociacao", "estruturada"],
    });
  });
});
