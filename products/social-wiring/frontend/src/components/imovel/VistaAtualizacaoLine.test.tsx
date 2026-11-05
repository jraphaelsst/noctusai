/**
 * VistaAtualizacaoLine.test.tsx — "Última atualização do Vista": the four states, the path/counts, admin-only button, the
 * hand-off to polling (queued job) and the finish toast. Mock-the-hook pattern; no QueryClientProvider besides the line's own.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock("sonner", () => ({ toast }));

const mockUltima = vi.fn();
const mockMutateAsync = vi.fn();
const invalidate = vi.fn();

vi.mock("@/hooks/useImoveis", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useImoveis")>()),
  useUltimaAtualizacaoVista: mockUltima,
  useAtualizarVista: () => ({ mutateAsync: mockMutateAsync, isPending: false }),
  useInvalidarImoveis: () => invalidate,
}));

const BASE = {
  execucao_id: "e1", em_andamento: false, status: "ok", caminho: "detalhes", origem: "agendado",
  iniciado_em: "2026-11-04T01:00:00Z", finalizado_em: "2026-11-04T01:05:00Z",
  novos: 2, atualizados: 30, inalterados: 900, removidos: 1, falhas: 0, chamadas: { detalhes: 933 }, sincronizado_em: "2026-11-04T01:05:00Z",
};

function estado(over: Record<string, unknown> = {}, data: Record<string, unknown> | null = BASE) {
  return {
    data: data === null ? undefined : { ...BASE, ...data }, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(), ...over,
  };
}

async function render(podeAtualizar = true) {
  const { render: rtlRender } = await import("@testing-library/react");
  const { default: Line } = await import("./VistaAtualizacaoLine");
  return rtlRender(<Line podeAtualizar={podeAtualizar} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUltima.mockReturnValue(estado());
});

describe("estados", () => {
  it("carregando só na primeira carga", async () => {
    mockUltima.mockReturnValue(estado({ showSkeleton: true }, null));
    const { getByTestId } = await render();
    expect(getByTestId("vista-linha-carregando")).toBeTruthy();
  });

  it("falha de leitura é um aviso com tentar de novo, não silêncio", async () => {
    const refetch = vi.fn();
    mockUltima.mockReturnValue(estado({ isError: true, refetch }, null));
    const { getByTestId, getByText } = await render();
    expect(getByTestId("vista-linha-erro")).toBeTruthy();
    getByText("Tentar de novo").click();
    expect(refetch).toHaveBeenCalled();
  });

  it("sem nenhuma execução registrada mostra a data do espelho", async () => {
    mockUltima.mockReturnValue(estado({}, { execucao_id: null, sincronizado_em: "2026-10-23T00:00:00Z" }));
    const { getByTestId } = await render();
    expect(getByTestId("vista-linha-sem-execucao").textContent).toMatch(/Última atualização do Vista/);
  });

  it("mostra quando, por qual caminho e os contadores", async () => {
    const { getByTestId } = await render();
    const t = getByTestId("vista-linha-resumo").textContent ?? "";
    expect(t).toMatch(/Última atualização do Vista/);
    expect(t).toMatch(/imóvel a imóvel/);
    expect(t).toMatch(/2 novos · 30 atualizados · 1 removidos · 0 falhas/);
  });

  it("um status ruim nunca parece limpo", async () => {
    mockUltima.mockReturnValue(estado({}, { status: "listar_vazio" }));
    const { getByTestId } = await render();
    expect(getByTestId("vista-linha-alerta").textContent).toMatch(/não listou/);
  });

  it("um refetch por cima de dados não desmonta a linha", async () => {
    mockUltima.mockReturnValue(estado({ isRefreshing: true }));
    const { getByTestId } = await render();
    expect(getByTestId("vista-linha-resumo")).toBeTruthy();
    expect(getByTestId("vista-linha-atualizando")).toBeTruthy();
  });
});

describe("atualizar agora", () => {
  it("só admin vê o botão", async () => {
    const { queryByTestId } = await render(false);
    expect(queryByTestId("vista-atualizar-agora")).toBeNull();
  });

  it("enfileira (modo auto) e avisa que começou", async () => {
    mockMutateAsync.mockResolvedValue({ execucao_id: "e2", status: "em_andamento", ja_em_andamento: false });
    const { getByTestId } = await render();
    getByTestId("vista-atualizar-agora").click();
    await vi.waitFor(() => expect(toast.info).toHaveBeenCalled());
    expect(mockMutateAsync).toHaveBeenCalledWith({ modo: "auto" });
    expect(toast.info.mock.calls[0][0]).toMatch(/iniciada/);
  });

  it("um segundo clique durante a execução diz que já existe uma", async () => {
    mockMutateAsync.mockResolvedValue({ execucao_id: "e1", status: "em_andamento", ja_em_andamento: true });
    const { getByTestId } = await render();
    getByTestId("vista-atualizar-agora").click();
    await vi.waitFor(() => expect(toast.info).toHaveBeenCalled());
    expect(toast.info.mock.calls[0][0]).toMatch(/Já existe/);
  });

  it("uma recusa do servidor aparece (nunca silêncio)", async () => {
    mockMutateAsync.mockRejectedValue(new Error("Vista não configurada para esta empresa"));
    const { getByTestId } = await render();
    getByTestId("vista-atualizar-agora").click();
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Vista não configurada para esta empresa"));
  });

  it("durante a execução mostra 'Atualizando' e desabilita o botão", async () => {
    mockUltima.mockReturnValue(estado({}, { em_andamento: true, status: "em_andamento" }));
    const { getByTestId } = await render();
    expect(getByTestId("vista-linha-resumo").textContent).toMatch(/Atualizando agora/);
    expect((getByTestId("vista-atualizar-agora") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("hand-off para o polling", () => {
  it("quando a execução termina: refaz a lista e avisa o resultado", async () => {
    mockUltima.mockReturnValue(estado({}, { em_andamento: true, status: "em_andamento" }));
    const { rerender } = await render();
    mockUltima.mockReturnValue(estado({}, { em_andamento: false, status: "ok" }));
    const { default: Line } = await import("./VistaAtualizacaoLine");
    rerender(<Line podeAtualizar />);
    expect(invalidate).toHaveBeenCalled();
    expect(toast.success.mock.calls[0][0]).toMatch(/Imóveis atualizados/);
  });

  it("terminar com falhas é um aviso, não um sucesso", async () => {
    mockUltima.mockReturnValue(estado({}, { em_andamento: true, status: "em_andamento" }));
    const { rerender } = await render();
    mockUltima.mockReturnValue(estado({}, { em_andamento: false, status: "incompleto", falhas: 3 }));
    const { default: Line } = await import("./VistaAtualizacaoLine");
    rerender(<Line podeAtualizar />);
    expect(toast.warning.mock.calls[0][0]).toMatch(/terminou com falhas/);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("não dispara nada se nunca esteve em andamento", async () => {
    await render();
    expect(invalidate).not.toHaveBeenCalled();
  });
});
