/**
 * NegociacoesDoClienteSection — the titular's "Negociações" block
 * (`pessoa-mesma-cpf-multideal-CONTRACT.md` §2/3, brief 2026-09-28 item 2).
 * `useNegociacoesDoCliente` is mocked (this suite does not mount a
 * QueryClientProvider), mirroring every other card-section test's pattern.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseNegociacoesDoCliente = vi.fn();

vi.mock("@/hooks/useClientes", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientes")>(
    "@/hooks/useClientes",
  );
  return { ...actual, useNegociacoesDoCliente: mockUseNegociacoesDoCliente };
});

async function renderSection(clienteId = "cl1", atendimentoAtualId: string | null = null) {
  const React = (await import("react")).default;
  const { MemoryRouter } = await import("react-router-dom");
  const { NegociacoesDoClienteSection } = await import("./NegociacoesDoClienteSection");
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(NegociacoesDoClienteSection, { clienteId, atendimentoAtualId }),
    ),
  );
}

function negociacao(overrides: Partial<any> = {}) {
  return {
    atendimento_id: "a1",
    titulo: "Apto Jardins",
    status: null,
    etapa_id: null,
    etapa_label: "Proposta",
    pipeline: null,
    imovel_codigo: "IM-1",
    lado: "comprador",
    papel: "titular",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("NegociacoesDoClienteSection — loading/error", () => {
  it("shows a loading message before any data has arrived", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: true,
      isFetching: true,
      isError: false,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByText } = await renderSection();
    expect(getByText("Carregando negociações…")).toBeTruthy();
  });

  it("shows an error message with a retry action", async () => {
    const refetch = vi.fn();
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: true,
      data: undefined,
      refetch,
    });
    const { getByText } = await renderSection();
    expect(getByText("Não foi possível carregar as negociações.")).toBeTruthy();
  });
});

describe("NegociacoesDoClienteSection — empty (only this deal)", () => {
  it("reads as an informational empty state when there is nothing besides the current card", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        cliente_id: "cl1",
        negociacoes: [negociacao({ atendimento_id: "current" })],
        total_negociacoes: 1,
        candidatos_pendentes: [],
      },
      refetch: vi.fn(),
    });
    const { getByTestId, queryByTestId } = await renderSection("cl1", "current");
    expect(getByTestId("negociacoes-do-cliente-vazio")).toBeTruthy();
    expect(queryByTestId("negociacoes-do-cliente-lista")).toBeNull();
    expect(queryByTestId("badge-outras-negociacoes")).toBeNull();
  });
});

describe("NegociacoesDoClienteSection — other deals", () => {
  it("lists every OTHER deal (título, papel/lado, etapa, imóvel) and links to the funil", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        cliente_id: "cl1",
        negociacoes: [
          negociacao({ atendimento_id: "current" }),
          negociacao({
            atendimento_id: "a2",
            titulo: "Casa Moema",
            lado: "vendedor",
            papel: "proprietario",
            etapa_label: "Visitas",
            imovel_codigo: "IM-2",
          }),
        ],
        total_negociacoes: 2,
        candidatos_pendentes: [],
      },
      refetch: vi.fn(),
    });
    const { getByTestId, getByText, queryByText } = await renderSection("cl1", "current");

    // The current card's own deal never lists itself as an "other" one.
    expect(queryByText("Apto Jardins")).toBeNull();
    expect(getByText("Casa Moema")).toBeTruthy();
    expect(getByText(/Venda · Proprietário · Visitas · imóvel IM-2/)).toBeTruthy();
    expect(getByTestId("negociacoes-do-cliente-abrir").getAttribute("href")).toBe(
      "/funil?atendimento=a2&cliente=cl1",
    );
    expect(getByTestId("badge-outras-negociacoes")).toBeTruthy();
  });

  it("surfaces the possível-duplicata badge, linking to the CPF review tab", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        cliente_id: "cl1",
        negociacoes: [],
        total_negociacoes: 0,
        candidatos_pendentes: [
          { cpf_normalizado: "12345678901", candidatos: [{ id: "cl1", nome: "Maria", cpf: "12345678901" }] },
        ],
      },
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderSection();
    const badge = getByTestId("badge-possivel-duplicata");
    expect(badge.getAttribute("href")).toBe("/clientes/revisao?tab=cpf");
  });
});
