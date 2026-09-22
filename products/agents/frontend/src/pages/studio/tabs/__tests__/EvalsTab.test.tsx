/**
 * EvalsTab.tsx tests — Agent Studio CONTRACT.md §G "Avaliações". Stubs
 * `useEvals.ts` hooks + `useIsAdmin`; `useDraftVersion` reads the draft off
 * the shared `useStudioAgent` query (`hooks/studio/useStudioAgents.ts`),
 * stubbed here rather than the network boundary.
 */
import React from "react";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseEvalCases = vi.fn();
const mockUseEvalRuns = vi.fn();
const mockUseEvalRun = vi.fn();
const mockUseCreateEvalRun = vi.fn();
const mockUseCreateEvalCase = vi.fn();
const mockUseUpdateEvalCase = vi.fn();
const mockUseDeleteEvalCase = vi.fn();
const mockUseCancelEvalRun = vi.fn();
const mockUseIsAdmin = vi.fn();
const mockUseStudioAgent = vi.fn();

vi.mock("@/hooks/studio/useEvals", () => ({
  useEvalCases: () => mockUseEvalCases(),
  useEvalRuns: () => mockUseEvalRuns(),
  useEvalRun: () => mockUseEvalRun(),
  useCreateEvalRun: () => mockUseCreateEvalRun(),
  useCreateEvalCase: () => mockUseCreateEvalCase(),
  useUpdateEvalCase: () => mockUseUpdateEvalCase(),
  useDeleteEvalCase: () => mockUseDeleteEvalCase(),
  useCancelEvalRun: () => mockUseCancelEvalRun(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));
vi.mock("@/hooks/studio/useStudioAgents", () => ({ useStudioAgent: () => mockUseStudioAgent() }));

const CASE = {
  id: "e1",
  slug: "pergunta-reels",
  titulo: "Pergunta sobre reels",
  entrada: "Como faço um reels?",
  criterios: { deve: ["menciona roteiro"], nao_deve: [] },
  tags: [],
  ativo: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(false);
  mockUseEvalCases.mockReturnValue({ data: [CASE], showSkeleton: false, isError: false, error: null });
  mockUseEvalRuns.mockReturnValue({ data: [] });
  mockUseEvalRun.mockReturnValue({ data: undefined, showSkeleton: false, isError: false });
  mockUseCreateEvalRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseCreateEvalCase.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateEvalCase.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDeleteEvalCase.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseCancelEvalRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseStudioAgent.mockReturnValue({ data: { versoes: [{ id: "v1", versao: 2, status: "rascunho" }] } });
});

afterEach(() => cleanup());

async function renderTab() {
  const EvalsTab = (await import("@/pages/studio/tabs/EvalsTab")).default;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(React.createElement(QueryClientProvider, { client: qc }, React.createElement(EvalsTab, { agentKey: "isaia" })));
}

describe("EvalsTab — loading/empty/error", () => {
  it("shows a skeleton while cases load", async () => {
    mockUseEvalCases.mockReturnValue({ data: undefined, showSkeleton: true, isError: false, error: null });
    await renderTab();
    expect(screen.queryByTestId("evals-case-pergunta-reels")).toBeNull();
  });

  it("shows an error state when cases fail to load", async () => {
    mockUseEvalCases.mockReturnValue({ data: undefined, showSkeleton: false, isError: true, error: new Error("boom") });
    await renderTab();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows empty states for no cases and no runs", async () => {
    mockUseEvalCases.mockReturnValue({ data: [], showSkeleton: false, isError: false, error: null });
    await renderTab();
    expect(screen.getByText("Nenhum caso de avaliação ainda.")).toBeTruthy();
    expect(screen.getByText("Nenhuma execução ainda.")).toBeTruthy();
  });
});

describe("EvalsTab — success + role gating", () => {
  it("member: sees the case card, no 'Rodar avaliação' or 'Novo caso' controls", async () => {
    await renderTab();
    expect(screen.getByTestId("evals-case-pergunta-reels")).toBeTruthy();
    expect(screen.queryByTestId("evals-run-button")).toBeNull();
  });

  it("admin: sees the run button, enabled once a draft + cases exist", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderTab();
    const btn = await screen.findByTestId("evals-run-button");
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("shows a run row and its detail with per-case verdicts", async () => {
    mockUseEvalRuns.mockReturnValue({
      data: [{ id: "r1", version_id: "v1", compiled_hash: "sha256:aaaa", status: "concluida", total: 1, aprovados: 1, score: 0.9, limiar: 0.8, started_at: "2026-09-21T10:00:00Z", finished_at: "t2", erro: null }],
    });
    mockUseEvalRun.mockReturnValue({
      data: {
        id: "r1",
        version_id: "v1",
        compiled_hash: "sha256:aaaa",
        status: "concluida",
        total: 1,
        aprovados: 1,
        score: 0.9,
        limiar: 0.8,
        started_at: "t",
        finished_at: "t2",
        erro: null,
        resultados: [{ case_id: "e1", case_slug: "pergunta-reels", case_titulo: "Pergunta sobre reels", status: "aprovado", score: 1, saida: "Resposta.", veredito: [{ criterio: "menciona roteiro", tipo: "deve", ok: true, motivo: "ok" }], notas_juiz: null, duracao_ms: 500 }],
      },
      showSkeleton: false,
      isError: false,
    });
    await renderTab();
    screen.getByTestId("evals-run-row-r1").click();
    expect(await screen.findByTestId("evals-run-detail")).toBeTruthy();
    expect(screen.getByTestId("evals-result-e1")).toBeTruthy();
  });
});

describe("EvalsTab — case editor (§G)", () => {
  it("admin: opens the editor pre-filled and saves a patch (no slug) via useUpdateEvalCase", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const mutateAsync = vi.fn().mockResolvedValue({ ...CASE });
    mockUseUpdateEvalCase.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("evals-case-edit-pergunta-reels"));
    const form = await screen.findByTestId("evals-edit-case-form-pergunta-reels");
    const titulo = within(form).getAllByRole("textbox")[1] as HTMLInputElement; // slug, titulo, entrada, ...
    fireEvent.change(titulo, { target: { value: "Pergunta sobre reels (revisado)" } });
    fireEvent.submit(form);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const [[arg]] = mutateAsync.mock.calls;
    expect(arg.caseId).toBe("e1");
    expect(arg.patch).not.toHaveProperty("slug");
    expect(arg.patch.titulo).toBe("Pergunta sobre reels (revisado)");
  });

  it("add/remove a 'deve' criterion in the editor", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const mutateAsync = vi.fn().mockResolvedValue({ ...CASE });
    mockUseUpdateEvalCase.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("evals-case-edit-pergunta-reels"));
    const form = await screen.findByTestId("evals-edit-case-form-pergunta-reels");
    const draft = within(form).getByTestId("evals-criteria-deve-draft");
    fireEvent.change(draft, { target: { value: "cita um exemplo" } });
    fireEvent.click(within(form).getByTestId("evals-criteria-deve-add"));
    // Remove the ORIGINAL criterion (index 0), keep the new one.
    fireEvent.click(within(form).getByTestId("evals-criteria-deve-remove-0"));
    fireEvent.submit(form);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const [[arg]] = mutateAsync.mock.calls;
    expect(arg.patch.criterios.deve).toEqual(["cita um exemplo"]);
  });

  it("delete conflict (409 case_in_use) offers 'Desativar' instead of dead-ending", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const { ApiError } = await import("@/lib/errors");
    const deleteMutateAsync = vi.fn().mockRejectedValue(new ApiError(409, "Caso em uso", { detail: "Caso em uso", code: "case_in_use" }));
    mockUseDeleteEvalCase.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    const updateMutateAsync = vi.fn().mockResolvedValue({ ...CASE, ativo: false });
    mockUseUpdateEvalCase.mockReturnValue({ mutateAsync: updateMutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("evals-case-delete-pergunta-reels"));
    const banner = await screen.findByTestId("evals-case-in-use-pergunta-reels");
    expect(banner.textContent).toContain("não pode ser excluído");

    fireEvent.click(screen.getByTestId("evals-case-deactivate-pergunta-reels"));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledWith({ caseId: "e1", patch: { ativo: false } }));
  });
});

describe("EvalsTab — run cancel + partial-run label", () => {
  const RUNNING_RUN = {
    id: "r2",
    version_id: "v1",
    compiled_hash: "sha256:bbbb",
    status: "executando" as const,
    total: 1,
    aprovados: 0,
    score: null,
    limiar: 0.8,
    started_at: "2026-09-21T10:00:00Z",
    finished_at: null,
    erro: null,
  };

  it("admin: sees 'Cancelar' on a running run's detail and it calls useCancelEvalRun", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    mockUseEvalRuns.mockReturnValue({ data: [RUNNING_RUN] });
    mockUseEvalRun.mockReturnValue({ data: { ...RUNNING_RUN, resultados: [] }, showSkeleton: false, isError: false });
    const cancelMutateAsync = vi.fn().mockResolvedValue({ ...RUNNING_RUN, status: "cancelada" });
    mockUseCancelEvalRun.mockReturnValue({ mutateAsync: cancelMutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("evals-run-row-r2"));
    const cancelBtn = await screen.findByTestId("evals-run-cancel");
    fireEvent.click(cancelBtn);
    await waitFor(() => expect(cancelMutateAsync).toHaveBeenCalledWith("r2"));
  });

  it("member: never sees 'Cancelar', even on a running run", async () => {
    mockUseEvalRuns.mockReturnValue({ data: [RUNNING_RUN] });
    mockUseEvalRun.mockReturnValue({ data: { ...RUNNING_RUN, resultados: [] }, showSkeleton: false, isError: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("evals-run-row-r2"));
    await screen.findByTestId("evals-run-detail");
    expect(screen.queryByTestId("evals-run-cancel")).toBeNull();
  });

  it("labels a run against fewer than every active case 'parcial'", async () => {
    // Two active cases, but the run only covers one (`case_ids` subset) —
    // `total` (1) < active-case count (2) ⇒ partial.
    mockUseEvalCases.mockReturnValue({
      data: [CASE, { ...CASE, id: "e2", slug: "pergunta-b", titulo: "Pergunta B" }],
      showSkeleton: false,
      isError: false,
      error: null,
    });
    mockUseEvalRuns.mockReturnValue({ data: [{ ...RUNNING_RUN, status: "concluida", total: 1, aprovados: 1 }] });
    await renderTab();
    expect(screen.getByTestId("evals-run-partial-r2")).toBeTruthy();
  });
});

describe("EvalsTab — Controle de custo (contract §L)", () => {
  const CONCLUDED_RUN = {
    id: "r1",
    version_id: "v1",
    compiled_hash: "sha256:aaaa",
    status: "concluida" as const,
    total: 2,
    aprovados: 1,
    score: 0.6,
    limiar: 0.8,
    started_at: "2026-09-21T10:00:00Z",
    finished_at: "t2",
    erro: null,
    modelo_geracao: null,
    limite_usd: 2.0,
    custo_usd: 0.1234,
  };

  const RESULT_APROVADO = {
    case_id: "e1",
    case_slug: "pergunta-reels",
    case_titulo: "Pergunta sobre reels",
    status: "aprovado" as const,
    score: 1,
    saida: "Resposta.",
    veredito: [],
    notas_juiz: null,
    duracao_ms: 500,
    custo_usd: 0.08,
    tokens_entrada: 120,
    tokens_saida: 40,
    tokens_cache_leitura: null,
  };

  const RESULT_PULADO = {
    case_id: "e2",
    case_slug: "pergunta-b",
    case_titulo: "Pergunta B",
    status: "pulado" as const,
    score: null,
    saida: null,
    veredito: null,
    notas_juiz: "limite de custo atingido",
    duracao_ms: null,
    custo_usd: null,
    tokens_entrada: null,
    tokens_saida: null,
    tokens_cache_leitura: null,
  };

  describe("Nova execução — form payload shape", () => {
    it("admin: opens the form and submits {version_id, modelo_geracao: undefined, limite_usd: undefined} for the defaults", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      const mutateAsync = vi.fn().mockResolvedValue({ id: "r9" });
      mockUseCreateEvalRun.mockReturnValue({ mutateAsync, isPending: false });
      await renderTab();

      fireEvent.click(screen.getByTestId("evals-run-button"));
      const form = await screen.findByTestId("evals-new-run-form");
      fireEvent.submit(form);

      await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
        version_id: "v1",
        modelo_geracao: undefined,
        limite_usd: undefined,
      }));
      expect(mutateAsync.mock.calls[0][0]).not.toHaveProperty("case_ids");
      expect(mutateAsync.mock.calls[0][0]).not.toHaveProperty("repetir_falhas_de");
    });

    it("admin: submits the chosen draft model + limite_usd override", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      const mutateAsync = vi.fn().mockResolvedValue({ id: "r9" });
      mockUseCreateEvalRun.mockReturnValue({ mutateAsync, isPending: false });
      await renderTab();

      fireEvent.click(screen.getByTestId("evals-run-button"));
      const form = await screen.findByTestId("evals-new-run-form");
      fireEvent.change(within(form).getByTestId("evals-run-modelo"), { target: { value: "claude-sonnet-5" } });
      fireEvent.change(within(form).getByTestId("evals-run-limite"), { target: { value: "5" } });
      fireEvent.submit(form);

      await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
        version_id: "v1",
        modelo_geracao: "claude-sonnet-5",
        limite_usd: 5,
      }));
    });

    it("rejects a limite_usd outside (0, 50] client-side, without calling the mutation", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      const mutateAsync = vi.fn();
      mockUseCreateEvalRun.mockReturnValue({ mutateAsync, isPending: false });
      await renderTab();

      fireEvent.click(screen.getByTestId("evals-run-button"));
      const form = await screen.findByTestId("evals-new-run-form");
      fireEvent.change(within(form).getByTestId("evals-run-limite"), { target: { value: "50.01" } });
      fireEvent.submit(form);

      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(mutateAsync).not.toHaveBeenCalled();
    });

    it("shows the draft-model-never-gates hint", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      await renderTab();
      fireEvent.click(screen.getByTestId("evals-run-button"));
      const hint = await screen.findByTestId("evals-run-draft-hint");
      expect(hint.textContent).toContain("nunca liberam a publicação");
    });
  });

  describe("Cost display", () => {
    it("renders '—' (never 0) for a null custo_usd, and the real figure when set", async () => {
      mockUseEvalRuns.mockReturnValue({ data: [CONCLUDED_RUN] });
      mockUseEvalRun.mockReturnValue({
        data: { ...CONCLUDED_RUN, resultados: [RESULT_APROVADO, RESULT_PULADO] },
        showSkeleton: false,
        isError: false,
      });
      await renderTab();

      // Row: real custo_usd formatted, never a bare "0".
      expect(screen.getByTestId("evals-run-custo-r1").textContent).toContain("US$0.1234");

      fireEvent.click(screen.getByTestId("evals-run-row-r1"));
      await screen.findByTestId("evals-run-detail");
      // A null-cost result renders "—", never "US$0.00" / "0".
      const puladoCost = screen.getByTestId("evals-result-cost-e2");
      expect(puladoCost.textContent).toContain("—");
      expect(puladoCost.textContent).not.toMatch(/US\$0\.00/);
      const aprovadoCost = screen.getByTestId("evals-result-cost-e1");
      expect(aprovadoCost.textContent).toContain("US$0.08");
      expect(aprovadoCost.textContent).toContain("120");
      expect(aprovadoCost.textContent).toContain("40");
    });

    it("renders a distinct 'pulado' status with its budget-cap note", async () => {
      mockUseEvalRuns.mockReturnValue({ data: [CONCLUDED_RUN] });
      mockUseEvalRun.mockReturnValue({
        data: { ...CONCLUDED_RUN, resultados: [RESULT_APROVADO, RESULT_PULADO] },
        showSkeleton: false,
        isError: false,
      });
      await renderTab();
      fireEvent.click(screen.getByTestId("evals-run-row-r1"));

      const puladoRow = await screen.findByTestId("evals-result-e2");
      expect(within(puladoRow).getByTestId("evals-result-pulado-icon-e2")).toBeTruthy();
      expect(puladoRow.textContent).toContain("pulado");
      expect(puladoRow.textContent).toContain("limite de custo atingido");
    });

    it("shows a clear banner when the run was cut short by the cost cap", async () => {
      const CAPPED_RUN = { ...CONCLUDED_RUN, status: "falhou" as const, erro: "limite de custo atingido" };
      mockUseEvalRuns.mockReturnValue({ data: [CAPPED_RUN] });
      mockUseEvalRun.mockReturnValue({
        data: { ...CAPPED_RUN, resultados: [RESULT_PULADO] },
        showSkeleton: false,
        isError: false,
      });
      await renderTab();
      fireEvent.click(screen.getByTestId("evals-run-row-r1"));

      const banner = await screen.findByTestId("evals-run-budget-banner");
      expect(banner.textContent).toContain("limite de custo atingido");
    });
  });

  describe("Draft-model run badge", () => {
    it("shows 'rascunho · Sonnet 5' on a run with modelo_geracao set, row + detail", async () => {
      const DRAFT_RUN = { ...CONCLUDED_RUN, modelo_geracao: "claude-sonnet-5" as const };
      mockUseEvalRuns.mockReturnValue({ data: [DRAFT_RUN] });
      mockUseEvalRun.mockReturnValue({
        data: { ...DRAFT_RUN, resultados: [RESULT_APROVADO] },
        showSkeleton: false,
        isError: false,
      });
      await renderTab();

      expect(screen.getByTestId("evals-run-model-badge-r1").textContent).toContain("rascunho · Sonnet 5");

      fireEvent.click(screen.getByTestId("evals-run-row-r1"));
      expect(await screen.findByTestId("evals-run-model-badge")).toBeTruthy();
    });

    it("shows no model badge on a gating run (modelo_geracao null)", async () => {
      mockUseEvalRuns.mockReturnValue({ data: [CONCLUDED_RUN] });
      await renderTab();
      expect(screen.queryByTestId("evals-run-model-badge-r1")).toBeNull();
    });
  });

  describe("Repetir só as falhas", () => {
    it("admin: enabled on a finished run with non-aprovado results; sends {version_id, repetir_falhas_de}, no case_ids", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      mockUseEvalRuns.mockReturnValue({ data: [CONCLUDED_RUN] }); // aprovados(1) < total(2)
      const mutateAsync = vi.fn().mockResolvedValue({ id: "r10" });
      mockUseCreateEvalRun.mockReturnValue({ mutateAsync, isPending: false });
      await renderTab();

      const btn = screen.getByTestId("evals-run-repeat-r1");
      expect(btn.hasAttribute("disabled")).toBe(false);
      fireEvent.click(btn);

      await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ version_id: "v1", repetir_falhas_de: "r1" }));
      expect(mutateAsync.mock.calls[0][0]).not.toHaveProperty("case_ids");
    });

    it("admin: disabled when the run has zero non-aprovado results", async () => {
      mockUseIsAdmin.mockReturnValue(true);
      const ALL_APROVADO_RUN = { ...CONCLUDED_RUN, total: 1, aprovados: 1 };
      mockUseEvalRuns.mockReturnValue({ data: [ALL_APROVADO_RUN] });
      await renderTab();

      const btn = screen.getByTestId("evals-run-repeat-r1");
      expect(btn.hasAttribute("disabled")).toBe(true);
    });

    it("member: never sees the 'Repetir só as falhas' action", async () => {
      mockUseEvalRuns.mockReturnValue({ data: [CONCLUDED_RUN] });
      await renderTab();
      expect(screen.queryByTestId("evals-run-repeat-r1")).toBeNull();
    });
  });
});
