/**
 * Modelos.test.tsx — the platform-admin lock, loading/error states, the
 * catalog rows (prices, badges, metrics + note), adding `gpt-image-2` with
 * prices + batch flag through the dialog, the "no price" warning, per-step
 * models with reset-to-default, and the note rewrite trigger.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseCatalogo = vi.fn();
const mockUseModelos = vi.fn();
const mockUseEtapas = vi.fn();
const mockUseVersoes = vi.fn();
const mockSalvar = vi.fn();
const mockEtapas = vi.fn();
const mockNotas = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useModelosCatalogo: (...a: any[]) => mockUseCatalogo(...a),
    useModelos: (...a: any[]) => mockUseModelos(...a),
    useModelosEtapas: (...a: any[]) => mockUseEtapas(...a),
    useModeloVersoes: (...a: any[]) => mockUseVersoes(...a),
    useSalvarModeloCatalogo: () => ({ mutateAsync: mockSalvar, isPending: false }),
    useAtualizarModelosEtapas: () => ({ mutateAsync: mockEtapas, isPending: false }),
    useGerarNotasModelos: () => ({ mutateAsync: mockNotas, isPending: false }),
  };
});

const PRECOS = { entrada_texto: 5, saida_texto: null, entrada_imagem: 8, saida_imagem: 30 };

function linha(overrides: Partial<any> = {}) {
  return {
    id: "gpt-image-2.5-sunburst",
    kind: "image_edit",
    nome: "GPT Image 2.5 Sunburst",
    descricao: null,
    snapshot: "-2026-09-08",
    versao: "gpt-image-2.5-sunburst-2026-09-08",
    habilitado: true,
    precos: PRECOS,
    suporta_batch: false,
    tag_performance: null,
    com_preco: true,
    origem: "catalogo",
    precos_padrao: PRECOS,
    revisao: null,
    atualizado_em: null,
    atualizado_por: null,
    ...overrides,
  };
}

function capacidades(overrides: Partial<any> = {}) {
  return { pode_administrar_plataforma: true, dashboard: "platform", ...overrides };
}

function catalogo(overrides: Partial<any> = {}) {
  return {
    modelos: [
      linha(),
      linha({ id: "gpt-image-2", nome: "GPT Image 2", origem: "adicionado", revisao: 2, com_preco: false,
              suporta_batch: true, precos: { ...PRECOS, saida_imagem: null }, precos_padrao: null }),
      linha({ id: "gpt-5.6-terra", kind: "vision", nome: "GPT-5.6 Terra", precos: { entrada_texto: 2, saida_texto: 12, entrada_imagem: null, saida_imagem: null } }),
      linha({ id: "gpt-6-astra", kind: "vision", nome: "GPT-6 Astra" }),
    ],
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

const ETAPAS = [
  { etapa: "guia", tipo: "vision", modelo: "gpt-5.6-terra", padrao: "gpt-5.6-sol", personalizado: true },
  { etapa: "avaliador", tipo: "vision", modelo: "gpt-5.6-terra", padrao: "gpt-5.6-terra", personalizado: false },
];

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Modelos } = await import("./Modelos");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Modelos)), fireEvent: rtl.fireEvent, waitFor: rtl.waitFor };
}

describe("Modelos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
    mockUseCatalogo.mockReturnValue(catalogo());
    mockUseModelos.mockReturnValue({
      modelos: [{
        id: "gpt-image-2.5-sunburst", nome: "x", versao: "x", tag_performance: null, suporta_batch: false,
        nota_recomendacao: "Boa aprovação.", nota_gerada_em: "2026-09-16T03:05:00Z",
        metricas: { total_fotos: 12, taxa_aprovacao: 0.75, score_medio_ia: 8.1, custo_por_foto_aprovada: 0.04 },
      }],
      showSkeleton: false,
    });
    mockUseEtapas.mockReturnValue({ etapas: ETAPAS, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseVersoes.mockReturnValue({ versoes: [], showSkeleton: false, error: null });
    mockSalvar.mockResolvedValue({ recarregado: true });
  });

  it("locks the page for anyone but the platform admin", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ pode_administrar_plataforma: false }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("modelos-restrito")).toBeTruthy();
    expect(mockUseCatalogo).not.toHaveBeenCalled();
  });

  it("shows a skeleton only while capabilities load", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("modelos-loading")).toBeTruthy();
  });

  it("renders catalog skeleton, error and refreshing states", async () => {
    mockUseCatalogo.mockReturnValue(catalogo({ modelos: [], showSkeleton: true }));
    const first = await renderPage();
    expect(first.getByTestId("modelos-loading")).toBeTruthy();
    first.unmount();

    const refetch = vi.fn();
    mockUseCatalogo.mockReturnValue(catalogo({ error: new Error("x"), refetch }));
    const second = await renderPage();
    second.fireEvent.click(second.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
    second.unmount();

    mockUseCatalogo.mockReturnValue(catalogo({ isRefreshing: true }));
    const third = await renderPage();
    expect(third.getByTestId("modelos-atualizando")).toBeTruthy();
    expect(third.getByTestId("modelo-gpt-image-2.5-sunburst")).toBeTruthy();
  });

  it("shows prices, badges, live metrics and the daily note", async () => {
    const { getByTestId, getByText } = await renderPage();
    const metricas = getByTestId("metricas-gpt-image-2.5-sunburst");
    expect(metricas.textContent).toContain("75.0%");
    expect(metricas.textContent).toContain("Boa aprovação.");
    const semPreco = getByTestId("modelo-gpt-image-2");
    expect(semPreco.textContent).toContain("Sem preço");
    expect(semPreco.textContent).toContain("Batch (Econômico)");
    expect(semPreco.textContent).toContain("Adicionado · v2");
    expect(getByText("Edição de imagem")).toBeTruthy();
  });

  it("adds gpt-image-2 with prices and the batch flag", async () => {
    const { getByText, getByLabelText, fireEvent, waitFor, getByTestId, queryByTestId } = await renderPage();
    fireEvent.click(getByText("Adicionar modelo"));
    fireEvent.change(getByLabelText("Identificador (OpenAI)"), { target: { value: "gpt-image-2" } });
    fireEvent.change(getByLabelText("Nome"), { target: { value: "GPT Image 2" } });
    fireEvent.change(getByLabelText("Texto — entrada"), { target: { value: "5" } });
    fireEvent.change(getByLabelText("Imagem — entrada"), { target: { value: "10,5" } });
    expect(getByTestId("aviso-sem-preco")).toBeTruthy();
    fireEvent.change(getByLabelText("Imagem — saída"), { target: { value: "40" } });
    expect(queryByTestId("aviso-sem-preco")).toBeNull();
    fireEvent.click(getByLabelText("Suporta Batch API (modo Econômico)"));
    fireEvent.click(getByText("Salvar"));
    await waitFor(() => expect(mockSalvar).toHaveBeenCalled());
    expect(mockSalvar.mock.calls[0][0]).toEqual({
      id: "gpt-image-2",
      body: expect.objectContaining({
        kind: "image_edit",
        nome: "GPT Image 2",
        preco_entrada_texto_1m: "5",
        preco_entrada_imagem_1m: "10.5",
        preco_saida_imagem_1m: "40",
        preco_saida_texto_1m: null,
        suporta_batch: true,
        habilitado: true,
      }),
    });
  });

  it("refuses to save an invalid id or price", async () => {
    const { getByText, getByLabelText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Adicionar modelo"));
    fireEvent.change(getByLabelText("Identificador (OpenAI)"), { target: { value: "Bad Id" } });
    expect((getByText("Salvar").closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(getByLabelText("Identificador (OpenAI)"), { target: { value: "ok-id" } });
    fireEvent.change(getByLabelText("Texto — saída"), { target: { value: "abc" } });
    expect(getByText("Preços devem ser números não negativos.")).toBeTruthy();
    expect((getByText("Salvar").closest("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("edits an existing row prefilled with its prices", async () => {
    const { getAllByText, getByLabelText, getByText, fireEvent, waitFor } = await renderPage();
    fireEvent.click(getAllByText("Editar")[0]);
    expect((getByLabelText("Imagem — saída") as HTMLInputElement).value).toBe("30");
    fireEvent.click(getByLabelText("Habilitado"));
    fireEvent.click(getByText("Salvar"));
    await waitFor(() => expect(mockSalvar).toHaveBeenCalled());
    expect(mockSalvar.mock.calls[0][0].body.habilitado).toBe(false);
    expect(mockSalvar.mock.calls[0][0].id).toBe("gpt-image-2.5-sunburst");
  });

  it("resets a customized step to its default and rewrites notes on demand", async () => {
    const { getByText, fireEvent, waitFor, getByTestId } = await renderPage();
    expect(getByTestId("etapa-avaliador").textContent).toContain("padrão");
    fireEvent.click(getByText("Voltar ao padrão (gpt-5.6-sol)"));
    await waitFor(() => expect(mockEtapas).toHaveBeenCalledWith({ guia: null }));
    fireEvent.click(getByText("Reescrever notas agora"));
    await waitFor(() => expect(mockNotas).toHaveBeenCalled());
  });

  it("opens the version history of an edited row", async () => {
    mockUseVersoes.mockReturnValue({
      versoes: [{ revisao: 2, habilitado: true, nome: "GPT Image 2", snapshot: null,
                  precos: { ...PRECOS, saida_imagem: 45 }, suporta_batch: true, tag_performance: null,
                  atualizado_em: "2026-09-16T18:00:00Z", atualizado_por: "u" }],
      showSkeleton: false, error: null,
    });
    const { getAllByText, getByTestId, fireEvent } = await renderPage();
    const botoes = getAllByText("Histórico");
    fireEvent.click(botoes[1]);
    expect(getByTestId("historico-lista").textContent).toContain("v2");
    expect(mockUseVersoes).toHaveBeenCalledWith("gpt-image-2", "image_edit");
  });
});
