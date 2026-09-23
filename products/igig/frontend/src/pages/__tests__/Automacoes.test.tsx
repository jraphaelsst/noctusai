/**
 * Automações page (Slice F): rules list with stage names, admin-only
 * create / toggle / delete, the create flow (stages of the chosen board →
 * POST with per-tipo params), and the execuções log with error detail.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api, user } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  user: { current: { id: "u1", user_metadata: { org_role: "admin" } as Record<string, unknown> } },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: user.current }) }));

import Automacoes from "../Automacoes";

const STAGES_COMERCIAL = [
  { id: "sc1", slug: "novo", label: "Novo lead", cor: "blue", posicao: 0, papel: null, ativo: true },
  { id: "sc2", slug: "proposta", label: "Proposta enviada", cor: "amber", posicao: 1, papel: null, ativo: true },
];
const STAGES_ESTEIRA = [{ id: "se1", slug: "criacao", label: "Criação", cor: "blue", posicao: 0, papel: null, ativo: true }];
const REGRA = {
  id: "a1", pipeline: "comercial", stage_id: "sc2", gatilho: "sla", sla_horas: 48,
  acao: { tipo: "notificar", params: { titulo: "Proposta parada", mensagem: null, usuario_ids: [] } },
  ativo: true, created_at: null, updated_at: null,
};
const EXEC = {
  id: "e1", automacao_id: "a1", entidade_id: "n1", status: "erro", detalhe: "Sem destinatário: o contato não tem e-mail.",
  executado_em: "2026-09-22T14:05:00Z",
  automacao: { id: "a1", pipeline: "comercial", stage_id: "sc2", gatilho: "sla", tipo: "enviar_email" },
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Automacoes />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  user.current = { id: "u1", user_metadata: { org_role: "admin" } };
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/automacoes") return { data: [REGRA] };
    if (path === "/api/automacoes/execucoes") return { data: [EXEC] };
    if (path === "/api/comercial/pipeline/stages") return STAGES_COMERCIAL;
    if (path === "/api/esteira/stages") return STAGES_ESTEIRA;
    if (path === "/api/custos/profissionais") return [];
    if (path === "/api/team") return { data: [{ id: "u9", nome: "Bia", email: "bia@agencia.com" }] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockImplementation(async (_p: string, body: Record<string, unknown>) => ({ data: { ...REGRA, ...body, id: "a2" } }));
  api.patch.mockImplementation(async (_p: string, body: Record<string, unknown>) => ({ data: { ...REGRA, ...body } }));
  api.delete.mockResolvedValue(null);
});
afterEach(cleanup);

describe("Automações page", () => {
  it("lists rules with the stage name and the SLA trigger", async () => {
    renderPage();
    const regra = await screen.findByTestId("automacao-a1");
    expect(await within(regra).findByText("Proposta enviada")).toBeInTheDocument();
    expect(within(regra).getByText(/SLA estourado · 48h/)).toBeInTheDocument();
    expect(within(regra).getByText("Notificar: Proposta parada")).toBeInTheDocument();
  });

  it("the execuções log shows why a run failed", async () => {
    renderPage();
    const log = await screen.findByTestId("execucoes-lista");
    expect(within(log).getByText("Erro")).toBeInTheDocument();
    expect(within(log).getByText(/Sem destinatário/)).toBeInTheDocument();
  });

  it("an admin pauses a rule through PATCH {ativo:false}", async () => {
    renderPage();
    const regra = await screen.findByTestId("automacao-a1");
    fireEvent.click(within(regra).getByRole("switch", { name: "Pausar automação" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/automacoes/a1", { ativo: false }));
  });

  it("an admin deletes a rule only after confirming", async () => {
    renderPage();
    const regra = await screen.findByTestId("automacao-a1");
    fireEvent.click(within(regra).getByRole("button", { name: "Excluir automação" }));
    expect(api.delete).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/automacoes/a1"));
  });

  it("creates a rule: board → stage → trigger → ação with exactly its params", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("automacao-nova"));
    const form = await screen.findByTestId("automacao-form");
    const etapa = within(form).getByLabelText("Etapa");
    await waitFor(() => expect(within(etapa).getByRole("option", { name: "Novo lead" })).toBeInTheDocument());
    fireEvent.change(etapa, { target: { value: "sc1" } });
    fireEvent.change(within(form).getByLabelText("Tipo de ação"), { target: { value: "criar_checklist" } });
    const checklist = within(form).getByTestId("params-criar_checklist");
    fireEvent.change(within(checklist).getAllByRole("textbox")[0], { target: { value: "Onboarding" } });
    fireEvent.change(within(checklist).getAllByRole("textbox")[1], { target: { value: "Contrato\nBriefing" } });
    fireEvent.click(within(form).getByTestId("automacao-salvar"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/automacoes", {
        pipeline: "comercial",
        stage_id: "sc1",
        gatilho: "entrada_etapa",
        sla_horas: null,
        acao: { tipo: "criar_checklist", params: { titulo: "Onboarding", itens: ["Contrato", "Briefing"] } },
        ativo: true,
      }),
    );
  });

  it("the Esteira board does not offer the card-hub checklist action", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("automacao-nova"));
    const form = await screen.findByTestId("automacao-form");
    fireEvent.change(within(form).getByLabelText("Quadro"), { target: { value: "esteira" } });
    const tipos = within(within(form).getByLabelText("Tipo de ação")).getAllByRole("option").map((o) => o.textContent);
    expect(tipos).not.toContain("Criar checklist");
    await waitFor(() => expect(within(within(form).getByLabelText("Etapa")).getByRole("option", { name: "Criação" })).toBeInTheDocument());
  });

  it("non-admins read rules and logs but get no editing controls", async () => {
    user.current = { id: "u2", user_metadata: { org_role: "member" } };
    renderPage();
    const regra = await screen.findByTestId("automacao-a1");
    expect(within(regra).queryByRole("switch")).not.toBeInTheDocument();
    expect(within(regra).queryByRole("button", { name: "Editar automação" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("automacao-nova")).not.toBeInTheDocument();
    expect(screen.getByText(/Somente administradores/)).toBeInTheDocument();
  });

  it("shows the server's error instead of an empty list", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/automacoes") throw new Error("banco indisponível");
      if (path === "/api/automacoes/execucoes") return { data: [] };
      return [];
    });
    renderPage();
    expect(await screen.findByText("banco indisponível")).toBeInTheDocument();
    expect(screen.queryByText("Nenhuma automação ainda.")).not.toBeInTheDocument();
  });
});
