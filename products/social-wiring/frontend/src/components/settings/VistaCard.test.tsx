/**
 * VistaCard.test.tsx — the four states, write-only key, "Testar conexão", confirmed remove.
 * Mock-the-hook pattern (see TestemunhasSection.test.tsx): no QueryClientProvider needed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUse = vi.fn();
const mockSalvar = vi.fn();
const mockRemover = vi.fn();
const mockTestar = vi.fn();

vi.mock("@/hooks/useVistaIntegracao", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useVistaIntegracao")>("@/hooks/useVistaIntegracao");
  return {
    ...actual,
    useVistaIntegracao: mockUse,
    useSalvarVista: () => ({ mutate: mockSalvar, isPending: false }),
    useRemoverVista: () => ({ mutate: mockRemover, isPending: false }),
    useTestarVista: () => ({ mutate: mockTestar, isPending: false }),
  };
});

vi.mock("@/components/settings/DivergenciasAvisos", () => ({ DivergenciasAvisos: () => <div data-testid="divergencias-stub" /> }));

const CONFIGURADA = {
  configurado: true,
  base_url: "https://acme-rest.vistahost.com.br",
  chave_final: "644c",
  verificado_em: "2026-11-03T12:00:00Z",
};

function estado(over: Record<string, unknown> = {}) {
  return { data: CONFIGURADA, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(), ...over };
}

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { VistaCard } = await import("./VistaCard");
  return rtlRender(<VistaCard />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUse.mockReturnValue(estado());
});

describe("estados", () => {
  it("mostra o esqueleto só no primeiro carregamento", async () => {
    mockUse.mockReturnValue(estado({ data: undefined, showSkeleton: true }));
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("vista-skeleton")).toBeTruthy();
    expect(queryByTestId("vista-form")).toBeNull();
  });

  it("distingue falha de carregamento de 'não configurada' e oferece tentar de novo", async () => {
    const refetch = vi.fn();
    mockUse.mockReturnValue(estado({ data: undefined, isError: true, refetch }));
    const { getByTestId, getByText, queryByTestId } = await render();
    expect(getByTestId("vista-error")).toBeTruthy();
    expect(queryByTestId("vista-chip")).toBeNull();
    getByText("Tentar novamente").click();
    expect(refetch).toHaveBeenCalled();
  });

  it("não configurada: chip de alerta, sem testar/remover", async () => {
    mockUse.mockReturnValue(estado({ data: { configurado: false, base_url: null, chave_final: null, verificado_em: null } }));
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("vista-chip").textContent).toContain("Não configurada");
    expect(queryByTestId("vista-test-btn")).toBeNull();
    expect(queryByTestId("vista-remove-btn")).toBeNull();
  });

  it("configurada: chip com os 4 últimos e a data; nunca a chave inteira", async () => {
    const { getByTestId, container } = await render();
    expect(getByTestId("vista-chip").textContent).toMatch(/Conectada · chave …644c · verificada em /);
    expect(getByTestId("vista-base-url").textContent).toBe("https://acme-rest.vistahost.com.br");
    expect((getByTestId("vista-api-key-input") as HTMLInputElement).value).toBe("");
    expect(container.textContent).not.toMatch(/feedface/);
  });

  it("um refetch não desmonta o card", async () => {
    mockUse.mockReturnValue(estado({ isRefreshing: true }));
    const { getByTestId } = await render();
    expect(getByTestId("vista-chip")).toBeTruthy();
    expect(getByTestId("vista-refreshing")).toBeTruthy();
  });
});

describe("chave write-only", () => {
  it("o campo da chave é password e o salvar fica desabilitado sem os dois campos", async () => {
    const { getByTestId } = await render();
    expect((getByTestId("vista-api-key-input") as HTMLInputElement).type).toBe("password");
    expect((getByTestId("vista-save-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("envia endereço + chave e limpa a chave digitada ao salvar", async () => {
    const { fireEvent } = await import("@testing-library/react");
    mockSalvar.mockImplementation((_corpo, opts) => opts?.onSuccess?.());
    const { getByTestId } = await render();
    fireEvent.change(getByTestId("vista-base-url-input"), { target: { value: " https://acme-rest.vistahost.com.br " } });
    fireEvent.change(getByTestId("vista-api-key-input"), { target: { value: "nova-chave-123" } });
    fireEvent.submit(getByTestId("vista-form"));
    expect(mockSalvar).toHaveBeenCalledTimes(1);
    expect(mockSalvar.mock.calls[0][0]).toEqual({ base_url: "https://acme-rest.vistahost.com.br", api_key: "nova-chave-123" });
    expect((getByTestId("vista-api-key-input") as HTMLInputElement).value).toBe("");
  });
});

describe("testar e remover", () => {
  it("'Testar conexão' mostra o resultado inline", async () => {
    const { fireEvent } = await import("@testing-library/react");
    mockTestar.mockImplementation((_v, opts) => opts?.onSuccess?.({ ok: true, mensagem: "Conexão com o Vista funcionando." }));
    const { getByTestId } = await render();
    fireEvent.click(getByTestId("vista-test-btn"));
    expect(mockTestar).toHaveBeenCalled();
    expect(getByTestId("vista-test-result").textContent).toBe("Conexão com o Vista funcionando.");
  });

  it("remover pede confirmação antes de chamar a API", async () => {
    const { fireEvent, screen } = await import("@testing-library/react");
    const { getByTestId } = await render();
    fireEvent.click(getByTestId("vista-remove-btn"));
    expect(mockRemover).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("vista-remove-confirm"));
    expect(mockRemover).toHaveBeenCalledTimes(1);
  });
});
