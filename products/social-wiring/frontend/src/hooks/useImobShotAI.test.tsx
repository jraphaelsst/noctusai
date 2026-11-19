/**
 * useImobShotAI -- request shapes against the contract, the cache write of `POST /lotes` (never invalidate-only: the
 * answer's card lands in the cached board before any refetch), and the 404 branch of the detail.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@noctusai/seed/infra", async () => ({ api: (await import("@/test/imobshotaiApiMock")).api }));

import { api, cardResumo, erroDoContrato, limparRotas, loteResumo, paginaDeCards, rota } from "@/test/imobshotaiApiMock";
import { imobKeys, useImobCard, useImobCards, useIniciarImobLote } from "./useImobShotAI";

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
const novoClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

beforeEach(limparRotas);
afterEach(cleanup);

describe("useImobCards", () => {
  it("sends etapa/q/page/page_size and upper-cases q", async () => {
    rota("GET", "/api/imobshotai/cards", () => paginaDeCards([cardResumo()]));
    const { result } = renderHook(() => useImobCards({ q: " one8 ", etapa: "fotos_enviadas", pageSize: 100 }), {
      wrapper: wrapper(novoClient()),
    });
    await waitFor(() => expect(result.current.cards).toHaveLength(1));
    expect(api.get).toHaveBeenCalledWith("/api/imobshotai/cards", { etapa: "fotos_enviadas", q: "ONE8", page: 1, page_size: 100 });
    expect(result.current.showSkeleton).toBe(false);
  });
});

describe("useImobCard", () => {
  it("404 card_nao_encontrado surfaces as the error (no retry storm)", async () => {
    rota("GET", "/api/imobshotai/cards/x", () => {
      throw erroDoContrato(404, "card_nao_encontrado", "Card não encontrado.");
    });
    const { result } = renderHook(() => useImobCard("x"), { wrapper: wrapper(novoClient()) });
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});

describe("useIniciarImobLote", () => {
  it("posts the body and writes the answered card into the cached unfiltered board (before any refetch)", async () => {
    const client = novoClient();
    const lista = imobKeys.list({ pageSize: 100 });
    client.setQueryData(lista, paginaDeCards([cardResumo({ id: "velho", imovel: { org_id: "o", codigo: "ONE1", titulo: null, bairro: null } })]));
    const filtrada = imobKeys.list({ q: "ZZ", pageSize: 100 });
    client.setQueryData(filtrada, paginaDeCards([]));
    rota("POST", "/api/imobshotai/lotes", () => ({ card: cardResumo({ id: "novo" }), lote: loteResumo() }));
    rota("GET", "/api/imobshotai/cards", () => new Promise(() => {})); // settle refetch never answers: only the write can explain the cache

    const { result } = renderHook(() => useIniciarImobLote(), { wrapper: wrapper(client) });
    await act(async () => {
      await result.current.mutateAsync({ imovel_codigo: "ONE8990", velocidade: "urgente" });
    });

    expect(api.post).toHaveBeenCalledWith("/api/imobshotai/lotes", { imovel_codigo: "ONE8990", velocidade: "urgente" });
    const depois = client.getQueryData<{ items: { id: string }[]; total: number }>(lista)!;
    expect(depois.items.map((c) => c.id)).toEqual(["novo", "velho"]);
    expect(depois.total).toBe(2);
    // a search for another ref does not hold this card
    expect(client.getQueryData<{ items: unknown[] }>(filtrada)!.items).toHaveLength(0);
  });
});
