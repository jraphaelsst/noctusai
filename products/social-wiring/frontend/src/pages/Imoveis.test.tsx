/**
 * Imoveis (listing page) — CONTRACT § 6 additions.
 *
 * Scoped to the new card surface: condomínio/IPTU compact line, the
 * true-only badges, and the Pencil placeholder button (fires the toast,
 * never a mutation — CONTRACT § 4).
 *
 * Query hooks are mocked; the real formatters/labels come through via
 * `importOriginal` so `formatValor`/`caracteristicaLabel`/etc. behave
 * exactly as they do in production.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseImoveis = vi.fn();
const mockUseImovelFiltros = vi.fn();
const mockUseCaracteristicas = vi.fn();
const mockUseSyncImoveis = vi.fn();

vi.mock("@/hooks/useImoveis", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImoveis")>();
  return {
    ...actual,
    useImoveis: mockUseImoveis,
    useImovelFiltros: mockUseImovelFiltros,
    useCaracteristicas: mockUseCaracteristicas,
    useSyncImoveis: mockUseSyncImoveis,
  };
});

// The "Cadastrar imóvel" modal owns real mutations (QueryClient) — inert here;
// its behaviour lives in `ImovelManualModal.test.tsx`.
vi.mock("@/hooks/useImovelManual", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImovelManual")>();
  return {
    ...actual,
    useCriarImovelManual: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useAtualizarImovelManual: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

const mockToastInfo = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    info: (...a: unknown[]) => mockToastInfo(...a),
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

import type { Imovel, ImovelPage } from "@/hooks/useImoveis";

function makeImovel(overrides: Partial<Imovel> = {}): Imovel {
  return {
    codigo: "AP1234",
    codigo_imobiliaria: null,
    titulo: "Apartamento no centro",
    categoria: "Apartamento",
    status: "Ativo",
    finalidades: ["venda"],
    cep: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: "Centro",
    cidade: "Porto Alegre",
    uf: "RS",
    empreendimento: null,
    latitude: null,
    longitude: null,
    valor_venda: 500000,
    valor_locacao: null,
    area_total: null,
    area_privativa: null,
    area_construida: null,
    dormitorios: 2,
    suites: null,
    vagas: 1,
    banheiro_social: null,
    foto_destaque: null,
    fotos: [],
    corretores: [],
    construtora: null,
    data_cadastro: null,
    data_atualizacao: null,
    caracteristicas: [],
    sincronizado_em: null,
    descricao_web: null,
    observacoes: null,
    valor_condominio: null,
    valor_iptu: null,
    ano_construcao: null,
    situacao: null,
    ocupacao: null,
    pavimentos: null,
    posicao: null,
    elevador: null,
    portaria: null,
    exclusivo: null,
    aceita_permuta: null,
    aceita_financiamento: null,
    destaque_web: null,
    super_destaque_web: null,
    exibir_no_site: null,
    chave: null,
    zona: null,
    regiao: null,
    area_terreno: null,
    closet: null,
    frente: null,
    fundos: null,
    referencia: null,
    matricula_vista: null,
    inscricao_municipal: null,
    video_destaque: null,
    tour_360: null,
    dias_desde_atualizacao: null,
    orientacao_solar: [],
    ...overrides,
  };
}

function makePage(items: Imovel[]): ImovelPage {
  return { items, total: items.length, page: 1, pages: 1 };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseImovelFiltros.mockReturnValue({ data: { status: [], categoria: [], cidade: [], bairro: [] } });
  mockUseCaracteristicas.mockReturnValue({ data: {} });
  mockUseSyncImoveis.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

async function renderImoveis() {
  const React = (await import("react")).default;
  const { default: Imoveis } = await import("./Imoveis");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Imoveis))),
    fireEvent: rtl.fireEvent,
  };
}

describe("Imoveis — card badges (CONTRACT § 6, true-only)", () => {
  it("shows no badges when every flag is false/null", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel()]),
      isPending: false,
      isError: false,
    });
    const { queryByText } = await renderImoveis();

    expect(queryByText("Exclusivo")).toBeNull();
    expect(queryByText("Destaque")).toBeNull();
    expect(queryByText("Aceita permuta")).toBeNull();
    expect(queryByText("Aceita financiamento")).toBeNull();
    expect(queryByText("Tour 360°")).toBeNull();
  });

  it("shows only the badges that are true", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel({ exclusivo: true, tour_360: "https://tour.example/x" })]),
      isPending: false,
      isError: false,
    });
    const { getByText, queryByText } = await renderImoveis();

    expect(getByText("Exclusivo")).toBeTruthy();
    expect(getByText("Tour 360°")).toBeTruthy();
    expect(queryByText("Destaque")).toBeNull();
    expect(queryByText("Aceita permuta")).toBeNull();
  });

  it("shows condomínio + IPTU compactly when present", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel({ valor_condominio: 500, valor_iptu: 1200 })]),
      isPending: false,
      isError: false,
    });
    const { getByText } = await renderImoveis();

    expect(getByText(/Cond\..*IPTU/)).toBeTruthy();
  });

  it("omits the condomínio/IPTU line entirely when both are null", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel()]),
      isPending: false,
      isError: false,
    });
    const { queryByText } = await renderImoveis();

    expect(queryByText(/Cond\./)).toBeNull();
  });
});

describe("Imoveis — card Pencil placeholder (CONTRACT § 4)", () => {
  it("fires the honest-placeholder toast and performs no mutation on click", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel()]),
      isPending: false,
      isError: false,
    });
    const { getByRole, fireEvent } = await renderImoveis();

    fireEvent.click(getByRole("button", { name: "Editar AP1234" }));

    expect(mockToastInfo).toHaveBeenCalledTimes(1);
    expect(mockToastInfo).toHaveBeenCalledWith(
      "Edição via plataforma ainda não disponível — o Vista não expõe rota de escrita. Chega quando migrarmos para o sistema próprio.",
    );
    // The sync mutation is the ONLY mutation this page wires — asserting it
    // was never called is the "no mutation" half of the CONTRACT § 4 rule.
    expect(mockUseSyncImoveis().mutateAsync).not.toHaveBeenCalled();
  });
});


describe("Imoveis — S6 cadastrar imóvel + manual imóvel on the list", () => {
  it("🔴 a manual imóvel (no foto, no preço, no flags) renders a card with a Manual badge and no Vista edit placeholder", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([
        makeImovel({
          codigo: "SW-0001",
          fonte: "manual",
          titulo: "Al. Liverpool 81",
          foto_destaque: null,
          fotos: [],
          valor_venda: null,
          valor_locacao: null,
          dormitorios: null,
          vagas: null,
        }),
      ]),
      isPending: false,
      isError: false,
    });
    const { getByText, getByTestId, queryByLabelText } = await renderImoveis();

    expect(getByText("Al. Liverpool 81")).toBeTruthy();
    expect(getByText("Sob consulta")).toBeTruthy();
    expect(getByTestId("imovel-manual-badge").textContent).toBe("Manual");
    expect(queryByLabelText("Editar SW-0001")).toBeNull();
  });

  it("a Vista card has no Manual badge", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel({ fonte: "vista" })]),
      isPending: false,
      isError: false,
    });
    const { queryByTestId } = await renderImoveis();
    expect(queryByTestId("imovel-manual-badge")).toBeNull();
  });

  it("'Cadastrar imóvel' opens the modal", async () => {
    mockUseImoveis.mockReturnValue({
      data: makePage([makeImovel()]),
      isPending: false,
      isError: false,
    });
    const { getByTestId, queryByTestId, fireEvent } = await renderImoveis();

    expect(queryByTestId("imovel-manual-modal")).toBeNull();
    fireEvent.click(getByTestId("imoveis-cadastrar"));
    expect(getByTestId("imovel-manual-modal")).toBeTruthy();
  });
});
