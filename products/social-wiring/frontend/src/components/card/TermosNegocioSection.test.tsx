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
    // 🔴 Formatted BRL, not the raw Decimal string — see
    // `ParcelaMarcoSelect`'s `formatBRL` fix (the picker used to print
    // "p1 — 1000.00" instead of "R$ 1.000,00", the same raw-float class the
    // parcelas table three inches above never had).
    fireEvent.click(getByText("p1 — R$ 1.000,00"));

    expect(queryByTestId("termos-posse-parcela-erro")).toBeNull();
    expect(getByTestId("negest-termos-salvar")).toHaveProperty("disabled", false);
  });
});

describe("PUT — o corpo inteiro é sempre enviado", () => {
  it("🔴 salvar envia as 17 chaves de TERMOS_CAMPOS, mesmo em branco", async () => {
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
        "permuta_posse_prazo_dias",
        "permuta_posse_marco",
        "permuta_posse_marco_parcela_id",
        "permuta_obrigacoes_entrega",
        "itens_integrantes",
        "itens_integrantes_ausente_confirmado",
        "ad_corpus",
        "obrigacoes_vendedor",
        "onus_quitacao",
        "onus_prazo_dias",
        "confissao_juros_am",
        "confissao_garantia",
        "corretagem_contratantes",
        "corretagem_num_parcelas",
      ].sort(),
    );
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
