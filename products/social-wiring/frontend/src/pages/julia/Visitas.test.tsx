/**
 * Julia › Visitas — empty/active states, config drawer (per-operation split,
 * grade, admin gate), week/day calendar (no month), dialog transitions + 409.
 * `@/lib/api` is the seam; real hooks + components.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfirmProvider } from "@noctusai/lib";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import JuliaVisitas from "./Visitas";
import { chaveData } from "@/components/julia/visitas/calendario";

const grade = { seg: [], ter: [], qua: [], qui: [], sex: [], sab: [], dom: [] };
const op = (ativo: boolean) => ({ ativo, cpf_obrigatorio: false, min_dias: 1, min_horas: 2, max_dias: 30, grade });
const CFG_OFF = { separar_operacao: false, config: { geral: op(false) } };
const CFG_ON = { separar_operacao: false, config: { geral: op(true) } };

const hoje = new Date();
hoje.setHours(10, 0, 0, 0);
const fim = new Date(hoje.getTime() + 3600_000);
const VISITA = {
  id: "v1", contato_nome: "Maria", codigo_imovel: "AP1", operacao: "compra",
  inicio: hoje.toISOString(), fim: fim.toISOString(), status: "solicitada",
  responsavel_user_id: "u1", responsavel_nome: "Ana",
};

function err(code: string, status = 409) {
  return Object.assign(new Error("x"), { status, body: { error: { code, message: "srv" } } });
}
function setup(cfg: unknown = CFG_ON, visitas: unknown[] = [VISITA]) {
  api.get.mockImplementation((url: string) =>
    url === "/api/julia/visitas/config" ? Promise.resolve({ data: cfg }) : Promise.resolve({ data: visitas }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><ConfirmProvider><JuliaVisitas /></ConfirmProvider></QueryClientProvider>,
  );
}

beforeEach(() => { h.admin = true; vi.clearAllMocks(); });
afterEach(cleanup);

describe("Visitas page", () => {
  it("shows the empty state and opens the drawer from it", async () => {
    setup(CFG_OFF, []);
    expect(await screen.findByText("Ative as solicitações de visita")).toBeTruthy();
    fireEvent.click(within(screen.getByTestId("visitas-vazio")).getByRole("button", { name: "Configurar visitas" }));
    expect(screen.getByTestId("visitas-drawer")).toBeTruthy();
    expect(screen.getByTestId("visitas-status-chip").textContent).toBe("Inativo");
  });

  it("renders week by default, switches to day, and has no month view", async () => {
    setup();
    const cal = await screen.findByTestId("visitas-calendario");
    expect(cal.getAttribute("data-view")).toBe("semana");
    expect(within(cal).getAllByTestId(/^dia-/)).toHaveLength(7);
    expect(screen.queryByRole("button", { name: /mês/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Dia" }));
    await waitFor(() => expect(screen.getByTestId("visitas-calendario").getAttribute("data-view")).toBe("dia"));
    expect(within(screen.getByTestId("visitas-calendario")).getAllByTestId(/^dia-/)).toHaveLength(1);
    expect(api.get).toHaveBeenCalledWith(`/api/julia/visitas?view=dia&data=${chaveData(new Date())}`);
  });

  it("filters by status", async () => {
    setup();
    await screen.findByTestId("visitas-lista");
    await screen.findByText(/Maria/, { selector: "li button" });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "cancelada" } });
    expect(await screen.findByTestId("visitas-lista-vazia")).toBeTruthy();
  });
});

describe("config drawer", () => {
  async function abrir(cfg: unknown = CFG_ON) {
    setup(cfg);
    await screen.findByTestId("visitas-calendario");
    fireEvent.click(screen.getAllByRole("button", { name: "Configurar visitas" })[0]);
  }

  it("saves one config; grade validates De/Até", async () => {
    api.put.mockResolvedValue({});
    await abrir();
    fireEvent.change(screen.getByLabelText("Segunda de"), { target: { value: "09:00" } });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Segunda até"), { target: { value: "12:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/api/julia/visitas/config");
    expect(body.config.geral.grade.seg).toEqual([{ inicio: "09:00", fim: "12:00" }]);
    expect(body.separar_operacao).toBe(false);
  });

  it("splits per operation with independent settings", async () => {
    api.put.mockResolvedValue({});
    await abrir();
    fireEvent.click(screen.getByLabelText(/Diferenciar configuração/));
    fireEvent.click(screen.getByRole("tab", { name: "Compra" }));
    fireEvent.click(screen.getByLabelText("Solicitação de CPF obrigatória?"));
    fireEvent.click(screen.getByRole("tab", { name: "Aluguel" }));
    expect((screen.getByLabelText("Solicitação de CPF obrigatória?") as HTMLElement).getAttribute("data-state")).toBe("unchecked");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const body = api.put.mock.calls[0][1];
    expect(body.separar_operacao).toBe(true);
    expect(body.config.compra.cpf_obrigatorio).toBe(true);
    expect(body.config.aluguel.cpf_obrigatorio).toBe(false);
  });

  it("is read-only for non-admins", async () => {
    h.admin = false;
    await abrir();
    expect(screen.getByTestId("visitas-readonly")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("visit dialog", () => {
  async function abrirVisita() {
    setup();
    fireEvent.click(await screen.findByText(/Maria/, { selector: "li button" }));
    return screen.getByTestId("visita-dialog");
  }
  const aceitar = async (label: string) => {
    const dlg = await screen.findByTestId("confirm-dialog");
    fireEvent.click(within(dlg).getByRole("button", { name: label }));
  };

  it("confirms after a confirmation prompt", async () => {
    api.post.mockResolvedValue({ data: { ...VISITA, status: "confirmada" } });
    const d = await abrirVisita();
    fireEvent.click(within(d).getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText(/receberá uma mensagem/)).toBeTruthy();
    await aceitar("Confirmar visita");
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/visitas/v1/confirmar", {}));
  });

  it("remarca with the new window", async () => {
    api.post.mockResolvedValue({ data: VISITA });
    const d = await abrirVisita();
    fireEvent.click(within(d).getByRole("button", { name: "Remarcar" }));
    fireEvent.change(screen.getByLabelText("Novo início"), { target: { value: "2030-01-02T09:00" } });
    fireEvent.change(screen.getByLabelText("Novo fim"), { target: { value: "2030-01-02T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Remarcar visita" }));
    await aceitar("Remarcar");
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe("/api/julia/visitas/v1/remarcar");
    expect(new Date(body.inicio).getTime()).toBe(new Date("2030-01-02T09:00").getTime());
  });

  it("cancels with a reason and shows 409 transicao_invalida in pt-BR", async () => {
    api.post.mockRejectedValue(err("transicao_invalida"));
    const d = await abrirVisita();
    fireEvent.click(within(d).getByRole("button", { name: "Cancelar" }));
    fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "lead desistiu" } });
    fireEvent.click(within(d).getByRole("button", { name: "Cancelar visita" }));
    await aceitar("Cancelar visita");
    expect(await screen.findByTestId("visita-erro")).toBeTruthy();
    expect(screen.getByTestId("visita-erro").textContent).toMatch(/não pode mais mudar/);
    expect(api.post.mock.calls[0]).toEqual(["/api/julia/visitas/v1/cancelar", { motivo: "lead desistiu" }]);
  });
});
