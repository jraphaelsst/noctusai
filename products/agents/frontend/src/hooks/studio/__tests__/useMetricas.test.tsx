/** useMetricas — URLs/params per contract §14, loading signals, 403 not retried. */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { METRICAS_RESUMO, METRICAS_THREAD, METRICAS_TURNOS } from "@/pages/studio/tabs/__tests__/metricasFixtures";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});

import { useMetricasResumo, useMetricasThread, useMetricasThreads, useMetricasTurnos } from "../useMetricas";
import { studioKeys } from "../keys";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);
afterEach(() => vi.unstubAllGlobals());

describe("useMetricas", () => {
  it("resumo: sends the filter as query params; skeleton only until the first answer", async () => {
    const net = installFetch([{ method: "GET", path: "/api/studio/agents/julia/metricas", body: METRICAS_RESUMO }]);
    const { result } = renderHook(() => useMetricasResumo("julia", { origem: "eval", desde: "2026-11-01T00:00:00.000Z", org_id: "o1" }), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.showSkeleton).toBe(false);
    const q = net.calls[0].search;
    expect(q.get("origem")).toBe("eval");
    expect(q.get("desde")).toBe("2026-11-01T00:00:00.000Z");
    expect(q.get("org_id")).toBe("o1");
    expect(q.has("ate")).toBe(false);
  });

  it("turnos: pagina + limite", async () => {
    const net = installFetch([{ method: "GET", path: "/api/studio/agents/julia/metricas/turnos", body: METRICAS_TURNOS }]);
    const { result } = renderHook(() => useMetricasTurnos("julia", { origem: "canal" }, 2, 25), { wrapper });
    await waitFor(() => expect(result.current.data?.itens).toHaveLength(2));
    expect(net.calls[0].search.get("pagina")).toBe("2");
    expect(net.calls[0].search.get("limite")).toBe("25");
  });

  it("threads list and one thread (disabled without id)", async () => {
    const net = installFetch([
      { method: "GET", path: "/api/studio/agents/julia/metricas/threads", body: { total: 0, itens: [] } },
      { method: "GET", path: "/api/studio/agents/julia/metricas/threads/t-1", body: METRICAS_THREAD },
    ]);
    const a = renderHook(() => useMetricasThreads("julia", { origem: "canal" }), { wrapper });
    const b = renderHook(() => useMetricasThread("julia", null), { wrapper });
    const c = renderHook(() => useMetricasThread("julia", "t-1"), { wrapper });
    await waitFor(() => expect(a.result.current.data).toBeTruthy());
    await waitFor(() => expect(c.result.current.data?.turnos).toHaveLength(2));
    expect(b.result.current.data).toBeUndefined();
    expect(net.calls.map((x) => x.path)).not.toContain("/api/studio/agents/julia/metricas/threads/");
    expect(net.calls.find((x) => x.path.endsWith("/t-1"))?.search.get("origem")).toBe("todos");
  });

  it("403 surfaces as an error, once (no retry)", async () => {
    const net = installFetch([{ method: "GET", path: "/api/studio/agents/julia/metricas", status: 403, body: { detail: "Restrito", code: "forbidden" } }]);
    const { result } = renderHook(() => useMetricasResumo("julia", { origem: "canal" }), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { status: number }).status).toBe(403);
    expect(net.calls).toHaveLength(1);
  });

  it("keys are hierarchical under the agent", () => {
    expect(studioKeys.metricas("julia", {}).slice(0, 3)).toEqual(studioKeys.metricasAll("julia"));
    expect(studioKeys.metricasTurnos("julia", {}, 1, 25).slice(0, 3)).toEqual(studioKeys.agent("julia").concat("metricas"));
  });
});
