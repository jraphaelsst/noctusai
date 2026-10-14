/** Condominios page — loading / empty / error / data states, filters, admin gating. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { mockLista, mockSugerir, isAdminRef } = vi.hoisted(() => ({
  mockLista: vi.fn(),
  mockSugerir: vi.fn(),
  isAdminRef: { current: true },
}));

vi.mock("@noctusai/lib/design-system", async () => ({
  ...(await vi.importActual<typeof import("@noctusai/lib/design-system")>("@noctusai/lib/design-system")),
  useEffectiveSSOContext: () => ({}),
}));
vi.mock("@noctusai/lib", () => ({ isOrgAdmin: () => isAdminRef.current }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/components/condominios/CondominioDetalhe", () => ({
  CondominioDetalhe: ({ condominioId }: { condominioId: string | null }) =>
    condominioId ? <div data-testid="detalhe-aberto">{condominioId}</div> : null,
}));
vi.mock("@/hooks/useCondominios", async () => ({
  ...(await vi.importActual<typeof import("@/hooks/useCondominios")>("@/hooks/useCondominios")),
  useCondominios: (...a: unknown[]) => mockLista(...a),
  useSugerirCondominios: () => ({ mutate: mockSugerir, isPending: false }),
}));

function q(over: Record<string, unknown> = {}) {
  return { data: undefined, isPending: false, isFetching: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

const LINHA = {
  id: "c1", nome: "Vila Verde", nome_normalizado: "VILA VERDE", cidade: "Cotia", bairro: "Granja Viana",
  tipo: null, status_validacao: "sugerido", latitude: null, longitude: null, seguranca_nivel: null,
  portaria_24h: null, area_lazer: null, distancia_raposo_km: null, acesso_principal: null, observacoes: null,
  fundido_em_id: null, validado_em: null, imoveis_count: 12, anuncios_venda_count: 10,
  preco_m2_mediano: 8500, aliases_count: 3,
};

async function render() {
  const { render: r } = await import("@testing-library/react");
  const { default: Condominios } = await import("./Condominios");
  return r(<Condominios />);
}

beforeEach(() => {
  vi.clearAllMocks();
  isAdminRef.current = true;
  mockLista.mockReturnValue(q({ data: [] }));
});

describe("Condominios page", () => {
  it("mostra skeleton enquanto carrega sem dados", async () => {
    mockLista.mockReturnValue(q({ isPending: true }));
    const { getByTestId } = await render();
    expect(getByTestId("condominios-skeleton")).toBeTruthy();
  });

  it("mostra estado vazio com a dica de gerar sugestões para admin", async () => {
    const { getByTestId } = await render();
    expect(getByTestId("condominios-vazio").textContent).toContain("Gerar sugestões");
  });

  it("mostra o erro quando a lista falha sem dados", async () => {
    mockLista.mockReturnValue(q({ isError: true, error: new Error("boom") }));
    const { getByRole } = await render();
    expect(getByRole("alert").textContent).toContain("boom");
  });

  it("renderiza a tabela e abre o detalhe ao clicar", async () => {
    mockLista.mockReturnValue(q({ data: [LINHA] }));
    const { getByText, getByTestId, queryByTestId } = await render();
    const { within } = await import("@testing-library/react");
    expect(getByText("Vila Verde")).toBeTruthy();
    expect(getByText("Cotia / Granja Viana")).toBeTruthy();
    expect(within(getByTestId("condominio-linha-c1")).getByText("Sugerido")).toBeTruthy();
    expect(queryByTestId("detalhe-aberto")).toBeNull();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("condominio-linha-c1"));
    expect(getByTestId("detalhe-aberto").textContent).toBe("c1");
  });

  it("não troca por skeleton durante um refetch com dados", async () => {
    mockLista.mockReturnValue(q({ data: [LINHA], isFetching: true }));
    const { queryByTestId, getByText } = await render();
    expect(queryByTestId("condominios-skeleton")).toBeNull();
    expect(getByText("Vila Verde")).toBeTruthy();
  });

  it("o botão Gerar sugestões é só de admin e dispara a mutation", async () => {
    const { getByText, queryByText } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByText("Gerar sugestões"));
    expect(mockSugerir).toHaveBeenCalledTimes(1);
  });

  it("membro comum não vê o botão", async () => {
    isAdminRef.current = false;
    const { queryByText } = await render();
    expect(queryByText("Gerar sugestões")).toBeNull();
  });

  it("filtro de status chega ao hook", async () => {
    const { getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(getByLabelText("Filtrar por status"), { target: { value: "validado" } });
    expect(mockLista).toHaveBeenCalledWith(expect.objectContaining({ status: "validado" }));
  });
});
