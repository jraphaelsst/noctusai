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
  Skeleton: () => <div data-testid="skeleton-linha" />,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockUsePermutaMatches = vi.fn();
const mockUsePermutaAtivos = vi.fn();
const mockGerar = vi.fn();
const mockMover = vi.fn();
const mockMotivos = vi.fn();

vi.mock("@/hooks/usePermutas", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/usePermutas")>("@/hooks/usePermutas");
  return {
    ...actual,
    usePermutaMatches: mockUsePermutaMatches,
    usePermutaAtivos: mockUsePermutaAtivos,
    useGerarMatches: () => ({ mutateAsync: mockGerar, isPending: false }),
    useGerarEmbeddings: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useMoverEtapa: () => ({ mutateAsync: mockMover, isPending: false }),
    useMotivosRejeicao: () => mockMotivos(),
    useCriarAtivo: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useAtualizarAtivo: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useRemoverAtivo: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

const MOTIVOS = [
  { codigo: "preco", rotulo: "Preço incompatível", exige_detalhe: false },
  { codigo: "outro", rotulo: "Outro motivo", exige_detalhe: true },
];

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { default: Permutas } = await import("./Permutas");
  return rtlRender(<Permutas />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUsePermutaAtivos.mockReturnValue(query());
  mockUsePermutaMatches.mockReturnValue(query());
  mockMover.mockResolvedValue({});
  mockMotivos.mockReturnValue(query({ data: MOTIVOS }));
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

describe("cabeçalho — contagens", () => {
  it("🔴 não mostra '0 imóveis · 0 matches' enquanto as consultas carregam", async () => {
    mockUsePermutaAtivos.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    mockUsePermutaMatches.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    const { queryByText, getByTestId, queryByTestId } = await render();
    expect(queryByText(/0 imóveis/)).toBeNull();
    expect(queryByTestId("permutas-contagens")).toBeNull();
    expect(getByTestId("permutas-contagens-carregando")).toBeTruthy();
  });

  it("espera as DUAS consultas — matches prontos e ativos pendentes ainda é placeholder", async () => {
    mockUsePermutaAtivos.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const { queryByTestId } = await render();
    expect(queryByTestId("permutas-contagens")).toBeNull();
    expect(queryByTestId("permutas-contagens-carregando")).toBeTruthy();
  });

  it("mostra as contagens reais quando os dados chegam", async () => {
    mockUsePermutaAtivos.mockReturnValue(query({ data: [{ id: "x" }, { id: "y" }] }));
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const { getByTestId } = await render();
    expect(getByTestId("permutas-contagens").textContent).toMatch(
      /2 imóveis abertos a permuta · 1 match$/,
    );
  });

  it("falha nas contagens não vira '0'", async () => {
    mockUsePermutaAtivos.mockReturnValue(
      query({ isError: true, error: { message: "boom" }, data: undefined }),
    );
    const { getByText, queryByTestId } = await render();
    expect(getByText("Contagens indisponíveis")).toBeTruthy();
    expect(queryByTestId("permutas-contagens")).toBeNull();
  });
});

describe("LadoDoMatch — endereço uma vez só", () => {
  it("🔴 não repete o bairro quando o empreendimento é o próprio bairro", async () => {
    const lado = {
      ...RESUMO,
      titulo: "Casa térrea",
      bairro: "Fazendinha - Km 23",
      cidade: "Carapicuíba",
      condominio_nome: "Fazendinha - Km 23",
    };
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ ativo_origem: lado, ativo_destino: { ...RESUMO, id: "b" } })] }),
    );
    const { getAllByText } = await render();
    expect(getAllByText(/Fazendinha - Km 23/).length).toBe(1);
  });

  it("não repete o bairro quando o título é o bairro", async () => {
    const lado = { ...RESUMO, titulo: "Fazendinha - Km 23", bairro: "Fazendinha - Km 23" };
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ ativo_origem: lado, ativo_destino: { ...RESUMO, id: "b" } })] }),
    );
    const { getAllByText } = await render();
    expect(getAllByText(/Fazendinha - Km 23/).length).toBe(1);
  });

  it("um empreendimento distinto continua visível", async () => {
    const lado = { ...RESUMO, condominio_nome: "Residencial Aldeia" };
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ ativo_origem: lado, ativo_destino: { ...RESUMO, id: "b" } })] }),
    );
    const { getByText } = await render();
    expect(getByText("Residencial Aldeia")).toBeTruthy();
  });
});

describe("abas", () => {
  it("a aba 'Imóveis em permuta' mostra o registro", async () => {
    const { fireEvent, waitFor } = await import("@testing-library/react");
    const { getByRole, getByTestId } = await render();
    fireEvent.mouseDown(getByRole("tab", { name: "Imóveis em permuta" }), { button: 0 });
    await waitFor(() => expect(getByTestId("permuta-ativos-lista")).toBeTruthy());
  });
});

describe("rejeição com motivo", () => {
  async function abrirDialogo() {
    const rtl = await import("@testing-library/react");
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const r = await render();
    // The stage-filter bar repeats the labels; the card's buttons come last.
    rtl.fireEvent.click(r.getAllByRole("button", { name: "Descartado" }).at(-1)!);
    return { ...r, rtl };
  }

  it("abrir 'Rejeitado' mostra o diálogo e não move ainda", async () => {
    const { getByText } = await abrirDialogo();
    expect(getByText("Por que descartar este match?")).toBeTruthy();
    expect(mockMover).not.toHaveBeenCalled();
  });

  it("confirmar fica desabilitado até escolher o motivo", async () => {
    const { getByRole, getByLabelText, rtl } = await abrirDialogo();
    const confirmar = getByRole("button", { name: "Confirmar descarte" }) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    rtl.fireEvent.click(getByLabelText("Preço incompatível"));
    expect(confirmar.disabled).toBe(false);
  });

  it("motivo que exige detalhe pede o detalhe", async () => {
    const { getByRole, getByLabelText, rtl } = await abrirDialogo();
    const confirmar = getByRole("button", { name: "Confirmar descarte" }) as HTMLButtonElement;
    rtl.fireEvent.click(getByLabelText("Outro motivo"));
    expect(confirmar.disabled).toBe(true);
    rtl.fireEvent.change(getByLabelText(/Detalhes/), { target: { value: "  " } });
    expect(confirmar.disabled).toBe(true);
    rtl.fireEvent.change(getByLabelText(/Detalhes/), { target: { value: "dono desistiu" } });
    expect(confirmar.disabled).toBe(false);
  });

  it("envia motivo, lado e detalhe; 'Não sei' omite o lado", async () => {
    const { getByRole, getByLabelText, rtl } = await abrirDialogo();
    rtl.fireEvent.click(getByLabelText("Preço incompatível"));
    rtl.fireEvent.click(getByLabelText("Destino"));
    rtl.fireEvent.change(getByLabelText(/Detalhes/), { target: { value: "acima do teto" } });
    rtl.fireEvent.click(getByRole("button", { name: "Confirmar descarte" }));
    await rtl.waitFor(() =>
      expect(mockMover).toHaveBeenCalledWith({
        matchId: "m1",
        etapa: "rejeitado",
        motivo_rejeicao: "preco",
        motivo_rejeicao_detalhe: "acima do teto",
        motivo_lado: "destino",
      }),
    );
  });

  it("sem lado escolhido o campo não vai no corpo", async () => {
    const { getByRole, getByLabelText, rtl } = await abrirDialogo();
    rtl.fireEvent.click(getByLabelText("Preço incompatível"));
    rtl.fireEvent.click(getByRole("button", { name: "Confirmar descarte" }));
    await rtl.waitFor(() =>
      expect(mockMover).toHaveBeenCalledWith({
        matchId: "m1",
        etapa: "rejeitado",
        motivo_rejeicao: "preco",
      }),
    );
  });

  it("🔴 a recusa do servidor aparece no diálogo (nunca silenciosa)", async () => {
    mockMover.mockRejectedValue(new Error("motivo inválido"));
    const { getByRole, getByLabelText, findByText, rtl } = await abrirDialogo();
    rtl.fireEvent.click(getByLabelText("Preço incompatível"));
    rtl.fireEvent.click(getByRole("button", { name: "Confirmar descarte" }));
    expect(await findByText("motivo inválido")).toBeTruthy();
  });

  it("mostra carregando enquanto os motivos carregam, e o erro se falharem", async () => {
    mockMotivos.mockReturnValue(query({ isPending: true, data: undefined }));
    const a = await abrirDialogo();
    expect(a.getByTestId("motivos-carregando")).toBeTruthy();
    a.rtl.cleanup();
    mockMotivos.mockReturnValue(
      query({ isError: true, error: { message: "fora do ar" }, data: undefined }),
    );
    const b = await abrirDialogo();
    expect(b.getByText(/Não foi possível carregar os motivos/)).toBeTruthy();
  });

  it("outra etapa move na hora, sem diálogo nem campos de motivo", async () => {
    const rtl = await import("@testing-library/react");
    mockUsePermutaMatches.mockReturnValue(query({ data: [match()] }));
    const { getAllByRole, queryByText } = await render();
    rtl.fireEvent.click(getAllByRole("button", { name: "Em avaliação" }).at(-1)!);
    await rtl.waitFor(() =>
      expect(mockMover).toHaveBeenCalledWith({ matchId: "m1", etapa: "avaliacao" }),
    );
    expect(queryByText("Por que descartar este match?")).toBeNull();
  });

  it("cartão rejeitado mostra rótulo, lado e detalhe", async () => {
    mockUsePermutaMatches.mockReturnValue(
      query({
        data: [
          match({
            etapa: "rejeitado",
            motivo_rejeicao: "preco",
            motivo_lado: "origem",
            motivo_rejeicao_detalhe: "acima do teto",
          }),
        ],
      }),
    );
    const { getByTestId } = await render();
    const t = getByTestId("motivo-rejeicao").textContent;
    expect(t).toContain("Preço incompatível");
    expect(t).toContain("Origem");
    expect(t).toContain("acima do teto");
  });

  it("sem o vocabulário carregado cai no código cru", async () => {
    mockMotivos.mockReturnValue(query({ data: undefined, isPending: true }));
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ etapa: "rejeitado", motivo_rejeicao: "preco" })] }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("motivo-rejeicao").textContent).toContain("preco");
  });

  it("🔴 cartão rejeitado legado não mostra motivo nem 'undefined'", async () => {
    mockUsePermutaMatches.mockReturnValue(
      query({ data: [match({ etapa: "rejeitado", origem: "permutas_legacy", score: 0 })] }),
    );
    const { queryByTestId, container } = await render();
    expect(queryByTestId("motivo-rejeicao")).toBeNull();
    expect(container.textContent).not.toContain("undefined");
  });
});
