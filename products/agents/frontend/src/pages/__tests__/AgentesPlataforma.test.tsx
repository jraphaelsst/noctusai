import React from "react";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const view = (over: object) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, isPlaceholderData: false, isFetching: false, failureCount: 0, refetch: vi.fn(), ...over });
const mockLista = vi.fn();
const mockDetalhe = vi.fn();
const mockModelos = vi.fn();
const salvar = vi.fn();
const confirm = vi.fn();

vi.mock("@/hooks/usePlataformaAgentes", async (orig) => ({
  ...(await orig<typeof import("@/hooks/usePlataformaAgentes")>()),
  usePlataformaAgentes: () => mockLista(),
  usePlataformaAgente: (c: string | null) => mockDetalhe(c),
  usePlataformaModelos: (v: string) => mockModelos(v),
  useSalvarPlataformaAgente: () => ({ mutate: salvar, isPending: false, isError: false, reset: vi.fn() }),
}));
vi.mock("@noctusai/lib/components", async (orig) => ({ ...(await orig<object>()), useConfirm: () => confirm }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AgentesPlataforma from "../AgentesPlataforma";

const linha = (over: object = {}) => ({ chave: "agents.eval_improver", nome: "Avaliador", descricao: "d", vendor: "anthropic", modelo: "claude-sonnet-4-6", capacidade: "texto", ativo: true, atualizado_em: null, atualizado_por: null, ...over });
const detalhe = (over: object = {}) => ({ ...linha(), prompt: "Prompt original", estatisticas: [], ...over });
const MODELOS: Record<string, object[]> = {
  anthropic: [{ vendor: "anthropic", modelo: "claude-sonnet-4-6", nome: "Claude Sonnet 4.6" }, { vendor: "anthropic", modelo: "claude-haiku-4-5", nome: "Claude Haiku 4.5" }],
  openai: [{ vendor: "openai", modelo: "gpt-4o", nome: "GPT-4o" }],
};

beforeEach(() => {
  mockLista.mockReturnValue(view({ data: [linha(), linha({ chave: "agents.outro", nome: "Outro" })] }));
  mockDetalhe.mockImplementation((c: string | null) => (c ? view({ data: detalhe({ chave: c }) }) : view({})));
  mockModelos.mockImplementation((v: string) => view({ data: MODELOS[v] }));
  confirm.mockResolvedValue(true);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function abrir(q: ReturnType<typeof within>) {
  fireEvent.click(q.getByTestId("plat-item-agents.eval_improver"));
  return q.findByTestId("plat-editor");
}

describe("AgentesPlataforma", () => {
  it("shows a skeleton while loading and a retry state on error", () => {
    mockLista.mockReturnValue(view({ showSkeleton: true }));
    const a = render(<AgentesPlataforma />);
    expect(within(a.container).getByTestId("plat-lista-skeleton")).toBeTruthy();
    cleanup();
    mockLista.mockReturnValue(view({ isError: true, error: new ApiError(500, "x") }));
    const b = render(<AgentesPlataforma />);
    expect(within(b.container).getByRole("alert").textContent).toContain("Não foi possível carregar");
  });

  it("list -> select -> edit -> save sends only the changed prompt", async () => {
    const { container } = render(<AgentesPlataforma />);
    const q = within(container);
    await abrir(q);
    const save = q.getByTestId("plat-salvar") as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(q.getByTestId("plat-prompt"), { target: { value: "Novo prompt" } });
    expect(q.getByTestId("plat-nao-salvo")).toBeTruthy();
    fireEvent.click(q.getByTestId("plat-salvar"));
    expect(salvar).toHaveBeenCalledTimes(1);
    expect(salvar.mock.calls[0][0]).toEqual({ chave: "agents.eval_improver", patch: { prompt: "Novo prompt" } });
  });

  it("vendor change resets the model to the vendor's first and sends vendor+modelo together", async () => {
    const { container } = render(<AgentesPlataforma />);
    const q = within(container);
    await abrir(q);
    fireEvent.change(q.getByTestId("plat-vendor"), { target: { value: "openai" } });
    expect((q.getByTestId("plat-modelo") as HTMLSelectElement).value).toBe("gpt-4o");
    fireEvent.click(q.getByTestId("plat-salvar"));
    expect(salvar.mock.calls[0][0].patch).toEqual({ vendor: "openai", modelo: "gpt-4o" });
  });

  it("shows a 422 modelo_invalido inline under Modelo", async () => {
    salvar.mockImplementation((_v, opts) => opts.onError(new ApiError(422, "x", { code: "modelo_invalido" })));
    const { container } = render(<AgentesPlataforma />);
    const q = within(container);
    await abrir(q);
    fireEvent.change(q.getByTestId("plat-prompt"), { target: { value: "x" } });
    fireEvent.click(q.getByTestId("plat-salvar"));
    await waitFor(() => expect(q.getByTestId("plat-modelo-erro").textContent).toContain("não é válido"));
    expect(q.getByTestId("plat-modelo").getAttribute("aria-invalid")).toBe("true");
  });

  it("asks before switching agents with a draft, and Descartar restores the saved values", async () => {
    const { container } = render(<AgentesPlataforma />);
    const q = within(container);
    await abrir(q);
    fireEvent.change(q.getByTestId("plat-prompt"), { target: { value: "rascunho" } });
    confirm.mockResolvedValueOnce(false);
    fireEvent.click(q.getByTestId("plat-item-agents.outro"));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect((q.getByTestId("plat-prompt") as HTMLTextAreaElement).value).toBe("rascunho");
    fireEvent.click(q.getByTestId("plat-descartar"));
    expect((q.getByTestId("plat-prompt") as HTMLTextAreaElement).value).toBe("Prompt original");
    expect(q.queryByTestId("plat-nao-salvo")).toBeNull();
  });
});
