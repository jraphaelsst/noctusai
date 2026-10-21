/** useCondominios — query string + invalidation of the whole condominios tree. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { get, post, patch, del } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({ api: { get, post, patch, delete: del } }));

import {
  buscaCondominiosKey,
  useAcaoCondominio,
  useCondominioBusca,
  useCondominios,
  useCriarCondominio,
  useFundirCondominio,
} from "./useCondominios";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

beforeEach(() => {
  get.mockReset(); post.mockReset(); patch.mockReset(); del.mockReset();
});

describe("useCondominios", () => {
  it("sem filtros chama a rota base", async () => {
    get.mockResolvedValue({ items: [{ id: "a" }], total: 1 });
    const { wrapper } = setup();
    const { result } = renderHook(() => useCondominios(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([{ id: "a" }]));
    expect(get).toHaveBeenCalledWith("/api/condominios");
  });

  it("status, cidade e busca vão na query string", async () => {
    get.mockResolvedValue({ items: [], total: 0 });
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useCondominios({ status: "validado", cidade: "Cotia", q: " vila " }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("/api/condominios?status=validado&cidade=Cotia&q=vila");
  });
});

describe("mutations", () => {
  it("validar posta na rota certa e invalida a árvore", async () => {
    post.mockResolvedValue({});
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAcaoCondominio(), { wrapper });
    await result.current.mutateAsync({ id: "x", acao: "validar" });
    expect(post).toHaveBeenCalledWith("/api/condominios/x/validar", {});
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sw", "condominios"] });
  });

  it("fundir envia destino_id", async () => {
    post.mockResolvedValue({ aliases_movidos: 2 });
    const { wrapper } = setup();
    const { result } = renderHook(() => useFundirCondominio(), { wrapper });
    await result.current.mutateAsync({ id: "a", destinoId: "b" });
    expect(post).toHaveBeenCalledWith("/api/condominios/a/fundir", { destino_id: "b" });
  });
});

describe("imóvel-page picker (migration 300)", () => {
  it("busca encodes the term and stays idle while empty", async () => {
    get.mockResolvedValue({ items: [{ id: "c-1", nome: "Vila Verde" }], total: 1 });
    const { wrapper } = setup();
    const vazio = renderHook(() => useCondominioBusca("  "), { wrapper });
    expect(vazio.result.current.fetchStatus).toBe("idle");
    const { result } = renderHook(() => useCondominioBusca(" vila verde "), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([{ id: "c-1", nome: "Vila Verde" }]));
    expect(get).toHaveBeenCalledWith("/api/condominios/buscar?q=vila%20verde");
  });

  it("criar writes the server's answer into the typed term's search cache", async () => {
    const criado = {
      id: "c-9", nome: "Reserva", cidade: null, bairro: null, status_validacao: "sugerido", criado: true,
    };
    post.mockResolvedValue(criado);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(buscaCondominiosKey("Reserva"), [{ id: "c-1", nome: "Reserva Antiga" }]);
    const set = vi.spyOn(qc, "setQueryData");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCriarCondominio(), { wrapper });
    await result.current.mutateAsync({ nome: "Reserva" });
    expect(post).toHaveBeenCalledWith("/api/condominios", { nome: "Reserva" });
    expect(set).toHaveBeenCalledWith(buscaCondominiosKey("Reserva"), [
      { id: "c-9", nome: "Reserva", cidade: null, bairro: null, status_validacao: "sugerido" },
      { id: "c-1", nome: "Reserva Antiga" },
    ]);
  });
});
