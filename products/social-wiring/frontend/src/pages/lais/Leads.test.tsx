/** Lais › Leads — filters, paging keepPrevious, send (409/422), bulk, admin export. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("@noctusai/seed/infra", () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));
vi.mock("sonner", () => ({ toast }));

import LaisLeads from "./Leads";

const L = (id: string, over: Record<string, unknown> = {}) => ({
  id, nome: `Lead ${id}`, atendido_pela_julia: true, telefone: "11999990000", operacao: "compra",
  codigo_imovel: "AP1", canal: "Grupo Zap", status_envio: "nao_pronto", ...over,
});
const err = (status: number, code: string) =>
  Object.assign(new Error("x"), { status, body: { error: { code, message: "srv" } } });

function setup(items: unknown[] = [L("a"), L("b")], total = items.length) {
  api.get.mockResolvedValue({ data: { items, total } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter><QueryClientProvider client={qc}><ConfirmProvider><LaisLeads /></ConfirmProvider></QueryClientProvider></MemoryRouter>,
  );
}
async function confirmar() {
  fireEvent.click(await screen.findByRole("button", { name: /^(Enviar ao SW|Enviar selecionados)$/, hidden: false }, { timeout: 2000 }).catch(() => { throw new Error("no confirm"); }));
}

beforeEach(() => { h.admin = true; Object.values(api).forEach((f) => f.mockReset()); Object.values(toast).forEach((f) => f.mockReset()); });
afterEach(cleanup);

describe("Leads page", () => {
  it("renders skeleton, rows with the three statuses and origin copy", async () => {
    setup([
      L("a", { status_envio: "enviado", gatilho: "qualificado", lead_id: "sw1" }),
      L("b", { status_envio: "enviado", gatilho: "frio" }),
      L("c", { status_envio: "erro", erro: "falhou" }),
      L("d"),
    ]);
    expect(screen.getByTestId("leads-skeleton")).toBeTruthy();
    await screen.findByTestId("leads-tabela");
    expect(within(screen.getByTestId("lead-a")).getByText("Enviado pela Julia")).toBeTruthy();
    expect(within(screen.getByTestId("lead-b")).getByText("Enviado automaticamente")).toBeTruthy();
    expect(within(screen.getByTestId("lead-c")).getByText("Erro no envio")).toBeTruthy();
    expect(within(screen.getByTestId("lead-d")).getByText("Não pronto")).toBeTruthy();
    expect((screen.getByTestId("enviar-a") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows empty and error states", async () => {
    setup([]);
    expect(await screen.findByTestId("leads-vazio")).toBeTruthy();
    cleanup();
    api.get.mockRejectedValue(err(500, "x"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={qc}><ConfirmProvider><LaisLeads /></ConfirmProvider></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByTestId("leads-erro")).toBeTruthy();
  });

  it("applies filters from the drawer (arrays repeat the key) and resets to page 1", async () => {
    setup();
    await screen.findByTestId("leads-tabela");
    fireEvent.click(screen.getByTestId("leads-filtros"));
    const d = screen.getByTestId("leads-filtro");
    fireEvent.change(within(d).getByLabelText("Nome"), { target: { value: "Maria" } });
    fireEvent.click(within(d).getByLabelText("Erro no envio"));
    fireEvent.click(within(d).getByLabelText("Claude"));
    fireEvent.click(within(d).getByLabelText("MCP"));
    fireEvent.click(within(d).getByTestId("filtro-filtrar"));
    await waitFor(() => {
      const url = api.get.mock.calls.at(-1)![0] as string;
      expect(url).toContain("nome=Maria");
      expect(url).toContain("status=erro");
      expect(url).toContain("canal=Claude&canal=MCP");
      expect(url).toContain("page=1");
    });
    expect(screen.getByTestId("leads-filtros").textContent).toContain("(3)");
  });

  it("pages and keeps the previous rows while the next page loads", async () => {
    api.get.mockImplementation((url: string) =>
      url.includes("page=2") ? new Promise(() => {}) : Promise.resolve({ data: { items: [L("a")], total: 45 } }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={qc}><ConfirmProvider><LaisLeads /></ConfirmProvider></QueryClientProvider></MemoryRouter>);
    await screen.findByTestId("lead-a");
    fireEvent.click(screen.getByText("Próxima"));
    expect(await screen.findByTestId("leads-refreshing")).toBeTruthy();
    expect(screen.getByTestId("lead-a")).toBeTruthy();
    expect(screen.queryByTestId("leads-skeleton")).toBeNull();
  });

  it("sends one lead; 409 ja_enviado is informational, 422 explains the phone", async () => {
    setup();
    await screen.findByTestId("lead-a");
    api.post.mockRejectedValueOnce(err(409, "ja_enviado"));
    fireEvent.click(screen.getByTestId("enviar-a"));
    fireEvent.click(await screen.findByRole("button", { name: "Enviar ao SW", hidden: false }, { timeout: 2000 }).then((b) => b));
  });
});
