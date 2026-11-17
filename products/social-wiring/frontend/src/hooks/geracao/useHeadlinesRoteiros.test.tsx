/** useHeadlinesRoteiros: contract §6.9 query params, §6.8 origin, and the two loading signals. */
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { itemHR, origemCard } from "@/test/hrFixtures";
import { algumRoteiroEmAndamento, headlinesRoteirosQuery, useHeadlinesRoteiros, useOrigemDoCard } from "./useHeadlinesRoteiros";

afterEach(() => Object.values(api).forEach((m) => m.mockReset()));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

describe("headlinesRoteirosQuery", () => {
  it("sends only the filters that are set", () => {
    const p = new URLSearchParams(headlinesRoteirosQuery({ marcaId: "m1", q: " oi ", roteiroStatus: "sem_roteiro", estruturaId: "e1", offset: 20 }));
    expect(p.get("marca_id")).toBe("m1");
    expect(p.get("q")).toBe("oi");
    expect(p.get("roteiro_status")).toBe("sem_roteiro");
    expect(p.get("estrutura_id")).toBe("e1");
    expect(p.get("offset")).toBe("20");
    expect(p.get("limit")).toBe("20");
    expect(p.has("perfil_id")).toBe(false);
    expect(p.has("aprovacao")).toBe(false);
  });
});

describe("useHeadlinesRoteiros", () => {
  it("is idle without a marca", () => {
    const { result } = renderHook(() => useHeadlinesRoteiros({ marcaId: null }), { wrapper });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });

  it("shows the skeleton first, then the unwrapped items", async () => {
    api.get.mockResolvedValue({ data: { items: [itemHR()], total: 1 } });
    const { result } = renderHook(() => useHeadlinesRoteiros({ marcaId: "m1" }), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.total).toBe(1));
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get.mock.calls[0][0]).toContain("/api/media-creation/headlines-roteiros?marca_id=m1");
  });

  it("detects a roteiro still being produced", () => {
    expect(algumRoteiroEmAndamento([itemHR()])).toBe(false);
    const gerando = itemHR();
    gerando.roteiro = { ...gerando.roteiro!, status: "processando" };
    expect(algumRoteiroEmAndamento([gerando])).toBe(true);
    expect(algumRoteiroEmAndamento([itemHR({ roteiro: null })])).toBe(false);
  });
});

describe("useOrigemDoCard", () => {
  it("reads GET /esteira/posts/{id}/origem", async () => {
    api.get.mockResolvedValue({ data: origemCard() });
    const { result } = renderHook(() => useOrigemDoCard("p 1"), { wrapper });
    await waitFor(() => expect(result.current.data?.formato).toBe("stories"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p%201/origem");
  });
});
