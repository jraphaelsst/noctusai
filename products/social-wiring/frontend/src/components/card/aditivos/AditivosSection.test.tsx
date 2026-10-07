/**
 * AditivosSection + AditivoEditor — the "Aditivos" block of a signed
 * contract (contrato-aditivos-CONTRACT). Presentational: plain props, no
 * query client. Synthetic data only.
 *
 * Pinned: all four states; "Novo aditivo" sends the chosen estilo; every
 * aditivo renders the DOM id the readiness "Resolver" targets; adding a
 * posse amendment is validated client-side and saved as ONE replace-all
 * PATCH; the payment schedule is edited through the negociação's own
 * parcela dialog (no permuta, no dispara-corretagem); a signed aditivo is
 * read-only; the version's legal review renders in aditivo mode.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// Radix Select → inline buttons (same convention as ContratosPanel.test).
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-disabled": disabled, "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", "data-value": value, onClick: () => ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

import { AditivosSection } from "./AditivosSection";
import type { AditivoOut } from "@/hooks/useContratoAditivos";
import type { VersaoOut } from "@/hooks/useContratos";

function versao(over: Partial<VersaoOut> = {}): VersaoOut {
  return {
    id: "va1",
    nome_original: "aditivo-gerado-v1.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 2048,
    tipo_documento: "aditivo",
    enviado_por: null,
    created_at: "2026-09-25T12:00:00+00:00",
    numero: 1,
    rotulo: null,
    origem: "gerado",
    docx_disponivel: true,
    modalidade_assinatura: "digital",
    revisao_juridica: {
      status: "aguardando",
      campos: [
        {
          chave: "aditivo:ad1:redacao",
          entidade: "aditivo",
          entidade_id: "ad1",
          campo: "redacao",
          rotulo: "Redação do aditivo (revisão jurídica obrigatória)",
          grupo: "Aditivo",
          origem: "gerado",
          fonte_documento_id: null,
          fonte_nome: null,
          confianca: null,
        },
      ],
      revisado_por: null,
      revisado_em: null,
    },
    ...over,
  };
}

function aditivo(over: Partial<AditivoOut> = {}): AditivoOut {
  return {
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
    ...over,
  };
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    aditivos: [aditivo()],
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    onRetry: vi.fn(),
    onCriar: vi.fn(),
    criando: false,
    favorecidos: [{ id: "f1", nome: "Vendedora Exemplo" }],
    onSalvar: vi.fn(),
    salvandoAditivoId: null,
    erroSalvar: null,
    onPatchStatus: vi.fn(),
    onOpenVersao: vi.fn(),
    onDownloadVersao: vi.fn(),
    podeAprovarRevisao: true,
    onAprovarRevisao: vi.fn(),
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const props = baseProps(over);
  rtl.render(<AditivosSection {...(props as any)} />);
  return { ...rtl, props };
}

describe("AditivosSection — states", () => {
  it("skeleton only when there is nothing to show", async () => {
    const { screen } = await render({ aditivos: undefined, showSkeleton: true });
    expect(screen.getByTestId("aditivos-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("aditivos-vazio")).toBeNull();
  });

  it("empty state names the next step", async () => {
    const { screen } = await render({ aditivos: [] });
    expect(screen.getByTestId("aditivos-vazio").textContent).toContain("Novo aditivo");
  });

  it("error with retry when nothing loaded", async () => {
    const onRetry = vi.fn();
    const { screen, fireEvent } = await render({ aditivos: undefined, isError: true, onRetry });
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("🔴 each aditivo renders the DOM id the readiness 'Resolver' lands on", async () => {
    const { screen } = await render();
    const bloco = screen.getByTestId("aditivo-ad1");
    expect(bloco.id).toBe("aditivo-ad1");
    expect(bloco.textContent).toContain("Primeiro aditivo");
  });
});

describe("AditivosSection — create + edit", () => {
  it("'Novo aditivo' sends the chosen estilo", async () => {
    const onCriar = vi.fn();
    const { screen, fireEvent } = await render({ aditivos: [], onCriar });
    const estilo = screen.getByTestId("aditivo-novo-estilo").parentElement as HTMLElement;
    fireEvent.click(estilo.querySelector('button[data-value="formal"]') as HTMLElement);
    fireEvent.click(screen.getByTestId("aditivo-novo-btn"));
    expect(onCriar).toHaveBeenCalledWith("formal");
  });

  it("🔴 a posse amendment is validated, then saved as ONE replace-all PATCH", async () => {
    const onSalvar = vi.fn();
    const { screen, fireEvent } = await render({ onSalvar });
    const salvar = screen.getByTestId("aditivo-salvar-ad1") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);

    fireEvent.click(screen.getByTestId("aditivo-adicionar-posse-ad1"));
    // Only one posse per aditivo.
    expect((screen.getByTestId("aditivo-adicionar-posse-ad1") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("aditivo-alteracao-erros-posse-ad1").textContent).toContain(
      "Informe a data da posse.",
    );
    expect(salvar.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("aditivo-clausula-posse-ad1"), { target: { value: "5" } });
    fireEvent.change(screen.getByTestId("aditivo-posse-data-ad1"), { target: { value: "2026-12-15" } });
    expect(screen.queryByTestId("aditivo-alteracao-erros-posse-ad1")).toBeNull();
    fireEvent.click(salvar);
    expect(onSalvar).toHaveBeenCalledWith("ad1", {
      estilo: "house",
      alteracoes: [
        { tipo: "posse", clausula_alvo: 5, data: "2026-12-15", precaria: false, finalidade: null },
      ],
      parcelas: [],
    });
  });

  it("🔴 the payment schedule uses the negociação parcela dialog — no permuta, no dispara-corretagem", async () => {
    const onSalvar = vi.fn();
    const { screen, fireEvent } = await render({ onSalvar });
    fireEvent.click(screen.getByTestId("aditivo-adicionar-pagamento-ad1"));
    fireEvent.change(screen.getByTestId("aditivo-clausula-pagamento-ad1"), { target: { value: "2" } });
    fireEvent.click(screen.getByTestId("aditivo-parcela-nova-ad1"));

    const tipos = screen.getByTestId("parc-tipo").parentElement as HTMLElement;
    expect(tipos.querySelector('button[data-value="permuta"]')).toBeNull();
    expect(screen.queryByTestId("parc-dispara-corretagem")).toBeNull();

    fireEvent.click(tipos.querySelector('button[data-value="sinal"]') as HTMLElement);
    fireEvent.change(screen.getByTestId("parc-valor"), { target: { value: "50.000,00" } });
    fireEvent.click(screen.getByText("Outro (texto livre)"));
    fireEvent.change(screen.getByTestId("parc-evento-texto"), {
      target: { value: "na assinatura do presente aditivo" },
    });
    fireEvent.change(screen.getByTestId("parc-forma"), { target: { value: "PIX" } });
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));

    expect(screen.getByTestId("aditivo-parcela-ad1-0").textContent).toContain("Parcela 01");
    fireEvent.click(screen.getByTestId("aditivo-salvar-ad1"));
    const [, patch] = onSalvar.mock.calls[0];
    expect(patch.alteracoes).toEqual([{ tipo: "pagamento", clausula_alvo: 2, novo_valor: null }]);
    expect(patch.parcelas).toEqual([
      {
        tipo: "sinal",
        valor: "50000.00",
        vencimento: null,
        evento: "na assinatura do presente aditivo",
        forma_pagamento: "PIX",
        favorecido_id: null,
        confissao_divida: false,
      },
    ]);
  });

  it("a save refusal is shown on the editor", async () => {
    const { screen } = await render({
      erroSalvar: { aditivoId: "ad1", mensagem: "O aditivo está assinado e não pode ser alterado." },
    });
    expect(screen.getByTestId("aditivo-salvar-erro-ad1").textContent).toContain("assinado");
  });

  it("a signed aditivo is read-only", async () => {
    const { screen } = await render({
      aditivos: [
        aditivo({
          status: "assinado",
          alteracoes: [{ tipo: "posse", clausula_alvo: 5, data: "2026-12-15", precaria: false }],
        }),
      ],
    });
    expect(screen.queryByTestId("aditivo-editor-ad1")).toBeNull();
    expect(screen.getByTestId("aditivo-resumo-ad1").textContent).toContain("definitiva em 15/12/2026");
  });
});

describe("AditivosSection — versions + legal review", () => {
  it("🔴 the current version awaits the review in ADITIVO wording; admin approves it", async () => {
    const onAprovarRevisao = vi.fn();
    const { screen, fireEvent } = await render({
      aditivos: [aditivo({ versao_atual: versao(), versoes: [versao()] })],
      onAprovarRevisao,
    });
    expect(screen.getByTestId("aditivo-rascunho-ad1")).toBeTruthy();
    expect(screen.getByTestId("aditivo-revisao-texto-ad1").textContent).toContain(
      "revise o aditivo por inteiro",
    );
    fireEvent.click(screen.getByTestId("aditivo-revisao-aprovar-ad1"));
    fireEvent.click(screen.getByTestId("aditivo-revisao-aprovar-confirmar-ad1"));
    expect(onAprovarRevisao).toHaveBeenCalledWith("ad1", "va1");
  });

  it("opens / downloads the PDF and the .docx of a version", async () => {
    const onOpenVersao = vi.fn();
    const onDownloadVersao = vi.fn();
    const { screen, fireEvent } = await render({
      aditivos: [aditivo({ versao_atual: versao(), versoes: [versao()] })],
      onOpenVersao,
      onDownloadVersao,
    });
    fireEvent.click(screen.getByTestId("aditivo-versao-abrir-va1"));
    expect(onOpenVersao).toHaveBeenCalledWith("ad1", "va1", undefined);
    fireEvent.click(screen.getByTestId("aditivo-versao-baixar-docx-va1"));
    expect(onDownloadVersao).toHaveBeenCalledWith("ad1", "va1", "docx", undefined);
  });

  it("'Baixar para impressão' (física) waits for the review", async () => {
    const { screen } = await render({
      aditivos: [
        aditivo({ modalidade_assinatura: "fisica", versao_atual: versao(), versoes: [versao()] }),
      ],
    });
    expect((screen.getByTestId("aditivo-imprimir-ad1") as HTMLButtonElement).disabled).toBe(true);
  });
});
