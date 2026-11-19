/**
 * Configurações → Limites diários (geracao-contract.md §9.4.1): loading never lies, each limit shows its label,
 * default and ceiling, out-of-bounds input is refused before the request, a save sends only the dirty rows, a
 * refused save keeps the typed value and shows the server's sentence, "Restaurar padrão" sends null, members
 * read only. The save hook writes the answered list into the cache (real QueryClient).
 */
import React from "react";
import * as rtl from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { toast } from "sonner";
import { LimitesDiariosSection } from "./LimitesDiariosSection";
import { LIMITES_GERACAO_KEY, useSalvarLimitesGeracao } from "@/hooks/useLimitesGeracao";

const item = (over: Record<string, unknown> = {}) => ({
  chave: "roteiros_dia_usuario",
  rotulo: "Roteiros por pessoa",
  descricao: "Roteiros criados por cada pessoa",
  escopo: "usuario",
  valor: 20,
  padrao: 20,
  maximo: 200,
  personalizado: false,
  ...over,
});
const lista = (...items: ReturnType<typeof item>[]) => ({ items, total: items.length });

let qc: QueryClient;
function renderSection(canEdit = true) {
  return rtl.render(
    <QueryClientProvider client={qc}>
      <LimitesDiariosSection canEdit={canEdit} />
    </QueryClientProvider>,
  );
}
const input = () => rtl.screen.getByTestId("limite-roteiros_dia_usuario-input") as HTMLInputElement;
const salvar = () => rtl.screen.getByTestId("limites-salvar") as HTMLButtonElement;

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  Object.values(api).forEach((m) => m.mockReset());
  vi.clearAllMocks();
});

describe("LimitesDiariosSection", () => {
  it("shows a spinner, not an empty section, while the first load is pending", () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderSection();
    expect(rtl.screen.getByTestId("limites-carregando")).toBeTruthy();
    expect(rtl.screen.queryByText("Limites diários")).toBeNull();
  });

  it("a failed load offers a retry instead of an empty list", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    renderSection();
    await rtl.screen.findByTestId("limites-erro");
    expect(rtl.screen.getByTestId("limites-tentar-novamente")).toBeTruthy();
  });

  it("shows each limit with its label, default and ceiling", async () => {
    api.get.mockResolvedValue(lista(item({ valor: 50, personalizado: true })));
    renderSection();
    await rtl.screen.findByText("Roteiros por pessoa");
    expect(input().value).toBe("50");
    expect(rtl.screen.getByTestId("limite-roteiros_dia_usuario").textContent).toContain("Padrão: 20 · máximo: 200");
    expect(rtl.screen.getByTestId("limite-roteiros_dia_usuario-restaurar")).toBeTruthy();
  });

  it("saves only the edited rows and writes the answer into the screen", async () => {
    api.get.mockResolvedValue(
      lista(item(), item({ chave: "legendas_dia_usuario", rotulo: "Legendas por pessoa", valor: 40, padrao: 40, maximo: 400 })),
    );
    api.put.mockResolvedValue(lista(item({ valor: 60, personalizado: true }), item({ chave: "legendas_dia_usuario", rotulo: "Legendas por pessoa", valor: 40, padrao: 40, maximo: 400 })));
    renderSection();
    await rtl.screen.findByText("Roteiros por pessoa");
    expect(salvar().disabled).toBe(true);
    rtl.fireEvent.change(input(), { target: { value: "60" } });
    expect(rtl.screen.getByTestId("limites-nao-salvo")).toBeTruthy();
    rtl.fireEvent.click(salvar());
    await rtl.waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/settings/limites-geracao", { limites: { roteiros_dia_usuario: 60 } }));
    await rtl.waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(input().value).toBe("60");
    expect(rtl.screen.queryByTestId("limites-nao-salvo")).toBeNull();
    expect(rtl.screen.getByTestId("limite-roteiros_dia_usuario-restaurar")).toBeTruthy();
  });

  it.each([["0"], ["201"], ["abc"], ["2.5"]])("refuses %s before sending anything", async (valor) => {
    api.get.mockResolvedValue(lista(item()));
    renderSection();
    await rtl.screen.findByText("Roteiros por pessoa");
    rtl.fireEvent.change(input(), { target: { value: valor } });
    expect(rtl.screen.getByTestId("limite-roteiros_dia_usuario-erro")).toBeTruthy();
    expect(salvar().disabled).toBe(true);
    expect(api.put).not.toHaveBeenCalled();
  });

  it("a refused save keeps what was typed and shows the server's sentence", async () => {
    api.get.mockResolvedValue(lista(item()));
    api.put.mockRejectedValue(Object.assign(new Error("[422] x"), { status: 422, body: { error: { message: "Valor acima do máximo." } } }));
    renderSection();
    await rtl.screen.findByText("Roteiros por pessoa");
    rtl.fireEvent.change(input(), { target: { value: "150" } });
    rtl.fireEvent.click(salvar());
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Valor acima do máximo."));
    expect(input().value).toBe("150");
    expect(rtl.screen.getByTestId("limites-nao-salvo")).toBeTruthy();
  });

  it("Restaurar padrão sends null for that limit", async () => {
    api.get.mockResolvedValue(lista(item({ valor: 50, personalizado: true })));
    api.put.mockResolvedValue(lista(item()));
    renderSection();
    rtl.fireEvent.click(await rtl.screen.findByTestId("limite-roteiros_dia_usuario-restaurar"));
    await rtl.waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/settings/limites-geracao", { limites: { roteiros_dia_usuario: null } }));
    await rtl.waitFor(() => expect(input().value).toBe("20"));
    expect(rtl.screen.queryByTestId("limite-roteiros_dia_usuario-restaurar")).toBeNull();
  });

  it("a member sees the limits read-only", async () => {
    api.get.mockResolvedValue(lista(item({ personalizado: true })));
    renderSection(false);
    await rtl.screen.findByText("Roteiros por pessoa");
    expect(input().disabled).toBe(true);
    expect(rtl.screen.getByTestId("limites-somente-leitura")).toBeTruthy();
    expect(rtl.screen.queryByTestId("limites-salvar")).toBeNull();
    expect(rtl.screen.queryByTestId("limite-roteiros_dia_usuario-restaurar")).toBeNull();
  });
});

describe("useSalvarLimitesGeracao", () => {
  it("writes the answered list into the cache the moment the PUT answers", async () => {
    qc.setQueryData(LIMITES_GERACAO_KEY, lista(item()));
    const answered = lista(item({ valor: 70, personalizado: true }));
    api.put.mockResolvedValue(answered);
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = rtl.renderHook(() => useSalvarLimitesGeracao(), { wrapper });
    await rtl.act(() => result.current.mutateAsync({ roteiros_dia_usuario: 70 }));
    expect(qc.getQueryData(LIMITES_GERACAO_KEY)).toEqual(answered);
  });
});
