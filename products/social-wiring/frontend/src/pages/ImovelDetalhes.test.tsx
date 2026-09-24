/**
 * ImovelDetalhes — CONTRACT § 5 section surface.
 *
 * Scoped to what this slice owns: header badges (true-only), the header
 * Pencil placeholder (toast, no mutation), and section-hidden-when-empty
 * for the new CONTRACT § 5 sections. Real formatters/labels come through
 * `importOriginal` on `@/hooks/useImoveis`; the cartório/documentos/team
 * hooks are mocked to keep the render fast and deterministic — those are
 * pre-existing features this slice does not touch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseImovel = vi.fn();
const mockUseImovelRegistro = vi.fn();
vi.mock("@/hooks/useImoveis", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImoveis")>();
  return {
    ...actual,
    useImovel: mockUseImovel,
    useImovelRegistro: mockUseImovelRegistro,
  };
});

const mockUseSolicitacaoDoImovel = vi.fn();
const mockUseSolicitarCampanha = vi.fn();
vi.mock("@/hooks/useCampanhas", () => ({
  useSolicitacaoDoImovel: mockUseSolicitacaoDoImovel,
  useSolicitarCampanha: mockUseSolicitarCampanha,
}));

const mockUseImovelDados = vi.fn();
const mockUseImovelDadosMutation = vi.fn();
const mockUseEnderecoManualMutation = vi.fn(() => ({
  mutate: vi.fn(),
  isPending: false,
}));
const mockUseImovelDocumentoMutations = vi.fn();
const mockUseImovelDocumentos = vi.fn();
// `useImovelExtracaoPollingInvalidation` is real `useQueryClient()`, and
// this harness renders without a `QueryClientProvider` (same reason
// `useImovelContrato`'s mock below is inert) — a no-op stand-in here; its
// own behaviour is covered by `useImovelDados.extracaoPolling.test.tsx`.
const mockUseImovelExtracaoPollingInvalidation = vi.fn();
vi.mock("@/hooks/useImovelDados", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImovelDados")>();
  return {
    ...actual,
    useImovelDados: mockUseImovelDados,
    useImovelDadosMutation: mockUseImovelDadosMutation,
    useEnderecoManualMutation: mockUseEnderecoManualMutation,
    useImovelDocumentoMutations: mockUseImovelDocumentoMutations,
    useImovelDocumentos: mockUseImovelDocumentos,
    useImovelExtracaoPollingInvalidation: mockUseImovelExtracaoPollingInvalidation,
  };
});

const mockUseTeamMembers = vi.fn();
vi.mock("@/hooks/useTeam", () => ({ useTeamMembers: mockUseTeamMembers }));

// The contract reads this page now mounts (`ImovelContratoContainer`,
// migrations 115/118). Mocked for the same reason the cartório hooks are:
// this harness renders without a QueryClientProvider, so a real `useQuery`
// here would throw. The cards themselves are covered by their own colocated
// tests; what matters at THIS level is that mounting them does not break the
// page, which is exactly what these inert hooks exercise.
vi.mock("@/hooks/useImovelContrato", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImovelContrato")>();
  const query = () => ({ data: undefined, isPending: false, isFetching: false, isError: false });
  const mutation = () => ({
    mutate: vi.fn(),
    isPending: false,
    error: null,
    variables: undefined,
  });
  return {
    ...actual,
    useTituloAquisitivo: query,
    useEnderecoRegistro: query,
    useOnusCredor: query,
    useAntigosProprietarios: query,
    useImovelCertidoes: query,
    useConfirmarTitulo: mutation,
    useConfirmarEnderecoRegistro: mutation,
    useConfirmarOnusCredor: mutation,
    useConfirmarUltimaTransferenciaManual: mutation,
    useConfirmarDocumentoExtracao: mutation,
  };
});

const mockToastInfo = vi.fn();
vi.mock("sonner", () => ({
  toast: { info: (...a: unknown[]) => mockToastInfo(...a), success: vi.fn(), error: vi.fn() },
}));

import type { Imovel } from "@/hooks/useImoveis";

function makeImovel(overrides: Partial<Imovel> = {}): Imovel {
  return {
    codigo: "AP1234",
    codigo_imobiliaria: null,
    titulo: "Apartamento no centro",
    categoria: "Apartamento",
    status: "Ativo",
    finalidades: [],
    cep: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: null,
    cidade: null,
    uf: null,
    empreendimento: null,
    latitude: null,
    longitude: null,
    valor_venda: 500000,
    valor_locacao: null,
    area_total: null,
    area_privativa: null,
    area_construida: null,
    dormitorios: null,
    suites: null,
    vagas: null,
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

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSolicitacaoDoImovel.mockReturnValue({ data: undefined, isPending: false, isFetching: false });
  mockUseSolicitarCampanha.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockUseImovelDados.mockReturnValue({ data: undefined, isPending: false });
  mockUseImovelDadosMutation.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null });
  mockUseImovelDocumentoMutations.mockReturnValue({
    upload: { mutate: vi.fn(), isPending: false, error: null },
    remove: { mutate: vi.fn(), error: null },
    getUrl: { mutateAsync: vi.fn() },
  });
  mockUseImovelDocumentos.mockReturnValue({ data: undefined, isPending: false });
  mockUseTeamMembers.mockReturnValue({ data: [] });
  // Default: not registered — every existing test's `mockUseImovel` already
  // returns a real imóvel, so this branch is never reached by them; only
  // the manual-layout tests below override it.
  mockUseImovelRegistro.mockReturnValue({ data: undefined, isPending: false, isError: false });
});

async function renderDetalhes(codigo = "AP1234") {
  const React = (await import("react")).default;
  const { default: ImovelDetalhes } = await import("./ImovelDetalhes");
  const { MemoryRouter, Routes, Route } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [`/imoveis/${codigo}`] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, { path: "/imoveis/:codigo", element: React.createElement(ImovelDetalhes) }),
        ),
      ),
    ),
    fireEvent: rtl.fireEvent,
  };
}

describe("ImovelDetalhes — header badges (true-only)", () => {
  it("shows no badges when every flag is false/null", async () => {
    mockUseImovel.mockReturnValue({ data: makeImovel(), isPending: false, isError: false });
    const { queryByText } = await renderDetalhes();

    expect(queryByText("Exclusivo")).toBeNull();
    expect(queryByText("Destaque")).toBeNull();
    expect(queryByText("Super destaque")).toBeNull();
    expect(queryByText("Tour 360°")).toBeNull();
  });

  it("shows only the badges that are true", async () => {
    mockUseImovel.mockReturnValue({
      data: makeImovel({ exclusivo: true, super_destaque_web: true }),
      isPending: false,
      isError: false,
    });
    const { getAllByText, queryByText } = await renderDetalhes();

    // Both also appear as Fact labels in § 5.7 Condições comerciais (the
    // same flags are header badges AND detailed facts) — at least one
    // instance, not exactly one.
    expect(getAllByText("Exclusivo").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText("Super destaque").length).toBeGreaterThanOrEqual(1);
    expect(queryByText("Destaque")).toBeNull();
  });
});

describe("ImovelDetalhes — header Pencil placeholder (CONTRACT § 4)", () => {
  it("fires the toast and performs no mutation on click", async () => {
    mockUseImovel.mockReturnValue({ data: makeImovel(), isPending: false, isError: false });
    const { getByRole, fireEvent } = await renderDetalhes();

    fireEvent.click(getByRole("button", { name: "Editar cabeçalho" }));

    expect(mockToastInfo).toHaveBeenCalledTimes(1);
    expect(mockUseSolicitarCampanha().mutate).not.toHaveBeenCalled();
    expect(mockUseImovelDadosMutation().mutate).not.toHaveBeenCalled();
  });
});

describe("ImovelDetalhes — section-hidden-when-empty", () => {
  it("hides every optional section when the imóvel carries none of their fields", async () => {
    mockUseImovel.mockReturnValue({ data: makeImovel(), isPending: false, isError: false });
    const { queryByText } = await renderDetalhes();

    expect(queryByText("Descrição")).toBeNull();
    expect(queryByText("Cômodos")).toBeNull();
    expect(queryByText("Áreas")).toBeNull();
    expect(queryByText("Construção e estado")).toBeNull();
    expect(queryByText("Condições comerciais")).toBeNull();
    expect(queryByText("Comodidades")).toBeNull();
    expect(queryByText("Mídia")).toBeNull();
    expect(queryByText("Localização")).toBeNull();
    expect(queryByText("Registro")).toBeNull();
    expect(queryByText("Metadados")).toBeNull();
  });

  it("shows a section once it has ≥1 non-null field", async () => {
    mockUseImovel.mockReturnValue({
      data: makeImovel({ dormitorios: 0, descricao_web: "Um imóvel excelente com muitas vantagens." }),
      isPending: false,
      isError: false,
    });
    const { getByText, queryByText } = await renderDetalhes();

    expect(getByText("Descrição")).toBeTruthy();
    expect(getByText("Cômodos")).toBeTruthy();
    // A genuine 0 dormitórios still reads "0" here too, same distinction
    // the hook-level test covers.
    expect(getByText("0")).toBeTruthy();
    expect(queryByText("Áreas")).toBeNull();
  });

  it("shows Metadados with dias_desde_atualizacao once the sync timestamp exists", async () => {
    mockUseImovel.mockReturnValue({
      data: makeImovel({
        data_atualizacao: "2026-08-20T00:00:00Z",
        dias_desde_atualizacao: 15,
      }),
      isPending: false,
      isError: false,
    });
    const { getByText } = await renderDetalhes();

    expect(getByText("Metadados")).toBeTruthy();
    expect(getByText(/há 15 dias/)).toBeTruthy();
  });
});

describe("ImovelDetalhes — manually-registered código (mirror 404, registry 200)", () => {
  it("🔴 renders the not-found card when BOTH the mirror and the registry 404", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockUseImovel.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new ApiError(404, "Imóvel não encontrado"),
    });
    mockUseImovelRegistro.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
    });
    const { getByText, queryByTestId } = await renderDetalhes();

    expect(getByText("Imóvel AP1234 não encontrado.")).toBeTruthy();
    expect(queryByTestId("imovel-manual-layout")).toBeNull();
  });

  it("🔴 renders the manual layout when the mirror 404s but the registry says manual", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockUseImovel.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new ApiError(404, "Imóvel não encontrado"),
    });
    mockUseImovelRegistro.mockReturnValue({
      data: {
        codigo: "AP1234",
        registrado: true,
        origem: "manual",
        criado_em: "2026-09-01T00:00:00Z",
      },
      isPending: false,
      isError: false,
    });
    const { getByTestId, queryByText, getByText } = await renderDetalhes();

    expect(getByTestId("imovel-manual-layout")).toBeTruthy();
    expect(getByTestId("imovel-manual-badge").textContent).toContain(
      "Cadastrado manualmente",
    );
    // The same cartório card the full page renders — codigo-scoped, no fork.
    expect(getByText("Cartório e registro")).toBeTruthy();
    expect(queryByText("Imóvel AP1234 não encontrado.")).toBeNull();
  });

  it("🔴 also renders 'Para o contrato' — título/endereço do registro/ônus have no OTHER reachable input for a manually registered property", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockUseImovel.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new ApiError(404, "Imóvel não encontrado"),
    });
    mockUseImovelRegistro.mockReturnValue({
      data: {
        codigo: "AP1234",
        registrado: true,
        origem: "manual",
        criado_em: "2026-09-01T00:00:00Z",
      },
      isPending: false,
      isError: false,
    });
    const { getByText, getByTestId } = await renderDetalhes();

    expect(getByTestId("imovel-manual-layout")).toBeTruthy();
    // All three cards the manual layout owes a manually-registered código:
    // cartório/registro, documentos, AND the contract's título/endereço/ônus.
    expect(getByText("Cartório e registro")).toBeTruthy();
    expect(getByText("Documentos do imóvel")).toBeTruthy();
    expect(getByText("Para o contrato")).toBeTruthy();
  });

  it("shows the skeleton while either the mirror or the registry is still resolving", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockUseImovel.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new ApiError(404, "Imóvel não encontrado"),
    });
    // Mirror already 404'd, but the registry hasn't answered yet — must not
    // flash "não encontrado" before the registry check settles.
    mockUseImovelRegistro.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { queryByText, queryByTestId } = await renderDetalhes();

    expect(queryByText("Imóvel AP1234 não encontrado.")).toBeNull();
    expect(queryByTestId("imovel-manual-layout")).toBeNull();
  });
});
