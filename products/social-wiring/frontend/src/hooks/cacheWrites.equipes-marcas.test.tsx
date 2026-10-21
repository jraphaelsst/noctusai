/**
 * Cache-write contract for the social-wiring hooks migrated off invalidate-only:
 * the cache already shows the change WHILE the request is still in flight
 * (optimistic) or the moment the answer arrives (commit) — never only after a refetch.
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const { mockGet, mockPost, mockPatch, mockPut, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockPut: vi.fn(),
  mockDelete: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
}));
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
}));

import { useDeleteMarca, useUpdateMarca, type Marca } from "@/hooks/useMarcas";
import { useAtualizarAgenteFinanceiro, useRemoverAgenteFinanceiro } from "@/hooks/useAgentesFinanceiros";
import { useAtualizarTreinamento, TREINAMENTOS_KEY } from "@/hooks/geracao/useTreinamentos";
import { useRevokeReceiverToken, RECEIVER_TOKENS_KEY } from "@/hooks/useReceiverTokens";
import { useOrdenarMembros, EQUIPES_KEY, type Equipe } from "@/hooks/useJuliaEquipes";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

beforeEach(() => {
  for (const m of [mockGet, mockPost, mockPatch, mockPut, mockDelete]) m.mockReset();
});

describe("social-wiring cache writes — marcas, agentes, treinamentos, tokens, equipes", () => {
  it("useUpdateMarca draws the edit in the list and the detail before the PATCH answers", async () => {
    const { qc, wrapper } = setup();
    const row = { id: "m1", name: "Antigo", slug: "a" } as Marca;
    qc.setQueryData(["sw", "clients"], [row, { id: "m2", name: "Outro", slug: "o" }]);
    qc.setQueryData(["sw", "clients", "detail", "m1"], row);
    const d = deferred<Marca>();
    mockPatch.mockReturnValue(d.promise);
    const { result } = renderHook(() => useUpdateMarca(), { wrapper });

    act(() => result.current.mutate({ id: "m1", name: "Novo" }));
    await waitFor(() =>
      expect((qc.getQueryData(["sw", "clients"]) as Marca[])[0].name).toBe("Novo"),
    );
    expect((qc.getQueryData(["sw", "clients", "detail", "m1"]) as Marca).name).toBe("Novo");

    await act(async () => d.resolve({ ...row, name: "Novo", slug: "novo" }));
    await waitFor(() => expect((qc.getQueryData(["sw", "clients", "detail", "m1"]) as Marca).slug).toBe("novo"));
  });

  it("useDeleteMarca removes the row on the click and restores it when the DELETE fails", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["sw", "clients"], [{ id: "m1" }, { id: "m2" }]);
    const d = deferred<void>();
    mockDelete.mockReturnValue(d.promise);
    const { result } = renderHook(() => useDeleteMarca(), { wrapper });

    act(() => result.current.mutate("m1"));
    await waitFor(() => expect(qc.getQueryData(["sw", "clients"])).toEqual([{ id: "m2" }]));

    // The write fails: the snapshot comes back (the settle refetch has no query to run here).
    await act(async () => {
      d.promise.catch(() => undefined);
    });
    mockDelete.mockReset();
    mockDelete.mockRejectedValue(new Error("boom"));
    qc.setQueryData(["sw", "clients"], [{ id: "m1" }, { id: "m2" }]);
    await act(async () => {
      await result.current.mutateAsync("m2").catch(() => undefined);
    });
    expect(qc.getQueryData(["sw", "clients"])).toEqual([{ id: "m1" }, { id: "m2" }]);
  });

  it("agentes financeiros: every cached list (active-only and full) is edited by one write", async () => {
    const { qc, wrapper } = setup();
    const ativos = [{ id: "a1", nome: "Caixa", ativo: true }];
    const todos = [{ id: "a1", nome: "Caixa", ativo: true }, { id: "a2", nome: "Itaú", ativo: false }];
    qc.setQueryData(["sw", "agentes-financeiros", { incluirInativos: false }], ativos);
    qc.setQueryData(["sw", "agentes-financeiros", { incluirInativos: true }], todos);
    mockPatch.mockReturnValue(new Promise(() => undefined));
    const upd = renderHook(() => useAtualizarAgenteFinanceiro(), { wrapper });
    act(() => upd.result.current.mutate({ id: "a1", patch: { nome: "Caixa Econômica" } }));
    await waitFor(() => {
      expect((qc.getQueryData(["sw", "agentes-financeiros", { incluirInativos: false }]) as typeof ativos)[0].nome).toBe("Caixa Econômica");
      expect((qc.getQueryData(["sw", "agentes-financeiros", { incluirInativos: true }]) as typeof todos)[0].nome).toBe("Caixa Econômica");
    });

    mockDelete.mockReturnValue(new Promise(() => undefined));
    const rem = renderHook(() => useRemoverAgenteFinanceiro(), { wrapper });
    act(() => rem.result.current.mutate("a2"));
    await waitFor(() =>
      expect(qc.getQueryData(["sw", "agentes-financeiros", { incluirInativos: true }])).toHaveLength(1),
    );
  });

  it("useAtualizarTreinamento patches the cached list before the PUT answers", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(TREINAMENTOS_KEY, [{ id: "t1", titulo: "A" }, { id: "t2", titulo: "B" }]);
    mockPut.mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(() => useAtualizarTreinamento(), { wrapper });
    act(() => result.current.mutate({ id: "t1", titulo: "A2" }));
    await waitFor(() =>
      expect(qc.getQueryData(TREINAMENTOS_KEY)).toEqual([{ id: "t1", titulo: "A2" }, { id: "t2", titulo: "B" }]),
    );
  });

  it("useRevokeReceiverToken marks the token revoked in every provider list on the click", async () => {
    const { qc, wrapper } = setup();
    const t = { id: "k1", provider: "olx", revoked_at: null };
    qc.setQueryData([...RECEIVER_TOKENS_KEY, "all"], [t]);
    qc.setQueryData([...RECEIVER_TOKENS_KEY, "olx"], [t]);
    mockDelete.mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(() => useRevokeReceiverToken(), { wrapper });
    act(() => result.current.mutate("k1"));
    await waitFor(() => {
      expect((qc.getQueryData([...RECEIVER_TOKENS_KEY, "all"]) as (typeof t)[])[0].revoked_at).not.toBeNull();
      expect((qc.getQueryData([...RECEIVER_TOKENS_KEY, "olx"]) as (typeof t)[])[0].revoked_at).not.toBeNull();
    });
  });

  it("useOrdenarMembros reorders the team's members to exactly the order sent", async () => {
    const { qc, wrapper } = setup();
    const eq = {
      id: "e1",
      nome: "Time",
      membros: [
        { user_id: "u1", nome: "A", ativo: true, ordem: 0 },
        { user_id: "u2", nome: "B", ativo: true, ordem: 1 },
      ],
    } as unknown as Equipe;
    qc.setQueryData(EQUIPES_KEY, [eq]);
    mockPut.mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(() => useOrdenarMembros(), { wrapper });
    act(() => result.current.mutate({ id: "e1", user_ids: ["u2", "u1"] }));
    await waitFor(() => {
      const [t] = qc.getQueryData(EQUIPES_KEY) as Equipe[];
      expect(t.membros.map((m) => [m.user_id, m.ordem])).toEqual([["u2", 0], ["u1", 1]]);
    });
  });
});
