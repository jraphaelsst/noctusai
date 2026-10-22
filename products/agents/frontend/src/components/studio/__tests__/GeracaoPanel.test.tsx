import React from "react";
import { cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { GeracaoPanel } from "../GeracaoPanel";
import { CompletudeCard, GeradoBadge } from "../CompletudeCard";
import { GERACAO_POLL_MS, useItensGerados } from "@/hooks/studio/useGeracoes";
import type { GeracaoAreaOut, GeracaoOut } from "@/api/studio/types-geracao";

const area = (a: Partial<GeracaoAreaOut> & Pick<GeracaoAreaOut, "area">): GeracaoAreaOut => ({
  status: "concluida", erro: null, custo_usd: 0.5, itens_escritos: 1, itens: [], lacunas: [], concluido_em: null, ...a,
});
const run = (over: Partial<GeracaoOut> = {}): GeracaoOut => ({
  id: "g1", agent_key: "ag", status: "executando", versao_gerador: 3, modelo: "claude-opus-5",
  briefing: { nome: "Ag", objetivo: "Atender clientes", publico: "Clientes", canal: "web" },
  custo_usd: 1.25, limite_usd: 5, criado_em: "2026-10-22T10:00:00Z", iniciado_em: null, concluido_em: null, erro: null,
  areas: [area({ area: "secoes" }), area({ area: "textos", status: "falhou", erro: "boom", lacunas: ["skill X ausente"] })],
  ...over,
});

function wrap(qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) {
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(ui, { wrapper: wrap(qc) });
  return qc;
}
const detailCalls = () => get.mock.calls.filter((c) => String(c[0]).endsWith("/geracoes/g1")).length;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("GeracaoPanel", () => {
  it("renders per-area status, cost, lacunas, total vs limit and gerador/modelo", async () => {
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [run({ status: "parcial" })] } : run({ status: "parcial" })));
    mount(<GeracaoPanel agentKey="ag" />);
    expect((await screen.findByTestId("geracao-custo")).textContent).toBe("US$ 1.25 de US$ 5.00");
    expect(screen.getByTestId("geracao-gerador").textContent).toMatch(/claude-opus-5.*v3/);
    expect(screen.getByTestId("geracao-area-status-textos").textContent).toBe("Falhou");
    expect(screen.getByTestId("geracao-lacunas-textos").textContent).toMatch(/skill X ausente/);
  });

  it("polls while executando and stops once the run is terminal", async () => {
    let n = 0;
    get.mockImplementation(async (url: string) => {
      if (url.endsWith("/geracoes")) return { items: [run()] };
      n += 1;
      return run({ status: n >= 2 ? "concluida" : "executando" });
    });
    mount(<GeracaoPanel agentKey="ag" />);
    await waitFor(() => expect(detailCalls()).toBe(1));
    await vi.advanceTimersByTimeAsync(GERACAO_POLL_MS + 100);
    await waitFor(() => expect(screen.getByTestId("geracao-status").textContent).toBe("Concluída"));
    const settled = detailCalls();
    await vi.advanceTimersByTimeAsync(GERACAO_POLL_MS * 3);
    expect(detailCalls()).toBe(settled);
    expect(screen.queryByTestId("geracao-cancelar")).toBeNull();
  });

  it("cancels the active run with the server's answer", async () => {
    let atual = run();
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [atual] } : atual));
    post.mockImplementation(async () => (atual = run({ status: "cancelada" })));
    mount(<GeracaoPanel agentKey="ag" />);
    fireEvent.click(await screen.findByTestId("geracao-cancelar"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/studio/agents/ag/geracoes/g1/cancelar", {}));
    await waitFor(() => expect(screen.getByTestId("geracao-status").textContent).toBe("Cancelada"));
  });

  it("repeats a failed area; a concluded area needs an in-UI confirm and sends forcar", async () => {
    const done = run({ status: "parcial" });
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [done] } : done));
    post.mockResolvedValue(run());
    mount(<GeracaoPanel agentKey="ag" />);
    fireEvent.click(await screen.findByTestId("geracao-repetir-textos"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/studio/agents/ag/geracoes/g1/areas/textos/repetir", { forcar: false }));
    cleanup();
    post.mockClear();
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [done] } : done));
    mount(<GeracaoPanel agentKey="ag" />);
    fireEvent.click(await screen.findByTestId("geracao-repetir-secoes"));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("geracao-repetir-confirmar-secoes"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/studio/agents/ag/geracoes/g1/areas/secoes/repetir", { forcar: true }));
  });

  it("maps a 409 to the flat body message and offers a forcar retry for conteudo_editado", async () => {
    const done = run({ status: "parcial" });
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [done] } : done));
    post.mockRejectedValueOnce(new ApiError(409, "Erro HTTP 409", { code: "conteudo_editado", message: "Há textos editados à mão.", detail: ["textos"] }));
    post.mockResolvedValueOnce(run());
    mount(<GeracaoPanel agentKey="ag" />);
    fireEvent.click(await screen.findByTestId("geracao-repetir-textos"));
    expect((await screen.findByTestId("geracao-falha")).textContent).toMatch(/Há textos editados à mão\./);
    fireEvent.click(screen.getByTestId("geracao-falha-forcar"));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith("/api/studio/agents/ag/geracoes/g1/areas/textos/repetir", { forcar: true }));
  });

  it("starts a run on an existing agent with the shared briefing form, retrying with forcar on conteudo_editado", async () => {
    get.mockResolvedValue({ items: [] });
    post.mockRejectedValueOnce(new ApiError(409, "Erro HTTP 409", { code: "conteudo_editado", message: "Conteúdo editado.", detail: ["textos"] }));
    post.mockResolvedValueOnce(run());
    mount(<GeracaoPanel agentKey="ag" />);
    expect(await screen.findByTestId("geracao-vazio")).toBeTruthy();
    fireEvent.click(screen.getByTestId("geracao-abrir-form"));
    fireEvent.change(screen.getByLabelText(/Objetivo/), { target: { value: "Atender clientes" } });
    fireEvent.change(screen.getByLabelText(/Público/), { target: { value: "Clientes" } });
    fireEvent.change(screen.getByLabelText(/Canal/), { target: { value: "web" } });
    fireEvent.change(screen.getByLabelText(/Nome do agente/), { target: { value: "Ag" } });
    fireEvent.click(screen.getByTestId("geracao-form-submit"));
    fireEvent.click(await screen.findByTestId("geracao-form-forcar"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toMatchObject({ forcar: true, briefing: { nome: "Ag", canal: "web" } });
  });

  it("shows an error state with retry when the run list fails", async () => {
    get.mockRejectedValue(new ApiError(500, "falha", {}));
    mount(<GeracaoPanel agentKey="ag" />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("badges and completeness", () => {
  it("useItensGerados keys items by area + chave; GeradoBadge labels gerado / editado", async () => {
    const g = run({ areas: [area({ area: "textos", itens: [{ chave: "a.b", estado: "gerado" }, { chave: "c.d", estado: "editado" }] })] });
    get.mockImplementation(async (url: string) => (url.endsWith("/geracoes") ? { items: [g] } : g));
    const { result } = renderHook(() => useItensGerados("ag"), { wrapper: wrap() });
    await waitFor(() => expect(result.current.textos).toEqual({ "a.b": "gerado", "c.d": "editado" }));
    expect(result.current.secoes).toBeUndefined();
    render(<><GeradoBadge estado="gerado" /><GeradoBadge estado="editado" /><GeradoBadge estado={undefined} /></>);
    expect(screen.getByTestId("gerado-gerado").textContent).toBe("Gerado por IA");
    expect(screen.getByTestId("gerado-editado").textContent).toBe("Gerado · editado");
  });

  it("CompletudeCard shows N de M and the missing list, and hides on null", () => {
    const { rerender } = render(<CompletudeCard status={{ textos_preenchidos: 3, textos_total: 8, obrigatorios_faltando: ["a.b"] }} />);
    expect(screen.getByTestId("completude-contagem").textContent).toBe("3 de 8 textos");
    expect(screen.getByTestId("completude-faltando").textContent).toMatch(/a\.b/);
    rerender(<CompletudeCard status={null} />);
    expect(screen.queryByTestId("completude-card")).toBeNull();
  });
});
