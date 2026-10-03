/**
 * AditivosContainer — wiring between the aditivo hooks and the presentational
 * section: fetches gated on the collapsible, favorecidos from the SAME
 * negociação query, a save refusal routed ONTO the editor (not only a toast).
 * Hooks are mocked at the module boundary. Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { atualizarMutate, useAditivosMock, useNegociacaoMock } = vi.hoisted(() => ({
  atualizarMutate: vi.fn(),
  useAditivosMock: vi.fn(),
  useNegociacaoMock: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/hooks/useContratoAditivos", async (orig) => {
  const real = await orig<typeof import("@/hooks/useContratoAditivos")>();
  const mut = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, variables: undefined });
  return {
    ...real,
    useAditivos: useAditivosMock,
    useAditivoGeracao: vi.fn(() => ({ data: undefined, isPending: true, isFetching: false, isError: false, refetch: vi.fn() })),
    useAditivoMutations: vi.fn(() => ({
      criar: mut(),
      atualizar: { ...mut(), mutate: atualizarMutate },
      gerar: mut(),
      getUrl: mut(),
      aprovarRevisaoJuridica: mut(),
    })),
  };
});

vi.mock("@/hooks/useNegociacaoEstruturada", () => ({
  useNegociacaoEstruturada: useNegociacaoMock,
}));

import { AditivosContainer } from "./AditivosContainer";

const ADITIVO = {
  id: "ad1",
  contrato_id: "c1",
  ordinal: 1,
  estilo: "house",
  status: "rascunho",
  status_em: null,
  status_por: null,
  alteracoes: [],
  parcelas: [],
  assinatura_data: null,
  modalidade_assinatura: "digital",
  created_at: "2026-09-24T12:00:00+00:00",
  updated_at: null,
  versao_atual: null,
  versoes: [],
};

describe("AditivosContainer", () => {
  it("🔴 gates every fetch on the collapsible being open", async () => {
    useAditivosMock.mockReturnValue({ data: undefined, isPending: true, isFetching: false, isError: false });
    useNegociacaoMock.mockReturnValue({ data: undefined });
    const rtl = await import("@testing-library/react");
    rtl.render(<AditivosContainer clienteId="cl1" contratoId="c1" aberto={false} isAdmin={false} />);
    expect(useAditivosMock).toHaveBeenCalledWith("cl1", "c1", false);
    expect(useNegociacaoMock).toHaveBeenCalledWith(null);
    expect(rtl.screen.queryByTestId("aditivos-skeleton")).toBeNull();
  });

  it("🔴 a save refusal is shown on the editor, with the server's sentence", async () => {
    useAditivosMock.mockReturnValue({ data: [ADITIVO], isPending: false, isFetching: false, isError: false });
    useNegociacaoMock.mockReturnValue({ data: { favorecidos: [{ id: "f1", nome: "Vendedora Exemplo" }] } });
    atualizarMutate.mockImplementation((_vars, opts) =>
      opts.onError(new Error("O aditivo está assinado e não pode ser alterado.")),
    );
    const rtl = await import("@testing-library/react");
    rtl.render(<AditivosContainer clienteId="cl1" contratoId="c1" aberto isAdmin />);
    expect(useNegociacaoMock).toHaveBeenCalledWith("cl1");

    rtl.fireEvent.click(rtl.screen.getByTestId("aditivo-adicionar-outro-ad1"));
    rtl.fireEvent.change(rtl.screen.getByTestId("aditivo-outro-titulo-ad1"), {
      target: { value: "Da trava de dados bancários" },
    });
    rtl.fireEvent.change(rtl.screen.getByTestId("aditivo-outro-texto-ad1"), {
      target: { value: "Fica vedada qualquer alteração dos dados bancários." },
    });
    rtl.fireEvent.click(rtl.screen.getByTestId("aditivo-salvar-ad1"));

    expect(atualizarMutate).toHaveBeenCalledWith(
      {
        aditivoId: "ad1",
        patch: {
          estilo: "house",
          alteracoes: [
            {
              tipo: "outro",
              clausula_alvo: null,
              titulo: "Da trava de dados bancários",
              texto: "Fica vedada qualquer alteração dos dados bancários.",
            },
          ],
          parcelas: [],
        },
      },
      expect.anything(),
    );
    expect((await rtl.screen.findByTestId("aditivo-salvar-erro-ad1")).textContent).toContain(
      "não pode ser alterado",
    );
  });
});
