/**
 * TermosNegocioSection.test.tsx — the PUT-replaces-the-whole-object contract:
 * every save sends all sixteen keys, `marco = 'parcela'` blocks the save
 * until a parcela is picked, the permuta/confissão groups only show up when
 * the deal actually has a matching parcela, and a backend 400 surfaces via
 * toast.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// The real `Select` is a Radix popover jsdom does not model faithfully — same
// mock convention `ContratosPanel.test.tsx` / `Contatos.test.tsx` use.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", onClick: () => ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

const mockAtualizarTermos = vi.fn();
vi.mock("@/hooks/useNegociacaoEstruturada", async () => {
  const actual = await vi.importActual<
    typeof import("@/hooks/useNegociacaoEstruturada")
  >("@/hooks/useNegociacaoEstruturada");
  return {
    ...actual,
    useAtualizarTermos: () => ({ mutate: mockAtualizarTermos, isPending: false }),
  };
});

import TermosNegocioSection from "./TermosNegocioSection";
import type { NegociacaoEstruturada, NegociacaoParcela } from "@/types/negociacaoEstruturada";

function termosVazios() {
  return {
    posse_prazo_dias: null,
    posse_marco: null,
    posse_marco_parcela_id: null,
    posse_data: null,
    permuta_posse_prazo_dias: null,
    permuta_posse_marco: null,
    permuta_posse_marco_parcela_id: null,
    permuta_obrigacoes_entrega: null,
    itens_integrantes: null,
    itens_integrantes_ausente_confirmado: false,
    ad_corpus: null,
    obrigacoes_vendedor: null,
    onus_quitacao: null,
    onus_prazo_dias: null,
    confissao_juros_am: null,
    confissao_garantia: null,
    corretagem_contratantes: null,
    corretagem_num_parcelas: null,
  };
}

function parcela(over: Partial<NegociacaoParcela> = {}): NegociacaoParcela {
  return {
    id: "p1",
    tipo: "direta",
    valor: "1000.00",
    vencimento: null,
    evento: null,
    forma_pagamento: null,
    favorecido_id: null,
    confissao_divida: false,
    dispara_corretagem: false,
    permuta_ativo_ids: [],
    ordem: 1,
    origem: null,
    documento_id: null,
    extraido_em: null,
    confirmado_por: null,
    confirmado_em: null,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

function aggregate(over: Partial<NegociacaoEstruturada> = {}): NegociacaoEstruturada {
  return {
    atendimento_id: "at-1",
    valor_negociado: "850000.00",
    valor_negociado_origem: null,
    valor_negociado_documento_id: null,
    valor_negociado_em: null,
    valor_negociado_confirmado_por: null,
    valor_negociado_confirmado_em: null,
    a_distribuir: null,
    saldo_nao_alocado: "0.00",
    posse_data: null,
    posse_condicoes: null,
    permuta_ativo_id: null,
    parcelas: [],
    favorecidos: [],
    intermediarios: [],
    termos: termosVazios(),
    completude: { completo: true, faltando: [] },
    ...over,
  };
}

async function render(data: NegociacaoEstruturada) {
  const { render: rtlRender } = await import("@testing-library/react");
  return rtlRender(<TermosNegocioSection clienteId="cli-1" data={data} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("grupos condicionais", () => {
  it("posse, itens integrantes, ônus e corretagem SEMPRE aparecem", async () => {
    const { getByTestId } = await render(aggregate());
    expect(getByTestId("termos-posse")).toBeTruthy();
    expect(getByTestId("termos-itens")).toBeTruthy();
    expect(getByTestId("termos-onus")).toBeTruthy();
    expect(getByTestId("termos-corretagem")).toBeTruthy();
  });

  it("🔴 permuta reversa só aparece quando há parcela tipo permuta", async () => {
    const { queryByTestId } = await render(aggregate());
    expect(queryByTestId("termos-permuta")).toBeNull();
  });

  it("permuta reversa aparece quando uma parcela é do tipo permuta", async () => {
    const { getByTestId } = await render(
      aggregate({ parcelas: [parcela({ tipo: "permuta" })] }),
    );
    expect(getByTestId("termos-permuta")).toBeTruthy();
  });

  it("🔴 confissão só aparece quando alguma parcela tem confissao_divida", async () => {
    const { queryByTestId } = await render(aggregate());
    expect(queryByTestId("termos-confissao")).toBeNull();
  });

  it("confissão aparece quando uma parcela tem confissao_divida", async () => {
    const { getByTestId } = await render(
      aggregate({ parcelas: [parcela({ confissao_divida: true })] }),
    );
    expect(getByTestId("termos-confissao")).toBeTruthy();
  });

  it("🔴 'vendedores_boleto' (migração 192) é oferecido e pede o prazo", async () => {
    const { getByTestId, getByText } = await render(
      aggregate({ termos: { ...termosVazios(), onus_quitacao: "vendedores_boleto" } as any }),
    );
    expect(getByText("Vendedores quitam por boleto, em prazo")).toBeTruthy();
    expect(getByTestId("termos-onus-prazo-obrigatorio")).toBeTruthy();
  });

  it("🔴 'ja_quitado' pede a data do protocolo da baixa (migração 193) e a envia", async () => {
    const { getByTestId } = await render(
      aggregate({ termos: { ...termosVazios(), onus_quitacao: "ja_quitado" } as any }),
    );
    const { fireEvent } = await import("@testing-library/react");
    expect(getByTestId("termos-onus-baixa-protocolo-obrigatorio")).toBeTruthy();
    fireEvent.change(getByTestId("termos-onus-baixa-protocolo"), { target: { value: "2026-09-10" } });
    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[0][0].onus_baixa_protocolo_em).toBe("2026-09-10");
  });

  it("a nota de ônus explica quando ele se aplica", async () => {
    const { getByTestId } = await render(aggregate());
    expect(getByTestId("termos-onus").textContent).toContain("financiamento");
  });
});

describe("marco = 'parcela' exige uma parcela", () => {
  it("🔴 bloqueia salvar sem escolher a parcela", async () => {
    const { getByTestId, getByText } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("No pagamento de uma parcela"));

    expect(getByTestId("termos-posse-parcela-erro")).toBeTruthy();
    expect(getByTestId("negest-termos-salvar")).toHaveProperty("disabled", true);
    expect(mockAtualizarTermos).not.toHaveBeenCalled();
  });

  it("libera salvar assim que a parcela é escolhida", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      aggregate({ parcelas: [parcela({ id: "p1", valor: "1000.00" })] }),
    );
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("No pagamento de uma parcela"));
    // Formatted BRL, never the raw Decimal string ("1000.00").
    fireEvent.click(getByText("Parcela 01 — Direta — R$ 1.000,00"));

    expect(queryByTestId("termos-posse-parcela-erro")).toBeNull();
    expect(getByTestId("negest-termos-salvar")).toHaveProperty("disabled", false);
  });

  it("🔴 uma parcela sem evento NUNCA aparece pelo UUID — 'Parcela NN — tipo — R$ x', na ordem", async () => {
    const uuid = "6666c10e-0000-4000-8000-000000000001";
    const { getByText, queryByText, getAllByRole } = await render(
      aggregate({
        parcelas: [
          parcela({ id: uuid, tipo: "financiamento", valor: "400000.00", ordem: 2 }),
          parcela({ id: "p-sinal", tipo: "sinal", valor: "50000.00", ordem: 0, evento: "no ato" }),
          parcela({ id: "p-venc", tipo: "intermediaria", valor: "1000.00", ordem: 1, vencimento: "2026-12-10" }),
        ],
      }),
    );
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("No pagamento de uma parcela"));

    expect(queryByText(new RegExp(uuid))).toBeNull();
    expect(getByText("Parcela 01 — Sinal — no ato — R$ 50.000,00")).toBeTruthy();
    expect(getByText("Parcela 02 — Intermediária — 10/12/2026 — R$ 1.000,00")).toBeTruthy();
    expect(getByText("Parcela 03 — Financiamento — R$ 400.000,00")).toBeTruthy();
    expect(getAllByRole("button").some((b) => b.textContent?.includes(uuid))).toBe(false);
  });
});

describe("PUT — o corpo inteiro é sempre enviado", () => {
  it("🔴 salvar envia as 22 chaves de TERMOS_CAMPOS, mesmo em branco", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-termos-salvar"));

    expect(mockAtualizarTermos).toHaveBeenCalledTimes(1);
    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(Object.keys(payload).sort()).toEqual(
      [
        "posse_prazo_dias",
        "posse_marco",
        "posse_marco_parcela_id",
        "posse_data",
        "permuta_posse_prazo_dias",
        "permuta_posse_marco",
        "permuta_posse_marco_parcela_id",
        "permuta_obrigacoes_entrega",
        "itens_integrantes",
        "itens_integrantes_ausente_confirmado",
        "ad_corpus",
        "sinal_primeira_parcela",
        "obrigacoes_vendedor",
        "onus_quitacao",
        "onus_prazo_dias",
        "onus_baixa_protocolo_em",
        "confissao_juros_am",
        "confissao_garantia",
        "corretagem_contratantes",
        "corretagem_num_parcelas",
        "clausulas_extras",
        "posse_multa_diaria",
      ].sort(),
    );
  });

  it("sem condições especiais, clausulas_extras vai vazio e a multa vai nula", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("negest-termos-salvar"));
    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.clausulas_extras).toEqual({});
    expect(payload.posse_multa_diaria).toBeNull();
  });

  it("sinal como Parcela 01: ligado por padrão, desligar salva false pelo mesmo PUT", async () => {
    const { getByTestId, getByLabelText } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    const box = getByLabelText("Sinal sempre como Parcela 01");
    expect(box.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[0][0].sinal_primeira_parcela).toBe(true);

    fireEvent.click(box);
    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[1][0].sinal_primeira_parcela).toBe(false);
  });

  it("campos preenchidos chegam com os valores digitados", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.change(getByTestId("termos-posse-prazo"), { target: { value: "30" } });
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.posse_prazo_dias).toBe(30);
  });
});

describe("itens integrantes e ad corpus — respostas explícitas", () => {
  it("🔴 sem resposta, salvar NÃO responde por acidente (ad_corpus null, nenhum não confirmado)", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    expect(getByTestId("termos-itens-integrantes-resposta-pendente")).toBeTruthy();
    expect(getByTestId("termos-ad-corpus-resposta-pendente")).toBeTruthy();
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.ad_corpus).toBeNull();
    expect(payload.itens_integrantes).toBeNull();
    expect(payload.itens_integrantes_ausente_confirmado).toBe(false);
  });

  it("'Nenhum item integrante' envia a confirmação e nenhum texto", async () => {
    const { getByTestId, queryByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("termos-itens-integrantes-resposta-nenhum"));
    expect(queryByTestId("termos-itens-integrantes")).toBeNull();
    fireEvent.click(getByTestId("termos-ad-corpus-resposta-nao"));
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.itens_integrantes_ausente_confirmado).toBe(true);
    expect(payload.itens_integrantes).toBeNull();
    expect(payload.ad_corpus).toBe(false);
  });

  it("'Sim — listar' envia o texto e bloqueia o salvar enquanto vazio", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("termos-itens-integrantes-resposta-lista"));
    expect(getByTestId("negest-termos-salvar")).toHaveProperty("disabled", true);
    fireEvent.change(getByTestId("termos-itens-integrantes"), {
      target: { value: "Armários planejados" },
    });
    fireEvent.click(getByTestId("termos-ad-corpus-resposta-sim"));
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.itens_integrantes).toBe("Armários planejados");
    expect(payload.itens_integrantes_ausente_confirmado).toBe(false);
    expect(payload.ad_corpus).toBe(true);
  });

  it("uma resposta salva é relida como tal (nenhum confirmado + ad corpus não)", async () => {
    const { getByTestId, queryByTestId } = await render(
      aggregate({
        termos: { ...termosVazios(), itens_integrantes_ausente_confirmado: true, ad_corpus: false },
      }),
    );
    expect(
      getByTestId("termos-itens-integrantes-resposta-nenhum").getAttribute("aria-checked"),
    ).toBe("true");
    expect(getByTestId("termos-ad-corpus-resposta-nao").getAttribute("aria-checked")).toBe("true");
    expect(queryByTestId("termos-itens-integrantes-resposta-pendente")).toBeNull();
    expect(queryByTestId("termos-ad-corpus-resposta-pendente")).toBeNull();
  });

  it("os controles carregam os ids que o 'Resolver' mira", async () => {
    const { container } = await render(aggregate());
    expect(container.querySelector("#termos-itens-integrantes-resposta")).not.toBeNull();
    expect(container.querySelector("#termos-ad-corpus-resposta")).not.toBeNull();
  });
});

describe("posse concomitante (prazo 0) e em data fixa — migração 201", () => {
  it("🔴 prazo 0 é uma resposta: é enviado como 0, nunca como null", async () => {
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.change(getByTestId("termos-posse-prazo"), { target: { value: "0" } });
    expect(getByTestId("termos-posse-prazo-dica").textContent).toContain("concomitante");
    fireEvent.click(getByTestId("negest-termos-salvar"));

    expect(mockAtualizarTermos.mock.calls[0][0].posse_prazo_dias).toBe(0);
  });

  it("o prazo 0 salvo é relido como 0 (não como campo vazio)", async () => {
    const { getByTestId } = await render(
      aggregate({ termos: { ...termosVazios(), posse_prazo_dias: 0, posse_marco: "assinatura" } }),
    );
    expect((getByTestId("termos-posse-prazo") as HTMLInputElement).value).toBe("0");
  });

  it("o marco 'Em data fixa' troca o prazo pela data e a envia sem prazo", async () => {
    const { getByTestId, queryByTestId, getByText } = await render(
      aggregate({ termos: { ...termosVazios(), posse_prazo_dias: 30 } }),
    );
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("Em data fixa"));
    expect(queryByTestId("termos-posse-prazo")).toBeNull();
    fireEvent.change(getByTestId("termos-posse-data"), { target: { value: "2026-11-30" } });
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.posse_marco).toBe("data_fixa");
    expect(payload.posse_data).toBe("2026-11-30");
    expect(payload.posse_prazo_dias).toBeNull();
  });

  it("🔴 data fixa sem a data bloqueia o salvar", async () => {
    const { getByTestId, getByText } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("Em data fixa"));
    expect(getByTestId("termos-posse-data-erro")).toBeTruthy();
    expect(getByTestId("negest-termos-salvar")).toHaveProperty("disabled", true);
  });

  it("outro marco nunca envia a data de uma escolha anterior", async () => {
    const { getByTestId, getByText } = await render(
      aggregate({
        termos: { ...termosVazios(), posse_marco: "data_fixa", posse_data: "2026-11-30" },
      }),
    );
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByText("Na assinatura"));
    fireEvent.change(getByTestId("termos-posse-prazo"), { target: { value: "5" } });
    fireEvent.click(getByTestId("negest-termos-salvar"));

    const payload = mockAtualizarTermos.mock.calls[0][0];
    expect(payload.posse_marco).toBe("assinatura");
    expect(payload.posse_data).toBeNull();
    expect(payload.posse_prazo_dias).toBe(5);
  });

  it("as seções de posse carregam os ids que o 'Resolver' mira (imóvel e permuta)", async () => {
    const { container } = await render(
      aggregate({ parcelas: [parcela({ tipo: "permuta" })] }),
    );
    expect(container.querySelector("#termos-posse-controles")).not.toBeNull();
    expect(container.querySelector("#termos-permuta-posse-controles")).not.toBeNull();
  });
});

describe("erro do backend chega por toast", () => {
  it("🔴 uma mensagem pt-BR do backend aparece via toast.error", async () => {
    mockAtualizarTermos.mockImplementation(
      (_payload: unknown, opts?: { onError?: (e: unknown) => void }) => {
        opts?.onError?.({
          message: "[400] o prazo de posse não pode ser negativo",
        });
      },
    );
    const { getByTestId } = await render(aggregate());
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("negest-termos-salvar"));

    const { toast } = await import("sonner");
    const call = (toast.error as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0];
    expect(String(call[0])).toContain("prazo de posse não pode ser negativo");
  });
});

const OPCOES = {
  clausulas: [
    { chave: "objeto", rotulo: "Do objeto do contrato", condicional: false },
    { chave: "posse", rotulo: "Da posse sobre", condicional: false },
    { chave: "confissao", rotulo: "Da confissão de dívida", condicional: true },
  ],
  posse_multa_diaria_padrao: "500.00",
};

describe("Condições especiais por cláusula (migration 207)", () => {
  it("lista as cláusulas que o gerador devolve, e some sem termos_opcoes", async () => {
    const { getByTestId, queryByTestId, unmount } = await render(aggregate({ termos_opcoes: OPCOES }));
    expect(getByTestId("termos-clausulas-extras")).toBeTruthy();
    expect(getByTestId("clausula-extra-objeto")).toBeTruthy();
    expect(getByTestId("clausula-extra-confissao")).toBeTruthy();
    unmount();
    const outro = await render(aggregate());
    expect(outro.queryByTestId("termos-clausulas-extras")).toBeNull();
    expect(queryByTestId("clausula-extra-objeto")).toBeNull();
  });

  it("digitar + ligar 'substituir' salva pelo mesmo PUT, só as cláusulas com texto", async () => {
    const { getByTestId } = await render(aggregate({ termos_opcoes: OPCOES }));
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("clausula-extra-posse-toggle"));
    fireEvent.change(getByTestId("clausula-extra-posse-texto"), {
      target: { value: "  Prazo prorrogável uma vez.  " },
    });
    // Em branco (só espaços) não é uma entrada.
    fireEvent.click(getByTestId("clausula-extra-objeto-toggle"));
    fireEvent.change(getByTestId("clausula-extra-objeto-texto"), { target: { value: "   " } });
    expect(getByTestId("clausula-extra-posse-badge").textContent).toBe("Com texto");

    fireEvent.click(getByTestId("clausula-extra-posse-substituir"));
    expect(getByTestId("clausula-extra-posse-badge").textContent).toBe("Substitui a padrão");

    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[0][0].clausulas_extras).toEqual({
      posse: { texto: "Prazo prorrogável uma vez.", modo: "substituir" },
    });
  });

  it("entradas já salvas voltam preenchidas e abertas, e seguem no PUT", async () => {
    const { getByTestId } = await render(
      aggregate({
        termos_opcoes: OPCOES,
        termos: {
          ...termosVazios(),
          clausulas_extras: { objeto: { texto: "Parágrafo extra do objeto.", modo: "acrescentar" } },
        },
      }),
    );
    const { fireEvent } = await import("@testing-library/react");
    expect((getByTestId("clausula-extra-objeto-texto") as HTMLTextAreaElement).value).toBe(
      "Parágrafo extra do objeto.",
    );
    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[0][0].clausulas_extras).toEqual({
      objeto: { texto: "Parágrafo extra do objeto.", modo: "acrescentar" },
    });
  });
});

describe("Multa diária da posse — override por negócio (migration 207)", () => {
  it("mostra o padrão da imobiliária como placeholder e vai nulo em branco", async () => {
    const { getByTestId } = await render(aggregate({ termos_opcoes: OPCOES }));
    const input = getByTestId("termos-posse-multa") as HTMLInputElement;
    expect(input.placeholder).toContain("500,00");
    expect(input.value).toBe("");
  });

  it("valor digitado em pt-BR chega como decimal; vem do servidor com vírgula", async () => {
    const { getByTestId } = await render(aggregate({ termos_opcoes: OPCOES }));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(getByTestId("termos-posse-multa"), { target: { value: "1.250,50" } });
    fireEvent.click(getByTestId("negest-termos-salvar"));
    expect(mockAtualizarTermos.mock.calls[0][0].posse_multa_diaria).toBe("1250.50");
  });

  it("carrega o override salvo", async () => {
    const { getByTestId } = await render(
      aggregate({ termos: { ...termosVazios(), posse_multa_diaria: "150.50" } }),
    );
    expect((getByTestId("termos-posse-multa") as HTMLInputElement).value).toBe("150,50");
  });

  it("zero ou lixo bloqueia o salvar com a explicação", async () => {
    const { getByTestId, queryByTestId } = await render(aggregate({ termos_opcoes: OPCOES }));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(getByTestId("termos-posse-multa"), { target: { value: "0" } });
    expect(getByTestId("termos-posse-multa-erro")).toBeTruthy();
    expect((getByTestId("negest-termos-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(getByTestId("termos-posse-multa"), { target: { value: "abc" } });
    expect(getByTestId("termos-posse-multa-erro")).toBeTruthy();
    fireEvent.change(getByTestId("termos-posse-multa"), { target: { value: "" } });
    expect(queryByTestId("termos-posse-multa-erro")).toBeNull();
  });
});
