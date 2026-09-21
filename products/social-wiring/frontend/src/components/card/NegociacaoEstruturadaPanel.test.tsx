/**
 * NegociacaoEstruturadaPanel.test.tsx — the four states, the saldo indicator,
 * and the dividir-saldo 400 path.
 *
 * Follows the established mock-the-hook pattern (`pages/Permutas.test.tsx`):
 * `@/hooks/useNegociacaoEstruturada` and `@/hooks/usePermutas` are mocked
 * directly, so no QueryClientProvider is needed and the real
 * `@noctusai/seed/components/ui/table` import is exercised unmocked, same as
 * `pages/Certidoes.test.tsx`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// The real `Select` is a Radix popover (pointer-capture + portal) that jsdom
// does not model faithfully — same mock convention `ContratosPanel.test.tsx`
// uses: every `SelectItem` renders inline (no open/close step) so a click
// reaches `onValueChange` directly.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", onClick: () => ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

const mockUseNegociacaoEstruturada = vi.fn();
const mockCreateParcela = vi.fn();
const mockUpdateParcela = vi.fn();
const mockDeleteParcela = vi.fn();
const mockDividirSaldo = vi.fn();
const mockCreateFavorecido = vi.fn();
const mockUpdateFavorecido = vi.fn();
const mockDeleteFavorecido = vi.fn();
const mockCreateIntermediario = vi.fn();
const mockUpdateIntermediario = vi.fn();
const mockDeleteIntermediario = vi.fn();
const mockPosseMutation = vi.fn();
const mockAtualizarTermos = vi.fn();

vi.mock("@/hooks/useNegociacaoEstruturada", async () => {
  const actual = await vi.importActual<
    typeof import("@/hooks/useNegociacaoEstruturada")
  >("@/hooks/useNegociacaoEstruturada");
  return {
    ...actual,
    useNegociacaoEstruturada: mockUseNegociacaoEstruturada,
    useCreateParcela: () => ({ mutate: mockCreateParcela, isPending: false }),
    useUpdateParcela: () => ({ mutate: mockUpdateParcela, isPending: false }),
    useDeleteParcela: () => ({ mutate: mockDeleteParcela, isPending: false }),
    useDividirSaldo: () => ({ mutate: mockDividirSaldo, isPending: false }),
    useCreateFavorecido: () => ({
      mutate: mockCreateFavorecido,
      isPending: false,
    }),
    useUpdateFavorecido: () => ({
      mutate: mockUpdateFavorecido,
      isPending: false,
    }),
    useDeleteFavorecido: () => ({
      mutate: mockDeleteFavorecido,
      isPending: false,
    }),
    useCreateIntermediario: () => ({
      mutate: mockCreateIntermediario,
      isPending: false,
    }),
    useUpdateIntermediario: () => ({
      mutate: mockUpdateIntermediario,
      isPending: false,
    }),
    useDeleteIntermediario: () => ({
      mutate: mockDeleteIntermediario,
      isPending: false,
    }),
    useNegociacaoPosseMutation: () => ({
      mutate: mockPosseMutation,
      isPending: false,
    }),
    useAtualizarTermos: () => ({
      mutate: mockAtualizarTermos,
      isPending: false,
    }),
  };
});

const mockUsePermutaAtivos = vi.fn();
vi.mock("@/hooks/usePermutas", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/usePermutas")>(
      "@/hooks/usePermutas",
    );
  return {
    ...actual,
    usePermutaAtivos: mockUsePermutaAtivos,
  };
});

function query(over: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function termosVazios() {
  return {
    posse_prazo_dias: null,
    posse_marco: null,
    posse_marco_parcela_id: null,
    permuta_posse_prazo_dias: null,
    permuta_posse_marco: null,
    permuta_posse_marco_parcela_id: null,
    permuta_obrigacoes_entrega: null,
    itens_integrantes: null,
    ad_corpus: null,
    obrigacoes_vendedor: null,
    onus_quitacao: null,
    onus_prazo_dias: null,
    confissao_juros_am: null,
    confissao_garantia: null,
    corretagem_contratantes: null,
    corretagem_num_parcelas: null,
  };
}

function aggregate(over: Record<string, unknown> = {}) {
  return {
    atendimento_id: "at-1",
    valor_negociado: "850000.00",
    saldo_nao_alocado: "0.00",
    posse_data: null,
    posse_condicoes: null,
    permuta_ativo_id: null,
    parcelas: [],
    favorecidos: [],
    intermediarios: [],
    termos: termosVazios(),
    completude: { completo: true, faltando: [] },
    ...over,
  };
}

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { default: NegociacaoEstruturadaPanel } = await import(
    "./NegociacaoEstruturadaPanel"
  );
  return rtlRender(<NegociacaoEstruturadaPanel clienteId="cli-1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseNegociacaoEstruturada.mockReturnValue(query({ data: aggregate() }));
  mockUsePermutaAtivos.mockReturnValue(query({ data: [] }));
});

describe("os quatro estados", () => {
  it("mostra o esqueleto só antes do primeiro carregamento", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("negest-skeleton")).toBeTruthy();
  });

  it("distingue erro de vazio", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ isError: true, error: { message: "boom" }, data: undefined }),
    );
    const { getByTestId, getByText } = await render();
    expect(getByTestId("negest-error")).toBeTruthy();
    expect(getByText(/Não foi possível carregar/)).toBeTruthy();
  });

  it("🔴 um refetch não desmonta o painel existente", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ data: aggregate(), isFetching: true }),
    );
    const { queryByTestId, getByTestId } = await render();
    expect(queryByTestId("negest-skeleton")).toBeNull();
    expect(getByTestId("negest-refreshing")).toBeTruthy();
    expect(getByTestId("negociacao-estruturada-panel")).toBeTruthy();
  });

  it("renderiza os dados quando a carga termina", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({
        data: aggregate({
          parcelas: [
            {
              id: "p1",
              tipo: "sinal",
              valor: "50000.00",
              vencimento: "2026-10-01",
              evento: null,
              forma_pagamento: "PIX",
              favorecido_id: null,
              confissao_divida: false,
              ordem: 1,
              created_at: null,
              updated_at: null,
            },
          ],
        }),
      }),
    );
    const { getByText, getByTestId } = await render();
    expect(getByTestId("parcela-p1")).toBeTruthy();
    expect(getByText("Sinal")).toBeTruthy();
  });
});

describe("o indicador de saldo não alocado", () => {
  it("fica neutro quando o saldo é zero", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ data: aggregate({ saldo_nao_alocado: "0.00" }) }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("negest-saldo").className).toContain("text-muted-foreground");
    expect(getByTestId("negest-saldo").className).not.toContain("text-destructive");
  });

  it("🔴 fica em destaque (vermelho) quando o saldo é diferente de zero", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ data: aggregate({ saldo_nao_alocado: "1250.50" }) }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("negest-saldo").className).toContain("text-destructive");
  });

  it("trata `null` como zerado (nada ainda a alocar)", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ data: aggregate({ saldo_nao_alocado: null }) }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("negest-saldo").className).not.toContain("text-destructive");
  });
});

describe("completude", () => {
  it("lista o que falta quando incompleto, traduzido para pt-BR", async () => {
    // 🔴 Real backend keys (`negociacao_estruturada_service._completude`),
    // not raw literals — the operator must never see `parcelas_nao_cobrem_
    // valor_negociado` printed verbatim. An UNRECOGNISED key still falls back
    // to itself (never silently dropped) — `rotuloNegociacaoFaltando`.
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({
        data: aggregate({
          completude: {
            completo: false,
            faltando: ["valor_negociado", "posse", "chave_desconhecida"],
          },
        }),
      }),
    );
    const { getByText } = await render();
    expect(getByText("Valor negociado não informado")).toBeTruthy();
    expect(getByText("Termos de posse não preenchidos")).toBeTruthy();
    expect(getByText("chave_desconhecida")).toBeTruthy();
    expect(getByText("Pendente")).toBeTruthy();
  });

  it("não lista nada quando completo", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({ data: aggregate({ completude: { completo: true, faltando: [] } }) }),
    );
    const { getByText, queryByRole } = await render();
    expect(getByText("Completo")).toBeTruthy();
    expect(queryByRole("list")).toBeNull();
  });
});

describe("dividir saldo — o caminho de erro 400", () => {
  it("🔴 o 400 do backend ('sem valor_negociado ou sem saldo') chega via toast E no diálogo", async () => {
    mockDividirSaldo.mockImplementation(
      (_payload: unknown, opts?: { onError?: (e: unknown) => void }) => {
        opts?.onError?.({
          message: "[400] Não há saldo não alocado para dividir.",
        });
      },
    );

    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-dividir-saldo-abrir"));
    fireEvent.click(getByTestId("negest-dividir-saldo-salvar"));

    expect(mockDividirSaldo).toHaveBeenCalled();
    const { toast } = await import("sonner");
    const call = (toast.error as unknown as { mock: { calls: unknown[][] } })
      .mock.calls[0];
    expect(String(call[0])).toContain("saldo não alocado para dividir");
    // 🔴 A toast alone can be missed (behind the dialog overlay, or timed
    // out by the time the operator looks back) — the dialog STAYS OPEN and
    // renders the same message inline.
    expect(getByTestId("negest-dividir-saldo-erro").textContent).toContain(
      "saldo não alocado para dividir",
    );
  });
});

describe("nova parcela — o 422 do backend é renderizado NO DIÁLOGO (não só toast)", () => {
  it("🔴 um 422 real (forma_pagamento > 50 chars) fica visível no diálogo, que permanece aberto", async () => {
    mockCreateParcela.mockImplementation(
      (_payload: unknown, opts?: { onError?: (e: unknown) => void }) => {
        opts?.onError?.({
          message:
            "[422] String should have at most 50 characters",
        });
      },
    );

    const { getByTestId, queryByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));
    fireEvent.change(getByTestId("parc-valor"), { target: { value: "1000" } });
    fireEvent.click(getByTestId("negest-parcela-salvar"));

    expect(mockCreateParcela).toHaveBeenCalledTimes(1);
    // The dialog is STILL OPEN (onSuccess never fires on a mutation error) —
    // this is the whole point: an operator watching only the dialog (no
    // devtools) must see why nothing happened, without it silently closing.
    expect(queryByTestId("negest-parcela-erro")).toBeTruthy();
    expect(getByTestId("negest-parcela-erro").textContent).toContain(
      "at most 50 characters",
    );
    const { toast } = await import("sonner");
    expect(toast.error).toHaveBeenCalled();
  });

  it("reopening the dialog for a new parcela clears a previous error", async () => {
    mockCreateParcela.mockImplementation(
      (_payload: unknown, opts?: { onError?: (e: unknown) => void }) => {
        opts?.onError?.({ message: "[422] erro qualquer" });
      },
    );
    const { getByTestId, queryByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));
    fireEvent.change(getByTestId("parc-valor"), { target: { value: "1000" } });
    fireEvent.click(getByTestId("negest-parcela-salvar"));
    expect(getByTestId("negest-parcela-erro")).toBeTruthy();

    // Close (Radix Dialog's onOpenChange(false) — simulated by re-clicking
    // "Nova parcela", which this component always treats as a fresh open).
    fireEvent.click(getByTestId("negest-parcela-nova"));
    expect(queryByTestId("negest-parcela-erro")).toBeNull();
  });

  it("🔴 forma_pagamento e evento carregam o mesmo cap do backend (max_length) — não dá para digitar além dele", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));

    expect(getByTestId("parc-forma")).toHaveProperty("maxLength", 50);
    expect(getByTestId("parc-evento")).toHaveProperty("maxLength", 200);
  });
});

describe("nova parcela — fgts removido, permuta e corretagem", () => {
  it("🔴 'fgts' não aparece nas opções de uma parcela NOVA", async () => {
    const { getByTestId, queryByText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));

    expect(queryByText("FGTS (legado — junte ao financiamento)")).toBeNull();
  });

  it("uma parcela EXISTENTE de tipo fgts mantém 'fgts' selecionável na sua própria edição", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({
        data: aggregate({
          parcelas: [
            {
              id: "pf1",
              tipo: "fgts",
              valor: "10000.00",
              vencimento: null,
              evento: null,
              forma_pagamento: null,
              favorecido_id: null,
              confissao_divida: false,
              dispara_corretagem: false,
              permuta_ativo_ids: [],
              ordem: 1,
              created_at: null,
              updated_at: null,
            },
          ],
        }),
      }),
    );
    const { getByLabelText, getByRole } = await render();
    const { fireEvent, within } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Editar parcela"));

    const dialog = within(getByRole("dialog"));
    expect(dialog.queryByText("FGTS (legado — junte ao financiamento)")).toBeTruthy();
  });

  it("🔴 uma parcela legada de tipo fgts mostra o aviso na tabela", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({
        data: aggregate({
          parcelas: [
            {
              id: "pf1",
              tipo: "fgts",
              valor: "10000.00",
              vencimento: null,
              evento: null,
              forma_pagamento: null,
              favorecido_id: null,
              confissao_divida: false,
              dispara_corretagem: false,
              permuta_ativo_ids: [],
              ordem: 1,
              created_at: null,
              updated_at: null,
            },
          ],
        }),
      }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("parcela-fgts-aviso-pf1")).toBeTruthy();
  });

  it("o multi-select de imóveis de permuta só aparece quando tipo = permuta", async () => {
    mockUsePermutaAtivos.mockReturnValue(
      query({
        data: [
          {
            id: "ativo-1",
            natureza: "permuta_imovel",
            imovel_codigo: "IM-01",
            codigo: null,
            corretor_id: null,
            proprietario_nome: null,
            proprietario_telefone: null,
            tipo_imovel: "Casa",
            cidade: "Sorocaba",
            bairro: null,
            uf: null,
            zona: null,
            valor: null,
            observacoes: null,
            status: "disponivel",
            origem: "manual",
            tem_embedding: false,
            tem_embedding_interesses: false,
            interesses: [],
          },
        ],
      }),
    );
    const { getByTestId, getByText, queryByTestId } = await render();
    const { fireEvent, within } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));
    expect(queryByTestId("parc-permuta-ativos")).toBeNull();

    fireEvent.click(getByText("Permuta"));
    const grupo = getByTestId("parc-permuta-ativos");
    expect(grupo).toBeTruthy();
    expect(within(grupo).getByText(/IM-01/)).toBeTruthy();
  });

  it("🔴 o payload de criação inclui dispara_corretagem e permuta_ativo_ids", async () => {
    mockUsePermutaAtivos.mockReturnValue(
      query({
        data: [
          {
            id: "ativo-1",
            natureza: "permuta_imovel",
            imovel_codigo: "IM-01",
            codigo: null,
            corretor_id: null,
            proprietario_nome: null,
            proprietario_telefone: null,
            tipo_imovel: "Casa",
            cidade: "Sorocaba",
            bairro: null,
            uf: null,
            zona: null,
            valor: null,
            observacoes: null,
            status: "disponivel",
            origem: "manual",
            tem_embedding: false,
            tem_embedding_interesses: false,
            interesses: [],
          },
        ],
      }),
    );
    const { getByTestId, getByText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-parcela-nova"));
    fireEvent.change(getByTestId("parc-valor"), { target: { value: "1000" } });
    fireEvent.click(getByText("Permuta"));
    fireEvent.click(getByTestId("parc-permuta-ativo-ativo-1"));
    fireEvent.click(getByTestId("parc-dispara-corretagem"));
    fireEvent.click(getByTestId("negest-parcela-salvar"));

    expect(mockCreateParcela).toHaveBeenCalledTimes(1);
    const payload = mockCreateParcela.mock.calls[0][0];
    expect(payload.tipo).toBe("permuta");
    expect(payload.permuta_ativo_ids).toEqual(["ativo-1"]);
    expect(payload.dispara_corretagem).toBe(true);
  });
});
