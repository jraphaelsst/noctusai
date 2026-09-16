/**
 * Processamento.test.tsx — the platform-admin lock, loading/error/refreshing
 * states, the live pause switch, the loud "sem créditos" banner, the queue
 * health numbers + last error, the worker state, and the OpenAI probe.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseProcessamento = vi.fn();
const mockAtualizar = vi.fn();
const mockSondar = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useProcessamento: (...a: any[]) => mockUseProcessamento(...a),
    useAtualizarProcessamento: () => ({ mutateAsync: mockAtualizar, isPending: false }),
    useSondarOpenAI: () => ({ mutateAsync: mockSondar, isPending: false }),
  };
});

function painel(overrides: Partial<any> = {}) {
  return {
    ativo: false,
    worker: {
      escopo: "este_processo", kill_switch_ativo: true, rodando: true, pausado: true,
      worker_id: "sw-edicao-fotos-host-1", iniciado_em: "2026-09-16T18:00:00Z", motivo_parado: null,
      erro_gate: null, catalogo_atualizado_em: "2026-09-16T18:00:00Z", erro_catalogo: null,
    },
    fila: { pendentes: 7, prontos_para_rodar: 5, em_execucao: 1, lease_expirado: 0, mortos: 2, workers_ativos: ["w-1"] },
    ultimo_erro: { mensagem: "insufficient_quota", tipo_job: "fotos.edit", em: "2026-09-16T18:10:00Z" },
    sem_creditos: false,
    sonda: null,
    ...overrides,
  };
}

function query(overrides: Partial<any> = {}) {
  return { painel: painel(), showSkeleton: false, isRefreshing: false, error: null, refetch: vi.fn(), ...overrides };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Processamento } = await import("./Processamento");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Processamento)), fireEvent: rtl.fireEvent, waitFor: rtl.waitFor };
}

describe("Processamento", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCapacidades.mockReturnValue({ capacidades: { pode_administrar_plataforma: true }, showSkeleton: false });
    mockUseProcessamento.mockReturnValue(query());
    mockAtualizar.mockResolvedValue(painel({ ativo: true }));
    mockSondar.mockResolvedValue({ status: "sem_credito", mensagem: "Sem créditos na conta." });
  });

  it("locks the page for non platform admins", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: { pode_administrar_plataforma: false }, showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("processamento-restrito")).toBeTruthy();
    expect(mockUseProcessamento).not.toHaveBeenCalled();
  });

  it("polls the panel and shows skeleton / error / refreshing states", async () => {
    mockUseProcessamento.mockReturnValue(query({ painel: undefined, showSkeleton: true }));
    const first = await renderPage();
    expect(first.getByTestId("processamento-loading")).toBeTruthy();
    expect(mockUseProcessamento).toHaveBeenCalledWith({ refetchInterval: 15000 });
    first.unmount();

    const refetch = vi.fn();
    mockUseProcessamento.mockReturnValue(query({ painel: undefined, error: new Error("x"), refetch }));
    const second = await renderPage();
    second.fireEvent.click(second.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
    second.unmount();

    mockUseProcessamento.mockReturnValue(query({ isRefreshing: true }));
    const third = await renderPage();
    expect(third.getByTestId("processamento-atualizando")).toBeTruthy();
    expect(third.getByTestId("fila")).toBeTruthy();
  });

  it("shows the paused worker, queue numbers and last error", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("worker-estado").textContent).toContain("Rodando — pausado");
    expect(getByTestId("fila").textContent).toContain("7");
    expect(getByTestId("fila").textContent).toContain("Mortos (dead-letter)");
    expect(getByTestId("ultimo-erro").textContent).toContain("insufficient_quota");
    expect(getByTestId("interruptor").textContent).toContain("Pausado");
  });

  it("resumes processing from the switch", async () => {
    const { getByLabelText, fireEvent, waitFor } = await renderPage();
    fireEvent.click(getByLabelText("Processamento ativo"));
    await waitFor(() => expect(mockAtualizar).toHaveBeenCalledWith({ ativo: true }));
  });

  it("shows 'sem créditos' loudly and the probe result", async () => {
    mockUseProcessamento.mockReturnValue(query({
      painel: painel({
        sem_creditos: true,
        sonda: { status: "sem_credito", mensagem: "Sem créditos na conta.", verificado_em: "2026-09-16T18:00:00Z",
                 modelo: "gpt-4o-mini", http_status: 429 },
      }),
    }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("sem-creditos").textContent).toContain("Sem créditos na OpenAI");
    expect(getByTestId("sonda-resultado").textContent).toContain("Sem créditos");
  });

  it("runs the OpenAI probe on click", async () => {
    const { getByText, fireEvent, waitFor } = await renderPage();
    fireEvent.click(getByText("Testar chave OpenAI"));
    await waitFor(() => expect(mockSondar).toHaveBeenCalled());
  });

  it("explains a worker stopped by the kill switch", async () => {
    mockUseProcessamento.mockReturnValue(query({
      painel: painel({ worker: { ...painel().worker, kill_switch_ativo: false, rodando: false,
                                 motivo_parado: "Desligado pela variável EDICAO_FOTOS_WORKER_ENABLED=false." } }),
    }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("worker-estado").textContent).toContain("Desligado (variável de ambiente)");
    expect(getByTestId("worker").textContent).toContain("EDICAO_FOTOS_WORKER_ENABLED");
  });
});
