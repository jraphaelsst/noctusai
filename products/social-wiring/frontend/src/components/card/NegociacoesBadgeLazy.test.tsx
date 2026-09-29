/**
 * NegociacoesBadgeLazy — the comprador/vendedor party-row signal. This
 * component ONLY mounts once its `PessoaDocumentosSection` row is expanded
 * (see its own docblock) — this suite exercises what it renders once
 * mounted, not the expand mechanics themselves (covered by
 * `ClienteCardDialog`'s own render-prop wiring).
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

async function renderBadge(clienteId = "parte1", excludeAtendimentoId: string | undefined = undefined) {
  const React = (await import("react")).default;
  const { MemoryRouter } = await import("react-router-dom");
  const { NegociacoesBadgeLazy } = await import("./NegociacoesBadgeLazy");
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(NegociacoesBadgeLazy, { clienteId, excludeAtendimentoId }),
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("NegociacoesBadgeLazy", () => {
  it("renders nothing while pending — no flash of an empty badge row", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: true,
      isError: false,
      data: undefined,
    });
    const { container } = await renderBadge();
    expect(container.textContent).toBe("");
  });

  it("renders nothing on error, rather than surfacing a scary badge", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isError: true,
      data: undefined,
    });
    const { container } = await renderBadge();
    expect(container.textContent).toBe("");
  });

  it("shows the 'outras negociações' badge once loaded, excluding the current card's own deal", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        cliente_id: "parte1",
        negociacoes: [
          { atendimento_id: "current", titulo: "T1", status: null, etapa_id: null, etapa_label: null, pipeline: null, imovel_codigo: null, lado: "comprador", papel: "comprador" },
          { atendimento_id: "outro", titulo: "T2", status: null, etapa_id: null, etapa_label: null, pipeline: null, imovel_codigo: null, lado: "vendedor", papel: "proprietario" },
        ],
        total_negociacoes: 2,
        candidatos_pendentes: [],
      },
    });
    const { getByTestId } = await renderBadge("parte1", "current");
    expect(getByTestId("badge-outras-negociacoes")).toBeTruthy();
  });

  it("renders nothing when there is no signal (one deal, no pending candidates)", async () => {
    mockUseNegociacoesDoCliente.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        cliente_id: "parte1",
        negociacoes: [
          { atendimento_id: "current", titulo: "T1", status: null, etapa_id: null, etapa_label: null, pipeline: null, imovel_codigo: null, lado: "comprador", papel: "comprador" },
        ],
        total_negociacoes: 1,
        candidatos_pendentes: [],
      },
    });
    const { container } = await renderBadge("parte1", "current");
    expect(container.textContent).toBe("");
  });
});
