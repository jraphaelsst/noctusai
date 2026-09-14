/**
 * GeradorContratoContainer — the "Gerar contrato" fetch/mutation owner.
 *
 * Coverage: `aberto` is the lazy gate passed straight into
 * `useContratoGeracao` (the section must not fetch before it is opened), the
 * "Gerar versão" click calls `gerar.mutate` with the right payload, a 400
 * `CONTRATO_INCOMPLETO` renders its details, and a successful 201 renders the
 * returned `avisos`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockUseContratoGeracao = vi.fn();
const mockGerarMutate = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/hooks/useContratos", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useContratos")>("@/hooks/useContratos");
  return {
    ...actual,
    useContratoGeracao: (...args: unknown[]) => mockUseContratoGeracao(...args),
    useContratoMutations: () => ({
      create: {},
      addVersao: {},
      patch: {},
      deleteVersao: {},
      deleteContrato: {},
      getUrl: {},
      gerar: { mutate: mockGerarMutate, isPending: false },
    }),
  };
});

import { GeradorContratoContainer } from "./GeradorContratoContainer";
import { ContratoGeracaoError, type ContratoGeracaoStatus } from "@/hooks/useContratos";

function statusFixture(over: Partial<ContratoGeracaoStatus> = {}): ContratoGeracaoStatus {
  return {
    contrato_id: "c1",
    pronto: true,
    modelo_derivado: "compra_venda",
    modelo_confere: true,
    switches: {},
    faltando: [],
    bloqueios: [],
    avisos: [],
    ...over,
  };
}

beforeEach(() => {
  mockUseContratoGeracao.mockReset();
  mockGerarMutate.mockReset();
  mockRefetch.mockReset();
  mockUseContratoGeracao.mockReturnValue({
    data: statusFixture(),
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: mockRefetch,
  });
});

// 🔴 `screen`, NOT the render result's bound queries — see
// `GeradorContratoSection.test.tsx`'s header note on why `{...view, ...rtl}`
// makes a bare `getByTestId` resolve to the unbound (container, id) overload.
async function render(aberto = true) {
  const rtl = await import("@testing-library/react");
  rtl.render(<GeradorContratoContainer clienteId="cli1" contratoId="c1" aberto={aberto} />);
  return rtl;
}

describe("GeradorContratoContainer", () => {
  it("🔴 LAZY FETCH — `aberto=false` is passed straight through as the readiness query's enabled gate", async () => {
    await render(false);
    expect(mockUseContratoGeracao).toHaveBeenCalledWith("cli1", "c1", false);
  });

  it("`aberto=true` (the section is open) enables the readiness query", async () => {
    await render(true);
    expect(mockUseContratoGeracao).toHaveBeenCalledWith("cli1", "c1", true);
  });

  it("'Gerar versão' calls gerar.mutate with the contract id and a non-empty assinatura_data draft", async () => {
    const { screen, fireEvent } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    expect(mockGerarMutate).toHaveBeenCalledTimes(1);
    const [vars] = mockGerarMutate.mock.calls[0];
    expect(vars.contratoId).toBe("c1");
    expect(typeof vars.assinaturaData).toBe("string");
    expect(vars.assinaturaData.length).toBeGreaterThan(0);
  });

  it("🔴 a 400 CONTRATO_INCOMPLETO shows details.faltando/bloqueios via the section", async () => {
    const { screen, fireEvent, act } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    const [, opts] = mockGerarMutate.mock.calls[0];
    const erro = new ContratoGeracaoError("CONTRATO_INCOMPLETO", "Contrato incompleto.", {
      faltando: [{ campo: "cpf", rotulo: "CPF do comprador", onde: "partes", parte_id: "p1" }],
      bloqueios: [{ codigo: "sem_testemunha", mensagem: "Falta uma testemunha." }],
    });
    act(() => {
      opts.onError(erro);
    });
    const bloco = screen.getByTestId("gerador-contrato-erro-incompleto");
    expect(bloco.textContent).toContain("Contrato incompleto.");
    expect(bloco.textContent).toContain("CPF do comprador");
    expect(bloco.textContent).toContain("Falta uma testemunha.");
  });

  it("🔴 a successful 201 renders the returned avisos", async () => {
    const { screen, fireEvent, act } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    const [, opts] = mockGerarMutate.mock.calls[0];
    act(() => {
      opts.onSuccess({
        versao: {
          id: "v2",
          nome_original: "contrato.pdf",
          mime_type: "application/pdf",
          tamanho_bytes: 1024,
          tipo_documento: "contrato",
          enviado_por: null,
          created_at: "2026-09-14T00:00:00+00:00",
          numero: 2,
          rotulo: null,
          origem: "gerado",
        },
        avisos: [{ codigo: "prazo_padrao", mensagem: "Cláusula de foro padrão aplicada." }],
      });
    });
    expect(screen.getByTestId("gerador-contrato-avisos-pos-geracao").textContent).toContain(
      "Cláusula de foro padrão aplicada.",
    );
  });
});
