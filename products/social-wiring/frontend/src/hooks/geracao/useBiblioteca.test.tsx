/** useBiblioteca hits the §4.3 / §4.4 endpoints with the contract's params. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { FILTROS_VAZIOS } from "@/components/geracao/biblioteca/filtros";
import {
  perfisQuery,
  useAtualizarPerfil,
  useCriarReferencias,
  useGerarHeadlineViral,
  usePerfilBiblioteca,
  usePerfisBiblioteca,
  usePerfisMonitorados,
  useRemoverPerfil,
  useSolicitarPerfil,
  useVerificarPerfil,
  useViraisBiblioteca,
} from "./useBiblioteca";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  qc.clear();
  Object.values(api).forEach((f) => f.mockReset());
});

describe("useViraisBiblioteca", () => {
  it("serializes filters; a profile view forces ver_todos", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, filtro_automatico: false } });
    const { result } = renderHook(
      () =>
        useViraisBiblioteca("m1", {
          ...FILTROS_VAZIOS,
          nichos: [3, 5],
          perfilId: "p9",
          q: "obra",
          viewsMin: 100000,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const url = new URL(api.get.mock.calls[0][0], "http://x");
    expect(url.pathname).toBe("/api/media-creation/biblioteca/virais");
    expect(url.searchParams.get("marca_id")).toBe("m1");
    expect(url.searchParams.getAll("nichos")).toEqual(["3", "5"]);
    expect(url.searchParams.get("ver_todos")).toBe("true");
    expect(url.searchParams.get("perfil_id")).toBe("p9");
    expect(url.searchParams.get("buscar_em")).toBe("gancho");
    expect(url.searchParams.get("views_min")).toBe("100000");
    expect(url.searchParams.get("somente_virais")).toBe("true");
    expect(result.current.showSkeleton).toBe(false);
  });

  it("does not fetch without a marca", () => {
    renderHook(() => useViraisBiblioteca(null, FILTROS_VAZIOS), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("mutations", () => {
  it("references and headline batch use the contract bodies and invalidate geracao", async () => {
    const inv = vi.spyOn(qc, "invalidateQueries");
    api.post.mockResolvedValue({ data: { criadas: 1, ja_existentes: 0 } });
    const ref = renderHook(() => useCriarReferencias(), { wrapper });
    await ref.result.current.mutateAsync({ marca_id: "m1", modo: "video", viral_ids: ["v1"] });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/biblioteca/referencias", {
      marca_id: "m1",
      modo: "video",
      viral_ids: ["v1"],
    });
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao"] }));

    api.post.mockResolvedValue({ data: { id: "l1" } });
    const ger = renderHook(() => useGerarHeadlineViral(), { wrapper });
    await ger.result.current.mutateAsync({ marca_id: "m1", viral_id: "v1", assunto_livre: "x" });
    expect(api.post).toHaveBeenLastCalledWith("/api/media-creation/headlines/lotes", {
      marca_id: "m1",
      viral_id: "v1",
      assunto_livre: "x",
      origem: "biblioteca",
    });
  });
});

describe("marca-aware profile calls", () => {
  it("pool=minha_biblioteca replaces ver_todos", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, filtro_automatico: false, ingestao_ativa: true } });
    renderHook(() => useViraisBiblioteca("m1", { ...FILTROS_VAZIOS, pool: "minha_biblioteca" }), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const url = new URL(api.get.mock.calls[0][0], "http://x");
    expect(url.searchParams.get("pool")).toBe("minha_biblioteca");
    expect(url.searchParams.get("ver_todos")).toBeNull();
  });

  it("verificar sends marca_id", async () => {
    api.get.mockResolvedValue({ data: { status: "disponivel" } });
    renderHook(() => useVerificarPerfil("fulano", "m1"), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const url = new URL(api.get.mock.calls[0][0], "http://x");
    expect(url.pathname).toBe("/api/media-creation/biblioteca/perfis/verificar");
    expect(url.searchParams.get("marca_id")).toBe("m1");
  });

  it("delete is an admin write: no marca_id; apagar_estruturas only when the admin confirmed it", async () => {
    api.delete.mockResolvedValue(undefined);
    const r = renderHook(() => useRemoverPerfil(), { wrapper });
    await r.result.current.mutateAsync({ id: "p1", marca_id: "m1" });
    expect(api.delete).toHaveBeenLastCalledWith("/api/media-creation/biblioteca/perfis/p1");
    await r.result.current.mutateAsync({ id: "p1", apagar_estruturas: true });
    expect(api.delete).toHaveBeenLastCalledWith("/api/media-creation/biblioteca/perfis/p1?apagar_estruturas=true");
  });
});

describe("platform library profiles (estruturas-contract §4.2)", () => {
  const item = (over: Record<string, unknown> = {}) => ({ id: "p1", handle: "fulano", status: "ativo", monitorar: true, estruturas_total: 1, ...over });
  const KEY = (extra: unknown[]) => ["sw", "geracao", "biblioteca", "perfis", ...extra];

  it("lists library-wide, paged, as {items,total} (the array form is retired)", async () => {
    api.get.mockResolvedValue({ data: { items: [item()], total: 41 } });
    const { result } = renderHook(() => usePerfisBiblioteca({ marcaId: "m1", q: " ful ", limit: 30, offset: 30 }), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.total).toBe(41));
    expect(result.current.showSkeleton).toBe(false);
    const url = new URL(api.get.mock.calls[0][0], "http://x");
    expect(url.pathname).toBe("/api/media-creation/biblioteca/perfis");
    expect(Object.fromEntries(url.searchParams)).toEqual({ marca_id: "m1", q: "ful", limit: "30", offset: "30" });
    expect(perfisQuery({})).toBe("limit=30&offset=0");
  });

  it("usePerfisMonitorados still hands pickers a bare array (first 50) over the same endpoint", async () => {
    api.get.mockResolvedValue({ data: { items: [item(), item({ id: "p2" })], total: 2 } });
    const { result } = renderHook(() => usePerfisMonitorados(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(2));
    expect(new URL(api.get.mock.calls[0][0], "http://x").searchParams.get("limit")).toBe("50");
  });

  it("profile detail: GET /perfis/{id}", async () => {
    api.get.mockResolvedValue({ data: item({ estruturas_total: 7 }) });
    const { result } = renderHook(() => usePerfilBiblioteca("p1"), { wrapper });
    await waitFor(() => expect(result.current.data?.estruturas_total).toBe(7));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/biblioteca/perfis/p1");
    renderHook(() => usePerfilBiblioteca(null), { wrapper });
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it("adding a profile is an admin write without marca_id, and it heads the unfiltered first page", async () => {
    qc.setQueryData(KEY([null, "", 30, 0]), { items: [item({ id: "p0" })], total: 1 });
    qc.setQueryData(KEY(["m1", "ful", 30, 0]), { items: [], total: 0 });
    api.post.mockResolvedValue({ data: item({ id: "pnovo", handle: "novo" }) });
    const { result } = renderHook(() => useSolicitarPerfil(), { wrapper });
    await result.current.mutateAsync({ marca_id: "m1", handle: "novo", conta_descoberta_id: "c1" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/biblioteca/perfis", { handle: "novo", conta_descoberta_id: "c1" });
    const page = qc.getQueryData<{ items: { id: string }[]; total: number }>(KEY([null, "", 30, 0]));
    expect(page?.items.map((i) => i.id)).toEqual(["pnovo", "p0"]);
    expect(page?.total).toBe(2);
    // a filtered page is not guessed at — it converges on the settle
    expect(qc.getQueryData<{ items: unknown[] }>(KEY(["m1", "ful", 30, 0]))?.items).toHaveLength(0);
  });

  it("PATCH carries status / monitorar / nome (no id) and patches the list row and the detail", async () => {
    qc.setQueryData(KEY([null, "", 30, 0]), { items: [item()], total: 1 });
    qc.setQueryData(["sw", "geracao", "biblioteca", "perfil", "p1", null], item());
    api.patch.mockResolvedValue({ data: item({ monitorar: false }) });
    const { result } = renderHook(() => useAtualizarPerfil(), { wrapper });
    await result.current.mutateAsync({ id: "p1", monitorar: false });
    expect(api.patch).toHaveBeenCalledWith("/api/media-creation/biblioteca/perfis/p1", { monitorar: false });
    expect(qc.getQueryData<{ items: { monitorar: boolean }[] }>(KEY([null, "", 30, 0]))?.items[0]?.monitorar).toBe(false);
    expect(qc.getQueryData<{ monitorar: boolean; estruturas_total: number }>(["sw", "geracao", "biblioteca", "perfil", "p1", null])).toMatchObject({ monitorar: false, estruturas_total: 1 });
  });
});
