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

// D2 validation gate — the pre-check answers "nothing pending" by default,
// so every pre-existing case below still reaches `gerar.mutate`.
const mockVerificarMutate = vi.fn();
const mockDecidirMutate = vi.fn();
const mockSalvarMutate = vi.fn();
const mockUseValidacaoExtracao = vi.fn();

vi.mock("@/hooks/useValidacaoExtracao", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useValidacaoExtracao")>(
    "@/hooks/useValidacaoExtracao",
  );
  return {
    ...actual,
    useValidacaoExtracao: (...args: unknown[]) => mockUseValidacaoExtracao(...args),
    useValidacaoExtracaoMutations: () => ({
      verificar: { mutate: mockVerificarMutate, isPending: false },
      decidir: { mutate: mockDecidirMutate, isPending: false },
      salvarManual: { mutate: mockSalvarMutate, isPending: false },
    }),
  };
});

import { GeradorContratoContainer } from "./GeradorContratoContainer";
import type { ConflitoExtracao, PendenteValidacao } from "@/hooks/useValidacaoExtracao";
import { ContratoGeracaoError, type ContratoGeracaoStatus } from "@/hooks/useContratos";

function statusFixture(over: Partial<ContratoGeracaoStatus> = {}): ContratoGeracaoStatus {
  return {
    contrato_id: "c1",
    pronto: true,
    modelo_derivado: "compra_venda",
    modelo_confere: true,
    modelo_automatico: false,
    processo_legado: false,
    modalidade_assinatura: "digital",
    switches: {},
    faltando: [],
    bloqueios: [],
    avisos: [],
    ...over,
  };
}

let pendentesAtuais: PendenteValidacao[] = [];
let conflitosAtuais: ConflitoExtracao[] = [];

beforeEach(() => {
  mockUseContratoGeracao.mockReset();
  mockGerarMutate.mockReset();
  mockRefetch.mockReset();
  mockVerificarMutate.mockReset();
  mockDecidirMutate.mockReset();
  mockSalvarMutate.mockReset();
  mockUseValidacaoExtracao.mockReset();
  pendentesAtuais = [];
  conflitosAtuais = [];
  mockVerificarMutate.mockImplementation(
    (
      _: unknown,
      opts: {
        onSuccess: (s: { pendentes: PendenteValidacao[]; conflitos: ConflitoExtracao[] }) => void;
      },
    ) =>
      opts.onSuccess({
        pendentes: pendentesAtuais,
        conflitos: conflitosAtuais,
      }),
  );
  mockUseValidacaoExtracao.mockImplementation(() => ({
    data: { pendentes: pendentesAtuais, conflitos: conflitosAtuais },
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  }));
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
      faltando: [
        {
          campo: "cpf",
          rotulo: "CPF do comprador",
          onde: "partes",
          parte_id: "p1",
        },
      ],
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
        avisos: [
          {
            codigo: "prazo_padrao",
            mensagem: "Cláusula de foro padrão aplicada.",
          },
        ],
      });
    });
    expect(screen.getByTestId("gerador-contrato-avisos-pos-geracao").textContent).toContain(
      "Cláusula de foro padrão aplicada.",
    );
  });
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
    confianca: "alta",
    obrigatorio: true,
    edicao: { rota: "/api/clientes/v1", campo: "cpf", tipo: "texto" },
    ...over,
  };
}

describe("GeradorContratoContainer — D2 validation gate", () => {
  it("nothing pending: 'Gerar versão' goes straight to generate, no dialog", async () => {
    const { screen, fireEvent } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    expect(mockVerificarMutate).toHaveBeenCalledTimes(1);
    expect(mockGerarMutate).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("validacao-dialog")).toBeNull();
  });

  it("🔴 something pending: the dialog opens and generate is NOT called", async () => {
    pendentesAtuais = [pendente()];
    const { screen, fireEvent } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    expect(mockGerarMutate).not.toHaveBeenCalled();
    expect(screen.getByTestId("validacao-dialog")).toBeTruthy();
    expect(screen.getByTestId("validacao-item-cliente:v1:cpf").textContent).toContain(
      "12345678909",
    );
    expect(mockUseValidacaoExtracao).toHaveBeenLastCalledWith("cli1", "c1", true);
  });

  it("a rejected REQUIRED value gets an inline input that writes through its manual route", async () => {
    const item = pendente();
    pendentesAtuais = [item];
    const { screen, fireEvent, act } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    fireEvent.click(screen.getByTestId("validacao-rejeitar-cliente:v1:cpf"));
    const [decisoes, opts] = mockDecidirMutate.mock.calls[0];
    expect(decisoes).toEqual([{ chave: "cliente:v1:cpf", decisao: "rejeitado" }]);
    act(() => {
      pendentesAtuais = [];
      opts.onSuccess({ aplicadas: 1, pendentes: [], conflitos: [] });
    });
    // Nothing pending, but the rejected required value still blocks generation.
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("validacao-input-cliente:v1:cpf"), {
      target: { value: "98765432100" },
    });
    fireEvent.click(screen.getByTestId("validacao-salvar-cliente:v1:cpf"));
    const [vars, salvarOpts] = mockSalvarMutate.mock.calls[0];
    expect(vars).toEqual({ edicao: item.edicao, valor: "98765432100" });
    act(() => {
      salvarOpts.onSuccess();
      salvarOpts.onSettled();
    });
    expect(screen.queryByTestId("validacao-rejeitado-cliente:v1:cpf")).toBeNull();
    fireEvent.click(screen.getByTestId("validacao-prosseguir"));
    expect(mockGerarMutate).toHaveBeenCalledTimes(1);
  });

  it("an open extraction conflict alone opens the dialog and blocks generation", async () => {
    conflitosAtuais = [
      {
        id: "k1",
        entidade: "imovel",
        entidade_id: "EX001",
        campo: "numero_matricula",
        grupo: "Imóvel EX001",
        rotulo: "Número da matrícula",
        valor_atual: "12345",
        valor_proposto: "12346",
        origem_proposto: "matricula",
        link: { rota: "/imoveis/EX001?conflito=k1", rotulo: "Imóvel EX001" },
      },
    ];
    const { screen, fireEvent } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    expect(mockGerarMutate).not.toHaveBeenCalled();
    expect(screen.getByTestId("validacao-conflito-k1")).toBeTruthy();
    expect((screen.getByTestId("validacao-prosseguir") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 a 409 EXTRACAO_PENDENTE_VALIDACAO from gerar reopens the dialog instead of erroring", async () => {
    const { screen, fireEvent, act } = await render();
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    const [, opts] = mockGerarMutate.mock.calls[0];
    pendentesAtuais = [pendente()];
    act(() => {
      opts.onError(
        new ContratoGeracaoError("EXTRACAO_PENDENTE_VALIDACAO", "Há dados pendentes.", null),
      );
    });
    expect(screen.getByTestId("validacao-dialog")).toBeTruthy();
    expect(screen.queryByTestId("gerador-contrato-erro-incompleto")).toBeNull();
  });
});
