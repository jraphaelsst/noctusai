/**
 * Seed-op adoption (cache-writes v1.4.0): idKey rows, `pageOps.add`, `insertSorted`, `infiniteOps`,
 * and key-aware prefix creates (`predicate` / the `queryKey` argument). Each case asserts the cache
 * the moment the answer arrives (or while the request is in flight) — never only after a refetch.
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

import { useAdicionarParte } from "@/hooks/usePartes";
import { useCreateMarca, type Marca } from "@/hooks/useMarcas";
import { useCreateFolder } from "@/hooks/useN8nFolders";
import { useMailchimpSegmentMutations } from "@/hooks/useMailchimpSegments";
import { useEmCampaignMutations, useEmContactMutations } from "@/hooks/useEmailMarketing";
import { useAprovarAssunto, useEsvaziarAssuntos, ASSUNTOS_KEY } from "@/hooks/useAssuntosVirais";
import { useAcaoEmMassa, useZerarPesquisa, PESQUISA_KEY } from "@/hooks/usePesquisa";
import { useCriarExtracao, useExcluirExtracao } from "@/hooks/useExtracoes";
import { useCriarConversa, CHAT_KEY } from "@/hooks/geracao/useChat";
import { CEREBRO_KEY } from "@/hooks/useCerebro";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  // Refetches have no query function here; the settle must never be what the assertions depend on.
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

beforeEach(() => {
  for (const m of [mockGet, mockPost, mockPatch, mockPut, mockDelete]) m.mockReset();
});

const infinite = (...pages: unknown[]) => ({ pages, pageParams: pages.map((_, i) => i) });

describe("idKey / pageOps.add", () => {
  it("useAdicionarParte adds the party by parte_id (total moves) and isPending ends at the commit", async () => {
    const { qc, wrapper } = setup();
    const key = ["sw", "clientes", "c1", "partes", "all"];
    qc.setQueryData(key, { items: [{ parte_id: "p0" }], total: 1 });
    const d = deferred<unknown>();
    mockPost.mockReturnValue(d.promise);
    const { result } = renderHook(() => useAdicionarParte("c1"), { wrapper });

    act(() => result.current.mutate({ lado: "comprador" } as never));
    await act(async () => d.resolve({ parte_id: "p1", tipo_pessoa: "PF", cliente_id: "x" }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(key)).toEqual({
      items: [{ parte_id: "p0" }, { parte_id: "p1", tipo_pessoa: "PF", cliente_id: "x" }],
      total: 2,
    });
  });
});

describe("insertSorted", () => {
  it("useCreateMarca lands the new marca where the name order puts it", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["sw", "clients"], [{ id: "a", name: "Ana" }, { id: "c", name: "Carla" }] as Marca[]);
    mockPost.mockResolvedValue({ id: "b", name: "Bia" });
    const { result } = renderHook(() => useCreateMarca(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ slug: "bia", name: "Bia" });
    });
    expect((qc.getQueryData(["sw", "clients"]) as Marca[]).map((m) => m.id)).toEqual(["a", "b", "c"]);
  });
});

describe("key-aware prefix creates", () => {
  it("useCreateFolder commits into the account's lists only, never another account's", async () => {
    const { qc, wrapper } = setup();
    const empty = () => ({ workflows: [], folders: [{ id: "f0", name: "Zero", parent_id: null, position: 0 }] });
    qc.setQueryData(["sw", "n8n", "workflows", "acc1", "client", false], empty());
    qc.setQueryData(["sw", "n8n", "workflows", "acc1", "all", true], empty());
    qc.setQueryData(["sw", "n8n", "workflows", "acc2", "client", false], empty());
    mockPost.mockResolvedValue({ id: "f1", name: "Nova", parent_id: null, position: 1 });
    const { result } = renderHook(() => useCreateFolder(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ body: { name: "Nova" }, accountId: "acc1" });
    });
    const folders = (k: unknown[]) => (qc.getQueryData(k) as { folders: { id: string }[] }).folders.map((f) => f.id);
    expect(folders(["sw", "n8n", "workflows", "acc1", "client", false])).toEqual(["f0", "f1"]);
    expect(folders(["sw", "n8n", "workflows", "acc1", "all", true])).toEqual(["f0", "f1"]);
    expect(folders(["sw", "n8n", "workflows", "acc2", "client", false])).toEqual(["f0"]);
  });

  it("Mailchimp segment create goes to first-page lists only (not offset pages, not a segment's members)", async () => {
    const { qc, wrapper } = setup();
    const page = () => ({ items: [{ id: 1 }], total: 1 });
    qc.setQueryData(["mailchimp", "segments", undefined], page());
    qc.setQueryData(["mailchimp", "segments", { count: 10 }], page());
    qc.setQueryData(["mailchimp", "segments", { count: 10, offset: 10 }], page());
    qc.setQueryData(["mailchimp", "segments", 1, "members", undefined], page());
    mockPost.mockResolvedValue({ id: 2, name: "Novo" });
    const { result } = renderHook(() => useMailchimpSegmentMutations(), { wrapper });
    await act(async () => {
      await result.current.create.mutateAsync({ name: "Novo" } as never);
    });
    const ids = (k: unknown[]) => (qc.getQueryData(k) as { items: { id: number }[] }).items.map((i) => i.id);
    expect(ids(["mailchimp", "segments", undefined])).toEqual([1, 2]);
    expect(ids(["mailchimp", "segments", { count: 10 }])).toEqual([1, 2]);
    expect(ids(["mailchimp", "segments", { count: 10, offset: 10 }])).toEqual([1]);
    expect(ids(["mailchimp", "segments", 1, "members", undefined])).toEqual([1]);
  });

  it("email campaign create reaches the unfiltered list and its own status list only", async () => {
    const { qc, wrapper } = setup();
    const K = ["sw", "email-marketing", "campaigns"];
    qc.setQueryData([...K, "all"], [{ id: "c0", status: "enviada" }]);
    qc.setQueryData([...K, "rascunho"], []);
    qc.setQueryData([...K, "enviada"], [{ id: "c0", status: "enviada" }]);
    mockPost.mockResolvedValue({ data: { id: "c1", status: "rascunho" } });
    const { result } = renderHook(() => useEmCampaignMutations(), { wrapper });
    await act(async () => {
      await result.current.create.mutateAsync({ nome: "x" } as never);
    });
    const ids = (k: string) => (qc.getQueryData([...K, k]) as { id: string }[]).map((r) => r.id);
    expect(ids("all")).toEqual(["c1", "c0"]);
    expect(ids("rascunho")).toEqual(["c1"]);
    expect(ids("enviada")).toEqual(["c0"]);
  });

  it("email contact create skips search lists and other status lists", async () => {
    const { qc, wrapper } = setup();
    const K = ["sw", "email-marketing", "contacts"];
    qc.setQueryData([...K, "all", ""], []);
    qc.setQueryData([...K, "ativo", ""], []);
    qc.setQueryData([...K, "descadastrado", ""], []);
    qc.setQueryData([...K, "all", "ana"], []);
    mockPost.mockResolvedValue({ data: { id: "k1", status: "ativo", email: "a@b.c" } });
    const { result } = renderHook(() => useEmContactMutations(), { wrapper });
    await act(async () => {
      await result.current.create.mutateAsync({ email: "a@b.c" });
    });
    const len = (a: string, b: string) => (qc.getQueryData([...K, a, b]) as unknown[]).length;
    expect([len("all", ""), len("ativo", ""), len("descadastrado", ""), len("all", "ana")]).toEqual([1, 1, 0, 0]);
  });
});

describe("infiniteOps", () => {
  const lista = (ids: string[], status: string) => ({
    items: ids.map((id) => ({ id, status })),
    total: ids.length,
  });

  it("useAprovarAssunto takes the row off the pending lists at once, before the POST answers", async () => {
    const { qc, wrapper } = setup();
    const pending = [...ASSUNTOS_KEY, "list", "m1", "pending", "plays"];
    const approved = [...ASSUNTOS_KEY, "list", "m1", "approved", "plays"];
    qc.setQueryData(pending, infinite(lista(["a1", "a2"], "pending")));
    qc.setQueryData(approved, infinite(lista(["z"], "approved")));
    const d = deferred<unknown>();
    mockPost.mockReturnValue(d.promise);
    const { result } = renderHook(() => useAprovarAssunto(), { wrapper });

    act(() => result.current.mutate("a1"));
    await waitFor(() =>
      expect((qc.getQueryData(pending) as { pages: { items: unknown[] }[] }).pages[0].items).toHaveLength(1),
    );
    expect((qc.getQueryData(approved) as { pages: { items: unknown[] }[] }).pages[0].items).toHaveLength(1);
    await act(async () => d.resolve({ data: { id: "a1", status: "approved" } }));
  });

  it("useEsvaziarAssuntos blanks that marca+status lists in every sort, nothing else", async () => {
    const { qc, wrapper } = setup();
    const a = [...ASSUNTOS_KEY, "list", "m1", "pending", "plays"];
    const b = [...ASSUNTOS_KEY, "list", "m1", "pending", "recent"];
    const c = [...ASSUNTOS_KEY, "list", "m1", "approved", "plays"];
    const other = [...ASSUNTOS_KEY, "list", "m2", "pending", "plays"];
    for (const k of [a, b, c, other]) qc.setQueryData(k, infinite(lista(["x"], "pending")));
    const d = deferred<unknown>();
    mockPost.mockReturnValue(d.promise);
    const { result } = renderHook(() => useEsvaziarAssuntos(), { wrapper });
    act(() => result.current.mutate({ marca_id: "m1", status: "pending" }));
    const n = (k: unknown[]) => (qc.getQueryData(k) as { pages: { items: unknown[] }[] }).pages[0].items.length;
    await waitFor(() => expect(n(a)).toBe(0));
    expect([n(b), n(c), n(other)]).toEqual([0, 1, 1]);
    await act(async () => d.resolve({ data: { deleted: 1 } }));
  });

  it("pesquisa bulk approve only touches pending lists; zerar blanks the marca's lists", async () => {
    const { qc, wrapper } = setup();
    const p = [...PESQUISA_KEY, "items", "m1", "pending", null, "recent", 20];
    const ap = [...PESQUISA_KEY, "items", "m1", "approved", null, "recent", 20];
    qc.setQueryData(p, infinite(lista(["i1", "i2"], "pending")));
    qc.setQueryData(ap, infinite(lista(["i1"], "approved")));
    const d = deferred<unknown>();
    mockPost.mockReturnValue(d.promise);
    const { result } = renderHook(() => ({ bulk: useAcaoEmMassa(), zerar: useZerarPesquisa() }), { wrapper });
    act(() => result.current.bulk.mutate({ marca_id: "m1", action: "approve", ids: ["i1"] }));
    const n = (k: unknown[]) => (qc.getQueryData(k) as { pages: { items: unknown[] }[] }).pages[0].items.length;
    await waitFor(() => expect(n(p)).toBe(1));
    expect(n(ap)).toBe(1);
    await act(async () => d.resolve({ data: { affected: 1 } }));

    const d2 = deferred<unknown>();
    mockPost.mockReturnValue(d2.promise);
    act(() => result.current.zerar.mutate("m1"));
    await waitFor(() => expect(n(ap)).toBe(0));
    expect(n(p)).toBe(0);
    await act(async () => d2.resolve({ data: { deleted: 2 } }));
  });

  it("useCriarExtracao prepends into page 1 of the marca's unfiltered infinite list; delete removes it", async () => {
    const { qc, wrapper } = setup();
    const key = [...CEREBRO_KEY, "m1", "extracoes", { q: "" }];
    qc.setQueryData(key, infinite({ items: [{ id: "e0" }], total: 1 }));
    mockPost.mockResolvedValue({ data: { id: "e1", name: "Nova" } });
    const { result } = renderHook(() => ({ criar: useCriarExtracao(), excluir: useExcluirExtracao() }), { wrapper });
    await act(async () => {
      await result.current.criar.mutateAsync({ marca_id: "m1", name: "Nova", brain_ids: [], text: "t" });
    });
    const ids = () => (qc.getQueryData(key) as { pages: { items: { id: string }[] }[] }).pages[0].items.map((i) => i.id);
    expect(ids()).toEqual(["e1", "e0"]);
    const d = deferred<void>();
    mockDelete.mockReturnValue(d.promise);
    act(() => result.current.excluir.mutate("e0"));
    await waitFor(() => expect(ids()).toEqual(["e1"]));
    await act(async () => d.resolve());
  });

  it("totals move on EVERY loaded page, so a list reading the last page's total stays right", async () => {
    const { qc, wrapper } = setup();
    const key = [...CEREBRO_KEY, "m1", "extracoes", { q: "" }];
    qc.setQueryData(key, infinite({ items: [{ id: "e0" }], total: 2 }, { items: [{ id: "e9" }], total: 2 }));
    mockPost.mockResolvedValue({ data: { id: "e1", name: "Nova" } });
    const { result } = renderHook(() => ({ criar: useCriarExtracao(), excluir: useExcluirExtracao() }), { wrapper });
    const totals = () => (qc.getQueryData(key) as { pages: { total: number }[] }).pages.map((p) => p.total);
    await act(async () => {
      await result.current.criar.mutateAsync({ marca_id: "m1", name: "Nova", brain_ids: [], text: "t" });
    });
    expect(totals()).toEqual([3, 3]);
    const d = deferred<void>();
    mockDelete.mockReturnValue(d.promise);
    act(() => result.current.excluir.mutate("e9"));
    await waitFor(() => expect(totals()).toEqual([2, 2]));
    await act(async () => d.resolve());
  });

  it("useCriarConversa heads the first page of the conversas infinite list", async () => {
    const { qc, wrapper } = setup();
    const k = [...CHAT_KEY, "conversas", "m1", "roteirista"];
    qc.setQueryData(k, infinite({ items: [{ id: "c0" }], tem_mais: false }));
    mockPost.mockResolvedValue({ data: { id: "c1" } });
    const { result } = renderHook(() => useCriarConversa(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ marca_id: "m1", agente: "roteirista" as never });
    });
    expect((qc.getQueryData(k) as { pages: { items: { id: string }[] }[] }).pages[0].items.map((i) => i.id)).toEqual([
      "c1",
      "c0",
    ]);
  });
});
