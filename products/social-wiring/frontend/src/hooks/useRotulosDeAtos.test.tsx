/** `useRotulosDeAtos` — real hook against a fake API: ato_id -> "R-5", one request per extraction. */
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

import { useRotulosDeAtos } from "./useMatriculaEstrutura";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useRotulosDeAtos", () => {
  it("maps every act of every extraction to its rótulo, one request per distinct extraction", async () => {
    mockGet.mockImplementation(async (url: string) => ({
      data: {
        extracao_id: url,
        status: "concluida",
        codigo: "AP1",
        total: 1,
        atos: url.includes("ext-a")
          ? [{ id: "ato-1", rotulo: "R-5" }]
          : [{ id: "ato-2", rotulo: "AV-2" }],
      },
    }));
    const { result } = renderHook(() => useRotulosDeAtos(["ext-a", "ext-b", "ext-a", ""]), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.get("ato-2")).toBe("AV-2"));
    expect(result.current.get("ato-1")).toBe("R-5");
    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/extracoes/ext-a/atos");
  });

  it("is empty (and fires nothing) when there is no extraction to read", () => {
    mockGet.mockClear();
    const { result } = renderHook(() => useRotulosDeAtos([]), { wrapper: wrapper() });
    expect(result.current.size).toBe(0);
    expect(mockGet).not.toHaveBeenCalled();
  });
});
