/** VistaSincronizacao.test.tsx — two switches, validation hint, write unavailable/unknown, refused save surfaced (the WhatsApp digest destination lives in DivergenciasAvisos, kept 2026-11-15). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockCfg = vi.fn();
const mockSalvar = vi.fn();
const salvarState: Record<string, unknown> = { isPending: false, isError: false, error: null };

vi.mock("@/hooks/useVistaDivergenciasConfig", () => ({
  useDivergenciasConfig: mockCfg,
  useSalvarDivergenciasConfig: () => ({ mutate: mockSalvar, ...salvarState }),
}));

function cfg(over: Record<string, unknown> = {}, data: Record<string, unknown> = {}) {
  return {
    data: { ativa: true, vista_escrita_ativa: false, vista_escrita_disponivel: true, ...data },
    showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(), ...over,
  };
}

async function render() {
  const { render: r } = await import("@testing-library/react");
  const { VistaSincronizacao } = await import("./VistaSincronizacao");
  return r(<VistaSincronizacao />);
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(salvarState, { isPending: false, isError: false, error: null });
  mockCfg.mockReturnValue(cfg());
});

describe("VistaSincronizacao", () => {
  it("skeleton e erro de carregamento com tentar de novo", async () => {
    mockCfg.mockReturnValue(cfg({ data: undefined, showSkeleton: true }));
    expect((await render()).getByTestId("divergencias-skeleton")).toBeTruthy();
    (await import("@testing-library/react")).cleanup();
    const refetch = vi.fn();
    mockCfg.mockReturnValue(cfg({ data: undefined, isError: true, refetch }));
    const { getByTestId, getByText } = await render();
    expect(getByTestId("divergencias-error")).toBeTruthy();
    (await import("@testing-library/react")).fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("o Vista prevalece e o texto diz que os avisos do sync são no app, sem e-mail; o destino do resumo não mora aqui", async () => {
    const { getByTestId, queryByTestId, container } = await render();
    expect(getByTestId("sincronizacao-explicacao").textContent).toContain("sem e-mail");
    expect(queryByTestId("divergencias-destino")).toBeNull();
    expect(container.textContent).not.toContain("Quem recebe");
  });

  it("ativa: o interruptor grava só ativa", async () => {
    const { getByTestId } = await render();
    (await import("@testing-library/react")).fireEvent.click(getByTestId("divergencias-toggle"));
    expect(mockSalvar).toHaveBeenCalledWith({ ativa: false });
  });

  it("editar no Vista: desligado por padrão, com a dica de validação, grava só vista_escrita_ativa", async () => {
    const { getByTestId } = await render();
    expect(getByTestId("escrita-toggle").getAttribute("aria-checked")).toBe("false");
    expect(getByTestId("escrita-dica").textContent).toContain("Em validação — mantenha desligado até a Julia estar em operação");
    (await import("@testing-library/react")).fireEvent.click(getByTestId("escrita-toggle"));
    expect(mockSalvar).toHaveBeenCalledWith({ vista_escrita_ativa: true });
  });

  it("chave sem permissão: o interruptor fica desabilitado e explica", async () => {
    mockCfg.mockReturnValue(cfg({}, { vista_escrita_disponivel: false }));
    const { getByTestId } = await render();
    expect((getByTestId("escrita-toggle") as HTMLButtonElement).disabled).toBe(true);
    expect(getByTestId("escrita-indisponivel")).toBeTruthy();
  });

  it("permissão desconhecida (null): diz que não foi possível verificar", async () => {
    mockCfg.mockReturnValue(cfg({}, { vista_escrita_disponivel: null }));
    const { getByTestId } = await render();
    expect(getByTestId("escrita-desconhecida")).toBeTruthy();
    expect((getByTestId("escrita-toggle") as HTMLButtonElement).disabled).toBe(false);
  });

  it("gravação recusada aparece na tela", async () => {
    Object.assign(salvarState, { isError: true, error: new Error("403") });
    const { getByTestId } = await render();
    expect(getByTestId("divergencias-erro-salvar")).toBeTruthy();
  });
});
