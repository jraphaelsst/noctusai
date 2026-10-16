/** Lais › Notificações — day grouping, filters, prefs toggle, mark read. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import LaisNotificacoes from "./Notificacoes";
import { agruparPorDia } from "@/components/lais/notificacoes/agrupar";

const agora = new Date();
const ontem = new Date(agora.getTime() - 86400_000);
const N = (id: string, tipo: string, d: Date, is_read = false) =>
  ({ id, tipo, titulo: `texto ${id}`, is_read, created_at: d.toISOString() });
const ITENS = [N("a", "novo_lead", agora), N("b", "captacao", ontem, true)];

function setup(url = "/lais/notificacoes", items = ITENS, prefs: unknown[] = []) {
  api.get.mockImplementation((u: string) =>
    u.includes("/preferencias") ? Promise.resolve({ data: prefs })
      : Promise.resolve({ data: { items, total: items.length, nao_lidas: items.filter((i) => !i.is_read).length } }));
  api.post.mockResolvedValue(undefined);
  api.put.mockImplementation((_u: string, b: unknown) => Promise.resolve({ data: b }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}><LaisNotificacoes /></MemoryRouter></QueryClientProvider>,
  );
}
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("agruparPorDia", () => {
  it("groups Hoje / Ontem / date, newest first", () => {
    const g = agruparPorDia([...ITENS, N("c", "novo_lead", new Date(2020, 0, 5))], agora);
    expect(g.map((x) => x.rotulo)).toEqual(["Hoje", "Ontem", "05/01/2020"]);
  });
});

describe("Notificações page", () => {
  it("renders title, count and grouped cards", async () => {
    setup();
    expect(screen.getByTestId("notif-skeleton")).toBeTruthy();
    expect(await screen.findByText("Exibindo 2 notificações")).toBeTruthy();
    expect(screen.getAllByTestId("notif-grupo").map((s) => within(s).getByRole("heading").textContent)).toEqual(["Hoje", "Ontem"]);
    expect(screen.getByText("COMERCIAL")).toBeTruthy();
  });

  it("empty state", async () => {
    setup("/lais/notificacoes", []);
    expect(await screen.findByTestId("notif-vazio")).toBeTruthy();
  });

  it("applies tipo from the URL and via the filter drawer", async () => {
    setup("/lais/notificacoes?tipo=captacao");
    await screen.findByText("Exibindo 2 notificações");
    expect(api.get.mock.calls.some(([u]) => String(u).includes("/api/lais/notificacoes?") && String(u).includes("tipo=captacao"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Filtrar/ }));
    fireEvent.click(await screen.findByLabelText("Compra"));
    fireEvent.click(screen.getByLabelText("Novo lead gerado"));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Filtrar" }));
    await waitFor(() => expect(api.get.mock.calls.some(([u]) => String(u).includes("operacao=compra") && String(u).includes("tipo=novo_lead"))).toBe(true));
  });

  it("toggle saves the preference", async () => {
    setup();
    await screen.findByText("Exibindo 2 notificações");
    fireEvent.click(screen.getByRole("switch", { name: "Notificar lead pronto para atendimento" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/lais/notificacoes/preferencias", [{ tipo: "novo_atendimento", in_app: false }]));
  });

  it("marks one read on expand and all read", async () => {
    setup();
    await screen.findByText("Exibindo 2 notificações");
    fireEvent.click(screen.getAllByRole("button", { name: "Expandir" })[0]);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/notificacoes/lidas", { ids: ["a"] }));
    fireEvent.click(screen.getByRole("button", { name: /Marcar todas/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/notificacoes/lidas", { todas: true }));
  });
});
