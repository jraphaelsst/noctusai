/**
 * AdicionarCompradorDialog — PF/PJ toggle, CPF/CNPJ lookup (§2.5), reuse of an
 * existing cadastro, and the stale-certidões warning. The lookup hook is
 * mocked at the hook boundary with contract-shaped fixtures.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ParteLookup } from "@/types/partes";

const { mockLookup } = vi.hoisted(() => ({ mockLookup: vi.fn() }));
vi.mock("@/hooks/usePartes", () => ({ useParteLookup: mockLookup }));

import { AdicionarCompradorDialog } from "./AdicionarCompradorDialog";

const CPF_OK = "529.982.247-25";
const CNPJ_OK = "11.222.333/0001-81";

function lookupBase(over: Partial<ParteLookup> = {}): ParteLookup {
  return {
    documento: "52998224725",
    tipo_documento: "cpf",
    encontrado: "cliente",
    cliente: {
      id: "cli-9",
      nome: "Maria",
      nome_oficial: "Maria Souza",
      cpf: "52998224725",
      celular: null,
      email: null,
    },
    empresa: null,
    ja_no_atendimento: false,
    atendimentos: [
      {
        id: "a1", titulo: "A1", etapa: null, status: "aberto", arquivado: false,
        lado: "comprador", papel: "comprador", titular: true, parte_id: null,
      },
      {
        id: "a2", titulo: "A2", etapa: null, status: "aberto", arquivado: false,
        lado: "vendedor", papel: "proprietario", titular: false, parte_id: "p2",
      },
    ],
    certidoes: {
      max_dias: 30,
      data_referencia: "2026-10-01",
      itens: [],
      tipos_vencidos: [],
      alerta_vencidas: false,
      mensagem: null,
    },
    ...over,
  };
}

function resposta(data: ParteLookup | undefined) {
  return { data, showSkeleton: false, isRefreshing: false, isError: false, error: null };
}

beforeEach(() => {
  mockLookup.mockReturnValue(resposta(undefined));
});
afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockLookup.mockReset();
});

async function abrir(props: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onCreate = vi.fn();
  rtl.render(
    <AdicionarCompradorDialog
      open
      onOpenChange={vi.fn()}
      onCreate={onCreate}
      clienteId="titular-1"
      atendimentoId="at-1"
      {...props}
    />,
  );
  return { ...rtl, onCreate };
}

function digitarDocumento(rtl: typeof import("@testing-library/react"), valor: string) {
  rtl.fireEvent.change(rtl.screen.getByTestId("comprador-documento-input"), {
    target: { value: valor },
  });
}

describe("AdicionarCompradorDialog — lookup por documento", () => {
  it("só consulta com documento completo e válido (debounce natural: chave nula até lá)", async () => {
    const rtl = await abrir();
    expect(mockLookup).toHaveBeenLastCalledWith("titular-1", null, "at-1");

    digitarDocumento(rtl, "529.982");
    expect(mockLookup).toHaveBeenLastCalledWith("titular-1", null, "at-1");

    digitarDocumento(rtl, "111.111.111-11"); // check digits invalid
    expect(mockLookup).toHaveBeenLastCalledWith("titular-1", null, "at-1");

    digitarDocumento(rtl, CPF_OK);
    expect(mockLookup).toHaveBeenLastCalledWith("titular-1", "52998224725", "at-1");
  });

  it("🔴 match: mostra 'Já cadastrado … em N outros atendimentos' e reaproveita via cliente_id", async () => {
    mockLookup.mockReturnValue(resposta(lookupBase()));
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);

    const aviso = rtl.screen.getByTestId("parte-lookup-ja-cadastrado").textContent ?? "";
    expect(aviso).toContain("Já cadastrado:");
    expect(aviso).toContain("Maria Souza");
    expect(aviso).toContain("em 2 outros atendimentos");

    rtl.fireEvent.click(rtl.screen.getByTestId("parte-lookup-usar-btn"));
    // While reusing, the new-person fields are gone and submit is enabled.
    expect(rtl.screen.queryByTestId("comprador-nome-input")).toBeNull();
    rtl.fireEvent.click(rtl.screen.getByTestId("comprador-salvar-btn"));
    expect(rtl.onCreate).toHaveBeenCalledWith({ cliente_id: "cli-9" });
    // Exactly ONE identifier (contract §2.3).
    expect(Object.keys(rtl.onCreate.mock.calls[0][0])).toEqual(["cliente_id"]);
  });

  it("match de empresa reaproveita via empresa_id", async () => {
    mockLookup.mockReturnValue(
      resposta(
        lookupBase({
          documento: "11222333000181",
          tipo_documento: "cnpj",
          encontrado: "empresa",
          cliente: null,
          empresa: {
            id: "emp-3", razao_social: "NEON PARK LTDA", nome_fantasia: null,
            cnpj: "11222333000181", situacao_cadastral: "ATIVA",
          },
        }),
      ),
    );
    const rtl = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("parte-tipo-pj"));
    digitarDocumento(rtl, CNPJ_OK);
    rtl.fireEvent.click(rtl.screen.getByTestId("parte-lookup-usar-btn"));
    rtl.fireEvent.click(rtl.screen.getByTestId("comprador-salvar-btn"));
    expect(rtl.onCreate).toHaveBeenCalledWith({ empresa_id: "emp-3" });
  });

  it("🔴 certidões vencidas: avisa com a data e oferece 'Re-emitir e re-analisar' → reemitirCertidoes", async () => {
    mockLookup.mockReturnValue(
      resposta(
        lookupBase({
          certidoes: {
            max_dias: 30,
            data_referencia: "2026-10-01",
            itens: [
              {
                tipo: "cnd_federal", rotulo: "CND Federal", resultado_id: "r1",
                emitida_em: "2026-06-23", validade_ate: null, idade_dias: 100,
                stale_para_contrato: true, resultado: "negativa",
              },
            ],
            tipos_vencidos: ["cnd_federal"],
            alerta_vencidas: true,
            mensagem:
              "Há certidões com mais de 30 dias. Re-emita e re-analise antes de usar no contrato.",
          },
        }),
      ),
    );
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);

    expect(rtl.screen.getByTestId("parte-lookup-certidoes-vencidas").textContent).toContain(
      "Certidões de 23/06/2026 — vencidas para contrato",
    );
    // The re-emit offer only exists once the cadastro is being reused.
    expect(rtl.screen.queryByTestId("parte-lookup-reemitir-check")).toBeNull();
    rtl.fireEvent.click(rtl.screen.getByTestId("parte-lookup-usar-btn"));
    rtl.fireEvent.click(rtl.screen.getByTestId("parte-lookup-reemitir-check"));
    rtl.fireEvent.click(rtl.screen.getByTestId("comprador-salvar-btn"));
    expect(rtl.onCreate).toHaveBeenCalledWith({ cliente_id: "cli-9", reemitirCertidoes: true });
  });

  it("sem alerta de vencidas não há aviso nem opção de re-emitir", async () => {
    mockLookup.mockReturnValue(resposta(lookupBase()));
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);
    expect(rtl.screen.queryByTestId("parte-lookup-certidoes-vencidas")).toBeNull();
  });

  it("já faz parte do atendimento: não oferece 'Usar este cadastro'", async () => {
    mockLookup.mockReturnValue(resposta(lookupBase({ ja_no_atendimento: true })));
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);
    expect(rtl.screen.getByTestId("parte-lookup-ja-no-atendimento")).toBeTruthy();
    expect(rtl.screen.queryByTestId("parte-lookup-usar-btn")).toBeNull();
  });

  it("uma resposta de OUTRO documento (placeholder) não conta como match", async () => {
    mockLookup.mockReturnValue(resposta(lookupBase({ documento: "00000000000" })));
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);
    expect(rtl.screen.queryByTestId("parte-lookup-encontrado")).toBeNull();
  });

  it("erro do lookup é mostrado, nunca engolido", async () => {
    mockLookup.mockReturnValue({
      data: undefined, showSkeleton: false, isRefreshing: false, isError: true,
      error: new Error("[400] CPF inválido."),
    });
    const rtl = await abrir();
    digitarDocumento(rtl, CPF_OK);
    expect(rtl.screen.getByTestId("parte-lookup-erro").textContent).toBe("CPF inválido.");
  });
});

describe("AdicionarCompradorDialog — PF / PJ", () => {
  it("PF novo segue sendo { nome, celular } — shape inalterado", async () => {
    const rtl = await abrir();
    rtl.fireEvent.change(rtl.screen.getByTestId("comprador-nome-input"), {
      target: { value: "Ana Lima" },
    });
    rtl.fireEvent.change(rtl.screen.getByTestId("comprador-celular-input"), {
      target: { value: "11 99999-0000" },
    });
    rtl.fireEvent.click(rtl.screen.getByTestId("comprador-salvar-btn"));
    expect(rtl.onCreate).toHaveBeenCalledWith({ nome: "Ana Lima", celular: "11 99999-0000" });
  });

  it("🔴 PJ novo envia { cnpj (só dígitos), razao_social } — nunca nome", async () => {
    const rtl = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("parte-tipo-pj"));
    expect(rtl.screen.queryByTestId("comprador-nome-input")).toBeNull();
    expect((rtl.screen.getByTestId("comprador-salvar-btn") as HTMLButtonElement).disabled).toBe(true);

    digitarDocumento(rtl, "11.222.333/0001-80"); // wrong check digit
    expect(rtl.screen.getByTestId("comprador-cnpj-invalido").textContent).toBe("CNPJ inválido.");
    expect((rtl.screen.getByTestId("comprador-salvar-btn") as HTMLButtonElement).disabled).toBe(true);

    digitarDocumento(rtl, CNPJ_OK);
    rtl.fireEvent.change(rtl.screen.getByTestId("comprador-razao-social-input"), {
      target: { value: "NEON PARK LTDA" },
    });
    rtl.fireEvent.click(rtl.screen.getByTestId("comprador-salvar-btn"));
    expect(rtl.onCreate).toHaveBeenCalledWith({
      cnpj: "11222333000181",
      razao_social: "NEON PARK LTDA",
    });
    expect(rtl.onCreate.mock.calls[0][0]).not.toHaveProperty("nome");
  });

  it("vendedor tem o mesmo toggle PF/PJ; cônjuge não (empresa não pode ser cônjuge)", async () => {
    const vend = await abrir({ lado: "vendedor" });
    expect(vend.screen.getByTestId("parte-tipo-toggle")).toBeTruthy();
    vend.cleanup();
    const conj = await abrir({ lado: "conjuge" });
    expect(conj.screen.queryByTestId("parte-tipo-toggle")).toBeNull();
  });

  it("sem clienteId não consulta nada (hook não é usado)", async () => {
    const rtl = await abrir({ clienteId: undefined });
    digitarDocumento(rtl, CPF_OK);
    expect(mockLookup).not.toHaveBeenCalled();
  });
});
