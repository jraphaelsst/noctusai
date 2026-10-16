/** Lais › Equipes — wizard (3 steps), modes, keep-last, members, metrics, delete confirm, admin gate. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfirmProvider } from "@noctusai/lib";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("@/hooks/useTeam", () => ({
  useTeamMembers: () => ({ isPending: false, data: [
    { id: "u1", nome: "Ana", email: "a@x.com" }, { id: "u2", nome: "Beto", email: "b@x.com" },
  ] }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import LaisEquipes from "./Equipes";

const EQUIPE = {
  id: "e1", nome: "Comercial", atende_apos_julia: true, modo: "funil", manter_ultimo: false,
  membros: [{ user_id: "u1", nome: "Ana", ativo: true, ordem: 0 }],
};
const METRICAS = [{ user_id: "u1", nome: "Ana", ultimo_acesso: null, tpr_segundos: 125, conversas: 7, distribuicao: 4 }];

function setup(lista: unknown[] = [EQUIPE]) {
  api.get.mockImplementation((url: string) =>
    url.includes("/metricas") ? Promise.resolve({ data: METRICAS }) : Promise.resolve({ data: lista }));
  api.post.mockResolvedValue({ data: { ...EQUIPE, id: "e2" } });
  api.patch.mockResolvedValue({});
  api.delete.mockResolvedValue({});
  api.put.mockResolvedValue({});
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ConfirmProvider><LaisEquipes /></ConfirmProvider></QueryClientProvider>);
}

beforeEach(() => { h.admin = true; vi.clearAllMocks(); });
afterEach(cleanup);

describe("Equipes page", () => {
  it("shows empty state, then list rows with member count", async () => {
    setup([]);
    expect(await screen.findByTestId("equipes-vazio")).toBeTruthy();
    cleanup();
    setup();
    expect(await screen.findByText("Comercial")).toBeTruthy();
    expect(screen.getByText(/— 1 membro/)).toBeTruthy();
  });

  it("wizard runs 3 steps and posts team with mode, keep-last and members", async () => {
    setup();
    await screen.findByText("Comercial");
    fireEvent.click(screen.getByText("Criar equipe"));
    expect(await screen.findByText("Configurar nova equipe")).toBeTruthy();
    expect(screen.getAllByText("Passo 1 de 3").length).toBeGreaterThan(0);
    const next = screen.getByText("Próximo") as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("equipe-nome"), { target: { value: "Vendas" } });
    fireEvent.click(screen.getByLabelText(/Não/));
    fireEvent.click(screen.getByText("Próximo"));
    expect(screen.getByTestId("passo-membros")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Beto"));
    fireEvent.click(screen.getByText("Próximo"));
    expect(screen.getByText("Como os leads serão atribuídos?")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Via Julia/));
    fireEvent.click(screen.getByRole("switch", { name: /último responsável/ }));
    fireEvent.click(screen.getByText("Concluir"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/equipes",
      { nome: "Vendas", atende_apos_julia: false, modo: "julia", manter_ultimo: true }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/equipes/e2/membros", { user_id: "u2" }));
  });

  it("expanding a team shows the metrics table", async () => {
    setup();
    fireEvent.click(await screen.findByText("Comercial"));
    const linha = await screen.findByTestId("metrica-linha");
    expect(within(linha).getByText("2 min")).toBeTruthy();
    expect(within(linha).getByText("7")).toBeTruthy();
    expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/\/api\/lais\/equipes\/e1\/metricas\?mes=\d{4}-\d{2}/));
  });

  it("members drawer adds and removes", async () => {
    setup();
    fireEvent.click(await screen.findByLabelText("Editar Comercial"));
    fireEvent.click(screen.getByText("Usuários"));
    fireEvent.click(await screen.findByLabelText("Adicionar Beto"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/equipes/e1/membros", { user_id: "u2" }));
    fireEvent.click(screen.getByLabelText("Remover Ana"));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/lais/equipes/e1/membros/u1"));
  });

  it("delete asks for confirmation before calling DELETE", async () => {
    setup();
    fireEvent.click(await screen.findByLabelText("Editar Comercial"));
    fireEvent.click(screen.getByText("Excluir equipe"));
    expect(api.delete).not.toHaveBeenCalled();
    const dlg = await screen.findByRole("alertdialog");
    fireEvent.click(within(dlg).getByRole("button", { name: "Excluir equipe" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/lais/equipes/e1"));
  });

  it("hides write controls for non-admins", async () => {
    h.admin = false;
    setup();
    await screen.findByText("Comercial");
    expect(screen.queryByText("Criar equipe")).toBeNull();
    expect(screen.queryByLabelText("Editar Comercial")).toBeNull();
  });
});
