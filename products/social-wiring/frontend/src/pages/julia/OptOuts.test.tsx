/** Julia › Opt-outs — history (who/why/notice), failed-notice resend, reactivation with a required reason, ?evento highlight,
 *  the data-request tab with deadline highlighting, and every state (loading / empty / error / success). */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import JuliaOptOuts from "./OptOuts";

const EV = (over: Record<string, unknown> = {}) => ({
  id: "ev1", tipo: "opt_out", lead_ref: "lead1", lead_nome: "Ana", lead_telefone: "+5511988887777", agent_nome: "Julia",
  ator_user_id: null, ator_nome: null, origem: "agente", motivo: "lead_pediu_parar", mensagem_lead: "pare de me mandar",
  em: "2026-10-21T12:00:00Z", participantes_encerrados: 2, notificacao_status: "enviada", notificacao_erro: null,
  notificado_em: "2026-10-21T12:00:05Z", ativo: true, ...over,
});
const SOL = (over: Record<string, unknown> = {}) => ({
  id: "s1", contato_id: "lead1", chat_id: "c", tipo: "eliminacao", trecho_lead: "quero apagar meus dados",
  recebida_em: "2026-10-20T12:00:00Z", prazo_em: "2026-11-04T12:00:00Z", status: "aberta", decidido_por: null, decidido_em: null,
  motivo_decisao: null, notificacao_status: "enviada", notificacao_erro: null, prazo_situacao: "no_prazo", ...over,
});

function setup(url = "/julia/opt-outs", { historico = [EV()], solicitacoes = [SOL()] }: { historico?: unknown[] | Error; solicitacoes?: unknown[] | Error } = {}) {
  api.get.mockImplementation((u: string) => {
    if (u.startsWith("/api/julia/opt-outs/solicitacoes"))
      return solicitacoes instanceof Error ? Promise.reject(solicitacoes) : Promise.resolve({ data: { items: solicitacoes, total: solicitacoes.length } });
    if (u.startsWith("/api/julia/opt-outs"))
      return historico instanceof Error ? Promise.reject(historico) : Promise.resolve({ data: { items: historico, next_cursor: null } });
    return Promise.reject(new Error(`unexpected GET ${u}`));
  });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}><JuliaOptOuts /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { vi.clearAllMocks(); h.admin = true; });
afterEach(cleanup);

describe("histórico", () => {
  it("shows a skeleton, then when/lead/who/why/the lead's message/conversations ended/notice", async () => {
    setup();
    expect(screen.getByTestId("optouts-skeleton")).toBeTruthy();
    const item = await screen.findByTestId("optout-item");
    expect(item.textContent).toContain("Ana");
    expect(item.textContent).toContain("+5511988887777");
    expect(item.textContent).toContain("Agente (Julia)");
    expect(item.textContent).toContain("lead_pediu_parar");
    expect(item.textContent).toContain("pare de me mandar");
    expect(item.textContent).toContain("Enviada");
    expect(within(item).getByTestId("optout-ativo")).toBeTruthy();
  });

  it("names the operator who marked it", async () => {
    setup("/julia/opt-outs", { historico: [EV({ origem: "operador", ator_nome: "Adriana", agent_nome: null })] });
    expect((await screen.findByTestId("optout-item")).textContent).toContain("Operador: Adriana");
  });

  it("empty state", async () => {
    setup("/julia/opt-outs", { historico: [] });
    expect(await screen.findByTestId("optouts-vazio")).toBeTruthy();
  });

  it("error state with a retry", async () => {
    setup("/julia/opt-outs", { historico: new Error("agents down") });
    expect(await screen.findByTestId("optouts-erro")).toBeTruthy();
  });

  it("?evento highlights the record", async () => {
    setup("/julia/opt-outs?evento=ev2", { historico: [EV(), EV({ id: "ev2", ativo: false })] });
    const itens = await screen.findAllByTestId("optout-item");
    expect(itens.map((i) => i.getAttribute("data-destacado"))).toEqual(["false", "true"]);
  });

  it("a failed notice is red, shows its error and an admin can resend it", async () => {
    setup("/julia/opt-outs", { historico: [EV({ notificacao_status: "falhou", notificacao_erro: "sem destinatarios" })] });
    const item = await screen.findByTestId("optout-item");
    expect(item.className).toContain("border-destructive");
    expect(within(item).getByTestId("optout-notificacao").textContent).toContain("sem destinatarios");
    fireEvent.click(within(item).getByTestId("optout-reenviar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/opt-outs/ev1/notificar", {}));
  });

  it("a non-admin gets neither resend nor reactivate", async () => {
    h.admin = false;
    setup("/julia/opt-outs", { historico: [EV({ notificacao_status: "falhou", notificacao_erro: "x" })] });
    await screen.findByTestId("optout-item");
    expect(screen.queryByTestId("optout-reenviar")).toBeNull();
    expect(screen.queryByTestId("optout-reativar")).toBeNull();
  });

  it("reactivation needs a reason, posts it and shows a server refusal inline", async () => {
    setup();
    fireEvent.click(await screen.findByTestId("optout-reativar"));
    const confirmar = await screen.findByTestId("motivo-dialog-confirmar");
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("motivo-dialog-texto"), { target: { value: "o lead pediu para voltar" } });
    expect((confirmar as HTMLButtonElement).disabled).toBe(false);
    api.post.mockRejectedValueOnce({ message: "Este lead não tem opt-out ativo.", body: { error: { message: "Este lead não tem opt-out ativo." } } });
    fireEvent.click(confirmar);
    expect((await screen.findByTestId("motivo-dialog-erro")).textContent).toContain("não tem opt-out ativo");
    expect(api.post).toHaveBeenCalledWith("/api/julia/opt-outs/leads/lead1/reativar", { motivo: "o lead pediu para voltar" });
    api.post.mockResolvedValueOnce({ data: {} });
    fireEvent.click(screen.getByTestId("motivo-dialog-confirmar"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("no Reativar on a record that is not the active opt-out", async () => {
    setup("/julia/opt-outs", { historico: [EV({ ativo: false }), EV({ id: "ev3", tipo: "reativacao", ativo: false, origem: "operador", ator_nome: "Dono" })] });
    await screen.findAllByTestId("optout-item");
    expect(screen.queryByTestId("optout-reativar")).toBeNull();
    expect(screen.getAllByTestId("optout-item")[1].textContent).toContain("Atendimento reativado");
  });
});

describe("solicitações de dados", () => {
  it("highlights requests near or past the deadline, and a failed admin notice", async () => {
    setup("/julia/opt-outs?aba=solicitacoes", { solicitacoes: [
      SOL({ id: "a", prazo_situacao: "vencida" }), SOL({ id: "b", prazo_situacao: "vence_em_breve", notificacao_status: "falhou", notificacao_erro: "boom" }),
      SOL({ id: "c" }),
    ] });
    const itens = await screen.findAllByTestId("sol-item");
    expect(itens.map((i) => i.getAttribute("data-prazo"))).toEqual(["vencida", "vence_em_breve", "no_prazo"]);
    expect(itens[0].className).toContain("border-destructive");
    expect(itens[1].className).toContain("border-warning");
    expect(within(itens[0]).getByTestId("sol-prazo").textContent).toBe("Prazo vencido");
    expect(within(itens[1]).getByTestId("sol-notificacao-falhou").textContent).toContain("boom");
    expect(itens[0].textContent).toContain("quero apagar meus dados");
  });

  it("an admin moves the status; denying needs a reason; a non-admin cannot decide", async () => {
    setup("/julia/opt-outs?aba=solicitacoes");
    fireEvent.click(await screen.findByTestId("sol-em_analise"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/opt-outs/solicitacoes/s1", { status: "em_analise", motivo: undefined }));
    fireEvent.click(screen.getByTestId("sol-negada"));
    expect((await screen.findByTestId("motivo-dialog-confirmar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("motivo-dialog-texto"), { target: { value: "guarda legal" } });
    fireEvent.click(screen.getByTestId("motivo-dialog-confirmar"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/opt-outs/solicitacoes/s1", { status: "negada", motivo: "guarda legal" }));
    cleanup();
    h.admin = false;
    setup("/julia/opt-outs?aba=solicitacoes");
    await screen.findByTestId("sol-item");
    expect(screen.queryByTestId("sol-em_analise")).toBeNull();
  });

  it("empty and error states", async () => {
    setup("/julia/opt-outs?aba=solicitacoes", { solicitacoes: [] });
    expect(await screen.findByTestId("sol-vazio")).toBeTruthy();
    cleanup();
    setup("/julia/opt-outs?aba=solicitacoes", { solicitacoes: new Error("x") });
    expect(await screen.findByTestId("sol-erro")).toBeTruthy();
  });

  it("the tab switch changes the view", async () => {
    setup();
    await screen.findByTestId("optout-item");
    fireEvent.click(screen.getByTestId("aba-solicitacoes"));
    expect(await screen.findByTestId("sol-item")).toBeTruthy();
  });
});
