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
  it("lista o que falta quando incompleto", async () => {
    mockUseNegociacaoEstruturada.mockReturnValue(
      query({
        data: aggregate({
          completude: {
            completo: false,
            faltando: ["valor_negociado", "ao menos 1 parcela"],
          },
        }),
      }),
    );
    const { getByText } = await render();
    expect(getByText("valor_negociado")).toBeTruthy();
    expect(getByText("ao menos 1 parcela")).toBeTruthy();
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
  it("🔴 o 400 do backend ('sem valor_negociado ou sem saldo') chega via toast", async () => {
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
  });
});
