/**
 * ValidacaoExtracaoDialog — owner decision D2's modal, presentational.
 *
 * Coverage: rows grouped by owner with value / source document / confidence;
 * per-field ✓ and ✗; "Aceitar tudo" / "Rejeitar tudo" send every pending
 * key; loading / empty / error states (never `isLoading`); a rejected
 * required value renders an inline input (or a "fill it on the card" note
 * when it has no single-input route); "Gerar contrato" only enables once
 * nothing is pending, no conflict is open and no inline input is still
 * waiting; open conflicts render read-only with a link to decide them.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConflitoExtracao, PendenteValidacao } from "@/hooks/useValidacaoExtracao";

import ValidacaoExtracaoDialog from "./ValidacaoExtracaoDialog";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

function pendente(over: Partial<PendenteValidacao> = {}): PendenteValidacao {
  return {
    chave: "cliente:v1:cpf",
    entidade: "cliente",
    entidade_id: "v1",
    campo: "cpf",
    grupo: "Fulano de Tal (proprietario)",
    rotulo: "CPF",
    valor: "12345678909",
    origem: "rg",
    fonte_documento_id: "d1",
    fonte_nome: "rg-fulano.pdf",
    confianca: "baixa",
    obrigatorio: true,
    edicao: { rota: "/api/clientes/v1", campo: "cpf", tipo: "texto" },
    ...over,
  };
}

const CERTIDAO = pendente({
  chave: "certidao:r1:certidao",
  entidade: "certidao",
  entidade_id: "r1",
  campo: "certidao",
  grupo: "Certidões — Fulano de Tal (proprietario)",
  rotulo: "Certidão — Protestos",
  valor: "resultado: negativa",
  origem: "api",
  fonte_nome: null,
  confianca: null,
  edicao: null,
});

async function render(over: Partial<Parameters<typeof ValidacaoExtracaoDialog>[0]> = {}) {
  const rtl = await import("@testing-library/react");
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    pendentes: [pendente(), CERTIDAO],
    conflitos: [] as ConflitoExtracao[],
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    onRetry: vi.fn(),
    decidindo: false,
    onDecidir: vi.fn(),
    rejeitados: [] as PendenteValidacao[],
    salvandoChave: null,
    onSalvarManual: vi.fn(),
    gerando: false,
    onProsseguir: vi.fn(),
    ...over,
  };
  rtl.render(<ValidacaoExtracaoDialog {...props} />);
  return { ...rtl, props };
}

describe("ValidacaoExtracaoDialog", () => {
  it("lists each pending value with its owner, source document and confidence", async () => {
    const { screen } = await render();
    const linha = screen.getByTestId("validacao-item-cliente:v1:cpf");
    expect(linha.textContent).toContain("CPF");
    expect(linha.textContent).toContain("12345678909");
    expect(linha.textContent).toContain("rg-fulano.pdf");
    expect(linha.textContent).toContain("Confiança baixa");
    expect(screen.getByText("Fulano de Tal (proprietario)")).toBeTruthy();
    expect(screen.getByTestId("validacao-item-certidao:r1:certidao").textContent).toContain(
      "Consulta automática",
    );
  });

  it("✓ and ✗ decide one field", async () => {
    const { screen, fireEvent, props } = await render();
    fireEvent.click(screen.getByTestId("validacao-aceitar-cliente:v1:cpf"));
    fireEvent.click(screen.getByTestId("validacao-rejeitar-certidao:r1:certidao"));
    expect(props.onDecidir).toHaveBeenNthCalledWith(1, [
      { chave: "cliente:v1:cpf", decisao: "aceito" },
    ]);
    expect(props.onDecidir).toHaveBeenNthCalledWith(2, [
      { chave: "certidao:r1:certidao", decisao: "rejeitado" },
    ]);
  });

  it("'Aceitar tudo' and 'Rejeitar tudo' send every pending key", async () => {
    const { screen, fireEvent, props } = await render();
    fireEvent.click(screen.getByTestId("validacao-aceitar-tudo"));
    fireEvent.click(screen.getByTestId("validacao-rejeitar-tudo"));
    expect(props.onDecidir).toHaveBeenNthCalledWith(1, [
      { chave: "cliente:v1:cpf", decisao: "aceito" },
      { chave: "certidao:r1:certidao", decisao: "aceito" },
    ]);
    expect(props.onDecidir).toHaveBeenNthCalledWith(2, [
      { chave: "cliente:v1:cpf", decisao: "rejeitado" },
      { chave: "certidao:r1:certidao", decisao: "rejeitado" },
    ]);
  });

  it("while anything is pending, 'Gerar contrato' is disabled", async () => {
    const { screen } = await render();
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
  });

  it("nothing pending: the empty state shows and 'Gerar contrato' proceeds", async () => {
    const { screen, fireEvent, props } = await render({ pendentes: [] });
    expect(screen.getByTestId("validacao-vazio")).toBeTruthy();
    expect(screen.queryByTestId("validacao-aceitar-tudo")).toBeNull();
    fireEvent.click(screen.getByTestId("validacao-prosseguir"));
    expect(props.onProsseguir).toHaveBeenCalledTimes(1);
  });

  it("first load shows the skeleton, not an empty list", async () => {
    const { screen } = await render({
      pendentes: undefined,
      showSkeleton: true,
    });
    expect(screen.getByTestId("validacao-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("validacao-vazio")).toBeNull();
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
  });

  it("a load error offers a retry", async () => {
    const { screen, fireEvent, props } = await render({
      pendentes: undefined,
      isError: true,
    });
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(props.onRetry).toHaveBeenCalledTimes(1);
  });

  it("🔴 a rejected required value with a manual route gets an inline input and blocks generation", async () => {
    const item = pendente();
    const { screen, fireEvent, props } = await render({
      pendentes: [],
      rejeitados: [item],
    });
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
    const salvar = screen.getByTestId("validacao-salvar-cliente:v1:cpf") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("validacao-input-cliente:v1:cpf"), {
      target: { value: " 98765432100 " },
    });
    fireEvent.click(salvar);
    expect(props.onSalvarManual).toHaveBeenCalledWith(item, "98765432100");
  });

  it("a rejected required value with NO single-input route is pointed at the card, not blocking", async () => {
    const { screen } = await render({ pendentes: [], rejeitados: [CERTIDAO] });
    expect(screen.getByTestId("validacao-rejeitado-certidao:r1:certidao").textContent).toContain(
      "preencha no card",
    );
    expect(screen.queryByTestId("validacao-input-certidao:r1:certidao")).toBeNull();
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(false);
  });

  it("a date field's inline input is a date input", async () => {
    const item = pendente({
      chave: "cliente:v1:data_casamento",
      campo: "data_casamento",
      rotulo: "Data do casamento",
      edicao: {
        rota: "/api/clientes/v1",
        campo: "data_casamento",
        tipo: "data",
      },
    });
    const { screen } = await render({ pendentes: [], rejeitados: [item] });
    expect(
      (screen.getByTestId("validacao-input-cliente:v1:data_casamento") as HTMLInputElement).type,
    ).toBe("date");
  });
});

describe("ValidacaoExtracaoDialog — open conflicts", () => {
  const CONFLITO: ConflitoExtracao = {
    id: "k1",
    entidade: "cliente",
    entidade_id: "v1",
    campo: "cpf",
    grupo: "Fulano de Tal (proprietario)",
    rotulo: "CPF",
    valor_atual: "111",
    valor_proposto: "222",
    origem_proposto: "rg",
    link: { rota: "/configuracoes", rotulo: "Configurações → Pendências" },
  };

  it("renders read-only with both values and a link, and blocks generation", async () => {
    const { screen } = await render({ pendentes: [], conflitos: [CONFLITO] });
    const linha = screen.getByTestId("validacao-conflito-k1");
    expect(linha.textContent).toContain("111");
    expect(linha.textContent).toContain("222");
    expect(screen.getByTestId("validacao-conflito-link-k1").getAttribute("href")).toBe(
      "/configuracoes",
    );
    expect(screen.queryByTestId("validacao-vazio")).toBeNull();
    expect(screen.queryByTestId("validacao-aceitar-k1")).toBeNull();
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
  });
});
