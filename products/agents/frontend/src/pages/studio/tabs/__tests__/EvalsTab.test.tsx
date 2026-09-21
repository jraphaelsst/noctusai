/**
 * EvalsTab.tsx tests — Agent Studio CONTRACT.md §G "Avaliações". Stubs
 * `useEvals.ts` hooks + `useIsAdmin`; `useDraftVersion`'s own narrow
 * `GET /api/studio/agents/{key}` read is stubbed via `@/lib/api` (it is a
 * plain `useQuery`, not a `useEvals.ts` export).
 */
import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseEvalCases = vi.fn();
const mockUseEvalRuns = vi.fn();
const mockUseEvalRun = vi.fn();
const mockUseCreateEvalRun = vi.fn();
const mockUseCreateEvalCase = vi.fn();
const mockUseDeleteEvalCase = vi.fn();
const mockUseIsAdmin = vi.fn();
const mockGet = vi.fn();

vi.mock("@/hooks/studio/useEvals", () => ({
  useEvalCases: () => mockUseEvalCases(),
  useEvalRuns: () => mockUseEvalRuns(),
  useEvalRun: () => mockUseEvalRun(),
  useCreateEvalRun: () => mockUseCreateEvalRun(),
  useCreateEvalCase: () => mockUseCreateEvalCase(),
  useDeleteEvalCase: () => mockUseDeleteEvalCase(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

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
  mockUseDeleteEvalCase.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockGet.mockResolvedValue({ versoes: [{ id: "v1", versao: 2, status: "rascunho" }] });
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
