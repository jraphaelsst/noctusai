/** Offset paging: loads past 100 rows without any request exceeding limit 100. */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const get = vi.fn();
vi.mock("@noctusai/seed/infra", () => ({ api: { get: (...a: any[]) => get(...a) } }));
vi.mock("@/hooks/useCerebro", () => ({ CEREBRO_KEY: ["sw", "cerebro"], POLL_MS: 3000 }));

const TOTAL = 130;

describe("useExtracoes paging", () => {
  it("never requests limit > 100 and stops at total", async () => {
    get.mockImplementation(async (url: string) => {
      const p = new URL(url, "http://x").searchParams;
      const limit = Number(p.get("limit"));
      const offset = Number(p.get("offset"));
      const items = Array.from({ length: Math.max(0, Math.min(limit, TOTAL - offset)) }, (_, i) => ({
        id: `id-${offset + i}`,
        status: "ready",
        targets: [],
      }));
      return { success: true, data: { items, total: TOTAL } };
    });
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const React = (await import("react")).default;
    const { renderHook, waitFor, act } = await import("@testing-library/react");
    const { useExtracoes } = await import("./useExtracoes");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: any) => React.createElement(QueryClientProvider, { client }, children);
    const { result } = renderHook(() => useExtracoes("m1", ""), { wrapper });

    await waitFor(() => expect(result.current.data?.items.length).toBe(20));
    for (let n = 20; n < TOTAL; n += 20) {
      expect(result.current.hasNextPage).toBe(true);
      await act(async () => {
        await result.current.fetchNextPage();
      });
      await waitFor(() => expect(result.current.data?.items.length).toBe(Math.min(n + 20, TOTAL)));
    }
    expect(result.current.data?.items.length).toBe(TOTAL);
    expect(result.current.hasNextPage).toBe(false);
    const limits = get.mock.calls.map((c) => Number(new URL(c[0], "http://x").searchParams.get("limit")));
    expect(Math.max(...limits)).toBeLessThanOrEqual(100);
    const offsets = get.mock.calls.map((c) => Number(new URL(c[0], "http://x").searchParams.get("offset")));
    expect(offsets).toEqual([0, 20, 40, 60, 80, 100, 120]);
  });
});
