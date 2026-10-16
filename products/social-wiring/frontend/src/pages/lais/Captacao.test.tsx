/** Lais › Captação — day grouping, expand, registrar/descartar, filters, page size. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import LaisCaptacao from "./Captacao";
import { agruparPorDia } from "@/components/lais/captacao/agrupar";
import type { LaisCaptacao as Captacao } from "@/hooks/useLaisCaptacao";

const agora = new Date();
const ontem = new Date(agora.getTime() - 86400_000);
const C = (id: string, d: Date, status: Captacao["status"] = "nova"): Captacao => ({
  id, contato: { id: `ct-${id}`, nome: `Pessoa ${id}`, telefone: "5511999990000" },
  descricao: `Casa ${id}`, endereco: `Rua ${id}, 10`, operacao: "venda", status, created_at: d.toISOString(),
  imovel_id: status === "registrada" ? `im-${id}` : null,
});
const ITENS = [C("a", agora), C("b", ontem, "registrada")];

function setup(items: Captacao[] = ITENS, total = items.length) {
  api.get.mockResolvedValue({ data: { items, total } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter><ConfirmProvider><LaisCaptacao /></ConfirmProvider></MemoryRouter></QueryClientProvider>,
  );
}
const urls = () => api.get.mock.calls.map(([u]) => String(u));
beforeEach(() => { api.get.mockReset(); api.post.mockReset(); toast.success.mockReset(); toast.error.mockReset(); });
afterEach(cleanup);

describe("agruparPorDia", () => {
  it("groups Hoje / Ontem / date, newest first", () => {
    const g = agruparPorDia([...ITENS, C("c", new Date(2020, 0, 5))], agora);
    expect(g.map((x) => x.rotulo)).toEqual(["Hoje", "Ontem", "05/01/2020"]);
  });
});

describe("Captação page", () => {
  it("renders header, skeleton, then day groups", async () => {
    setup();
    expect(screen.getByText("Acompanhe as notificações de imóveis potencialmente captados.")).toBeTruthy();
    expect(screen.getByTestId("captacao-skeleton")).toBeTruthy();
    expect(await screen.findByText("Exibindo 2 captações")).toBeTruthy();
    expect(screen.getAllByTestId("captacao-grupo").map((s) => within(s).getByRole("heading").textContent)).toEqual(["Hoje", "Ontem"]);
    expect(screen.getAllByText("A Julia identificou uma potencial captação de imóvel")).toHaveLength(2);
  });

  it("empty and error states", async () => {
    setup([], 0);
    expect(await screen.findByTestId("captacao-vazio")).toBeTruthy();
    cleanup();
    api.get.mockRejectedValue(new Error("boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><MemoryRouter><ConfirmProvider><LaisCaptacao /></ConfirmProvider></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByTestId("captacao-erro")).toBeTruthy();
  });

  it("expands a card: details, conversation link, actions only for nova", async () => {
    setup();
    await screen.findByText("Exibindo 2 captações");
    fireEvent.click(screen.getAllByRole("button", { name: "Expandir" })[0]);
    const d = await screen.findByTestId("captacao-detalhe");
    expect(within(d).getByText("Casa a")).toBeTruthy();
    expect(within(d).getByText("Rua a, 10")).toBeTruthy();
    expect(within(d).getByText("venda")).toBeTruthy();
    expect(within(d).getByRole("link", { name: "Abrir conversa" }).getAttribute("href")).toBe("/lais/conversas?contato=ct-a");
    expect(within(d).getByRole("button", { name: "Registrar captação" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Expandir" }));
    const d2 = screen.getAllByTestId("captacao-detalhe")[1];
    expect(within(d2).queryByRole("button", { name: "Registrar captação" })).toBeNull();
    expect(within(d2).getByRole("link", { name: /Ver imóvel/ }).getAttribute("href")).toBe("/imoveis/im-b");
  });

  it("registrar posts, toasts success and refetches", async () => {
    setup();
    api.post.mockResolvedValue({ data: { imovel_id: "im-9" } });
    await screen.findByText("Exibindo 2 captações");
    fireEvent.click(screen.getAllByRole("button", { name: "Expandir" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Registrar captação" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/captacoes/a/registrar", {}));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(1));
  });

  it("registrar error toasts the server message", async () => {
    setup();
    api.post.mockRejectedValue({ body: { error: { message: "Já registrada" } } });
    await screen.findByText("Exibindo 2 captações");
    fireEvent.click(screen.getAllByRole("button", { name: "Expandir" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Registrar captação" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Já registrada"));
  });

  async function abrirDescartar() {
    await screen.findByText("Exibindo 2 captações");
    fireEvent.click(screen.getAllByRole("button", { name: "Expandir" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Descartar" }));
    await screen.findByText("Descartar captação?");
  }
  const confirmar = () =>
    fireEvent.click(screen.getAllByRole("button", { name: "Descartar" }).find((b) => !b.closest("[data-testid=captacao-card]"))!);

  it("descartar asks to confirm, then posts", async () => {
    setup();
    api.post.mockResolvedValue(undefined);
    await abrirDescartar();
    confirmar();
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/captacoes/a/descartar", {}));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Captação descartada."));
  });

  it("descartar error toasts; cancelling the confirm posts nothing", async () => {
    setup();
    api.post.mockRejectedValue(new Error("falhou"));
    await abrirDescartar();
    confirmar();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("falhou"));
    cleanup();
    api.post.mockClear();
    setup();
    await abrirDescartar();
    fireEvent.click(screen.getByRole("button", { name: /Cancelar|Voltar/ }));
    await waitFor(() => expect(screen.queryByText("Descartar captação?")).toBeNull());
    expect(api.post).not.toHaveBeenCalled();
  });

  it("filters drawer sends status and date range, resetting to page 1", async () => {
    setup();
    await screen.findByText("Exibindo 2 captações");
    fireEvent.click(screen.getByRole("button", { name: /Filtros/ }));
    fireEvent.click(await screen.findByLabelText("Novas"));
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-15" } });
    fireEvent.click(within(screen.getByTestId("captacao-filtro-drawer")).getByRole("button", { name: "Filtrar" }));
    await waitFor(() => expect(urls().some((u) => u.includes("status=nova") && u.includes("de=2026-10-01") && u.includes("ate=2026-10-15") && u.includes("page=1"))).toBe(true));
  });

  it("page size selector sends page_size and pagination moves pages", async () => {
    setup(ITENS, 30);
    await screen.findByText("Exibindo 30 captações");
    expect(urls()[0]).toContain("page_size=10");
    fireEvent.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(urls().some((u) => u.includes("page=2"))).toBe(true));
    fireEvent.change(screen.getByLabelText("Itens por página"), { target: { value: "20" } });
    await waitFor(() => expect(urls().some((u) => u.includes("page_size=20") && u.includes("page=1"))).toBe(true));
    expect(Array.from((screen.getByLabelText("Itens por página") as HTMLSelectElement).options).map((o) => o.value)).toEqual(["5", "10", "15", "20"]);
  });
});
