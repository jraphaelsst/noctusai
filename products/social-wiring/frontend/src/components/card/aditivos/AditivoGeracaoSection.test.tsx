/**
 * AditivoGeracaoSection — readiness + "Gerar aditivo", rendered through the
 * contract generator's own `ProntidaoListas`/`ErroGeracaoDetalhes`.
 * Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { MemoryRouter } from "react-router-dom";

import { AditivoGeracaoSection } from "./AditivoGeracaoSection";
import type { AditivoGeracao } from "@/hooks/useContratoAditivos";
import { ContratoGeracaoError } from "@/hooks/useContratos";

function geracao(over: Partial<AditivoGeracao> = {}): AditivoGeracao {
  return {
    aditivo_id: "ad1",
    contrato_id: "c1",
    ordinal: 1,
    estilo: "house",
    assinatura_data: "2026-09-20",
    pronto: true,
    faltando: [],
    bloqueios: [],
    avisos: [],
    revisao_juridica_exigida: true,
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const props = {
    aditivoId: "ad1",
    geracao: geracao(),
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    onRetry: vi.fn(),
    assinaturaData: "2026-09-20",
    onAssinaturaDataChange: vi.fn(),
    gerando: false,
    onGerar: vi.fn(),
    erroGeracao: null,
    avisosGerados: null,
    ...over,
  };
  rtl.render(
    <MemoryRouter>
      <AditivoGeracaoSection {...(props as any)} />
    </MemoryRouter>,
  );
  return { ...rtl, props };
}

describe("AditivoGeracaoSection", () => {
  it("skeleton while the first check runs; error with retry", async () => {
    const a = await render({ geracao: undefined, showSkeleton: true });
    expect(a.screen.getByTestId("aditivo-geracao-ad1-skeleton")).toBeTruthy();
    a.cleanup();
    const onRetry = vi.fn();
    const b = await render({ geracao: undefined, isError: true, onRetry });
    b.fireEvent.click(b.screen.getByText("Tentar novamente"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("pronto → 'Gerar aditivo' generates", async () => {
    const onGerar = vi.fn();
    const { screen, fireEvent } = await render({ onGerar });
    expect(screen.getByTestId("aditivo-geracao-ad1-pronto")).toBeTruthy();
    fireEvent.click(screen.getByTestId("aditivo-geracao-ad1-btn"));
    expect(onGerar).toHaveBeenCalled();
  });

  it("🔴 a falta about the aditivo itself 'Resolver's onto its editor", async () => {
    const onIrPara = vi.fn();
    const destino = {
      tela: "card_contratos",
      rota: "/clientes",
      ancora: "contratos",
      alvo: "aditivo-ad1",
      ids: { cliente_id: "cl1", contrato_id: "c1" },
    };
    const { screen, fireEvent } = await render({
      onIrPara,
      geracao: geracao({
        pronto: false,
        faltando: [
          { campo: "aditivo.alteracoes", rotulo: "Alterações do aditivo", onde: "contrato", parte_id: null, destino } as any,
        ],
        bloqueios: [{ codigo: "SOMA_PARCELAS_DIFERENTE_DO_PRECO", mensagem: "A soma das parcelas difere do preço." }],
      }),
    });
    expect((screen.getByTestId("aditivo-geracao-ad1-btn") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("aditivo-geracao-ad1-bloqueios").textContent).toContain("soma das parcelas");
    fireEvent.click(screen.getByTestId("aditivo-geracao-ad1-faltando-ir-aditivo.alteracoes-"));
    expect(onIrPara).toHaveBeenCalledWith(destino);
  });

  it("unsaved editor changes hold the button", async () => {
    const { screen } = await render({ temAlteracoesNaoSalvas: true });
    expect(screen.getByTestId("aditivo-geracao-ad1-nao-salvo")).toBeTruthy();
    expect((screen.getByTestId("aditivo-geracao-ad1-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a refusal's details", async () => {
    const erro = new ContratoGeracaoError("ADITIVO_INCOMPLETO", "O aditivo não pode ser gerado.", {
      bloqueios: [{ codigo: "MAIS_DE_UM_SINAL", mensagem: "Há mais de um sinal." }],
    });
    const { screen } = await render({ erroGeracao: erro });
    const box = screen.getByTestId("aditivo-geracao-ad1-erro-incompleto");
    expect(box.textContent).toContain("O aditivo não pode ser gerado.");
    expect(box.textContent).toContain("Há mais de um sinal.");
  });
});
