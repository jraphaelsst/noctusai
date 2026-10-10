/** useBiblioteca hits the §4.3 / §4.4 endpoints with the contract's params. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { FILTROS_VAZIOS } from "@/components/geracao/biblioteca/filtros";
import {
  useCriarReferencias,
  useGerarHeadlineViral,
  useRemoverPerfil,
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

  it("delete sends marca_id", async () => {
    api.delete.mockResolvedValue(undefined);
    const r = renderHook(() => useRemoverPerfil(), { wrapper });
    await r.result.current.mutateAsync({ id: "p1", marca_id: "m1" });
    expect(api.delete).toHaveBeenCalledWith("/api/media-creation/biblioteca/perfis/p1?marca_id=m1");
  });
});
