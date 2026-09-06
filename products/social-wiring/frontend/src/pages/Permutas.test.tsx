/**
 * Permutas.test.tsx — the four required states plus this page's own
 * non-negotiable rules.
 *
 * The three that are NOT generic page hygiene:
 *
 *   1. a rule-only run is announced. `sem_semantica > 0` means the free text
 *      — where this corpus keeps its real constraints — was never read, and
 *      the output otherwise looks completely normal. erp shipped that state
 *      for months.
 *   2. a legacy row's `score: 0` never renders as a score. Those decisions
 *      were inherited, not computed; "0" beside real scores reads as "we
 *      scored this and it is terrible".
 *   3. an empty list and a failed request are different states.
 *
 * `@noctusai/seed/infra` and `@noctusai/lib/design-system` are stubbed at the
 * module boundary for the same reason as `PortalRoi.test.tsx`: both construct
 * the real Supabase client at import time and throw without VITE_SUPABASE_URL.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/lib/design-system", () => ({
  TableSkeleton: () => <div data-testid="skeleton" />,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockUsePermutaMatches = vi.fn();
const mockUsePermutaAtivos = vi.fn();
const mockGerar = vi.fn();

vi.mock("@/hooks/usePermutas", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/usePermutas")>("@/hooks/usePermutas");
  return {
    ...actual,
    usePermutaMatches: mockUsePermutaMatches,
    usePermutaAtivos: mockUsePermutaAtivos,
    useGerarMatches: () => ({ mutateAsync: mockGerar, isPending: false }),
    useGerarEmbeddings: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useMoverEtapa: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

function query(over: Record<string, unknown> = {}) {
  return {
    data: [],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    ...over,
  };
}

const RESUMO = {
  id: "a",
  natureza: "imovel" as const,
  imovel_codigo: "ONE9265",
  codigo: null,
  titulo: "Casa na Granja",
  tipo_imovel: "Casa em Condomínio",
  cidade: "Cotia",
  bairro: "Granja Viana",
  uf: "SP",
  valor: 1_200_000,
  quartos: 3,
  vagas: 2,
  area_total: 300,
  condominio_nome: null,
  observacoes: null,
  proprietario_nome: null,
};

function match(over: Record<string, unknown> = {}) {
  return {
    id: "m1",
    ativo_origem_id: "a",
    ativo_destino_id: "b",
    score: 82,
    justificativa: "Preço alinhado",
    detalhes: { semantica_disponivel: true },
    score_breakdown: {},
    is_bilateral: true,
    etapa: "sugerido" as const,
    observacoes: "",
    origem: "motor" as const,
    created_at: "2026-09-06T00:00:00Z",
    decidido_em: null,
    ativo_origem: RESUMO,
    ativo_destino: { ...RESUMO, id: "b", imovel_codigo: "ONE9807" },
    ...over,
  };
}

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { default: Permutas } = await import("./Permutas");
  return rtlRender(<Permutas />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUsePermutaAtivos.mockReturnValue(query());
  mockUsePermutaMatches.mockReturnValue(query());
});

describe("os quatro estados", () => {
  it("mostra o esqueleto só antes do primeiro carregamento", async () => {
    mockUsePermutaMatches.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("skeleton")).toBeTruthy();
  });

  it("🔴 um refetch NÃO desmonta a lista existente", async () => {
    // `isFetching` is true with data present — the lying-loading-state trap.
    // A bare `isFetching` gate here would replace a rendered list with a
    // spinner on every mutation. → KB § PATTERNS/frontend/lying-loading-state.md
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match()], isFetching: true }),
    );
    const { queryByTestId, getAllByText } = await render();
    expect(queryByTestId("skeleton")).toBeNull();
    // Both sides carry the same fixture title — `getAllByText`, not `getByText`.
    expect(getAllByText("Casa na Granja").length).toBe(2);
    expect(queryByTestId("permutas-refreshing")).toBeTruthy();
  });

  it("distingue lista vazia de falha na requisição", async () => {
    mockUsePermutaMatches.mockReturnValue(query({ data: [] }));
    const vazio = await render();
    expect(vazio.getByText(/Nenhum match/)).toBeTruthy();

    (await import("@testing-library/react")).cleanup();

    mockUsePermutaMatches.mockReturnValue(
      query({ isError: true, error: { message: "boom" }, data: undefined }),
    );
    const erro = await render();
    expect(erro.getByText(/Não foi possível carregar/)).toBeTruthy();
    expect(erro.queryByText(/Nenhum match/)).toBeNull();
  });

  it("renderiza os dois lados de um match", async () => {
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const { getByText, getAllByText } = await render();
    expect(getByText("ONE9265")).toBeTruthy();
    expect(getByText("ONE9807")).toBeTruthy();
    expect(getAllByText(/82/).length).toBeGreaterThan(0);
  });
});

describe("a análise semântica é visível", () => {
  it("🔴 marca o par pontuado só por regras", async () => {
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ detalhes: { semantica_disponivel: false } })] }),
    );
    const { getByText } = await render();
    expect(getByText("Sem análise semântica")).toBeTruthy();
  });

  it("não marca o par que teve os vetores", async () => {
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const { queryByText } = await render();
    expect(queryByText("Sem análise semântica")).toBeNull();
  });

  it("🔴 avisa depois de uma rodada sem embeddings", async () => {
    const { fireEvent, waitFor } = await import("@testing-library/react");
    mockGerar.mockResolvedValue({
      encontrados: 40,
      gravados: 40,
      protegidos: 0,
      imoveis_avaliados: 99,
      permutas_avaliadas: 14,
      sem_semantica: 40,
      imoveis_nao_resolvidos: [],
    });
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));

    const { getByText } = await render();
    fireEvent.click(getByText("Gerar matches"));

    await waitFor(() => {
      expect(getByText(/pontuados só por regras/)).toBeTruthy();
    });
  });

  it("avisa sobre intenções cujo imóvel saiu do catálogo", async () => {
    const { fireEvent, waitFor } = await import("@testing-library/react");
    mockGerar.mockResolvedValue({
      encontrados: 5,
      gravados: 5,
      protegidos: 0,
      imoveis_avaliados: 99,
      permutas_avaliadas: 14,
      sem_semantica: 0,
      imoveis_nao_resolvidos: ["ONE1111", "ONE2222"],
    });
    const { getByText } = await render();
    fireEvent.click(getByText("Gerar matches"));
    await waitFor(() => {
      expect(getByText(/não está mais no catálogo/)).toBeTruthy();
    });
  });
});

describe("decisões herdadas", () => {
  it("🔴 nunca renderiza o score 0 de uma decisão herdada", async () => {
    mockUsePermutaMatches.mockReturnValue(
      query({
        data: [match({ score: 0, origem: "permutas_legacy", etapa: "rejeitado" })],
      }),
    );
    const { getByText, queryByText } = await render();
    expect(getByText("Decisão herdada do Permutas")).toBeTruthy();
    expect(queryByText(/0 · Parcial/)).toBeNull();
  });
});
