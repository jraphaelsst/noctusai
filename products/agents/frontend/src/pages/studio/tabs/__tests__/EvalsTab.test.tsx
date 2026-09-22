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
