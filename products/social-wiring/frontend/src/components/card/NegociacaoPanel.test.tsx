/**
 * NegociacaoPanel — the split is shown, including what is NOT allocated.
 *
 * Not one centavo is computed here; the server allocates and this formats. So
 * the assertions worth having are about what the panel REFUSES to hide: an
 * agents' slice with no agents, a captação slice with no captador, and the
 * difference between "not enough information yet" and "zero".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import NegociacaoPanel from "./NegociacaoPanel";
import type { Negociacao } from "@/hooks/useNegociacao";

function negociacao(over: Partial<Negociacao> = {}): Negociacao {
  return {
    atendimento_id: "a1",
    imovel_codigo: null,
    valor_negociado: "500000.00",
    pct_comissao: "6",
    tem_parceria: false,
    pct_parceria: "50",
    pct_agencia: "50",
    pct_agentes: "45",
    pct_captador: "5",
    formas_pagamento: null,
    parcelas: null,
    financiamento: false,
    fgts: false,
    observacoes: null,
    created_at: null,
    updated_at: null,
    existe: true,
    // No lead behind this card — the origin affordance renders nothing.
    // `TestTheLeadOriginIsNeverTheDeal` below supplies one where it matters.
    lead_imovel: null,
    calculo: {
      calculavel: true,
      motivo: null,
      comissao_total: "30000.00",
      parceria: "0.00",
      nossa_parte: "30000.00",
      agencia: "15000.00",
      agentes_total: "13500.00",
      agentes: [],
      captador_total: "1500.00",
      captador: null,
    },
    ...over,
  };
}

async function render(over: Partial<Negociacao> | undefined = {}) {
  const rtl = await import("@testing-library/react");
  const onSave = vi.fn();
  const view = rtl.render(
    <NegociacaoPanel
      negociacao={over === undefined ? undefined : negociacao(over)}
      loading={false}
      saving={false}
      onSave={onSave}
    />,
  );
  return { ...rtl, ...view, onSave };
}

describe("NegociacaoPanel", () => {
  it("shows the split the server computed, formatted as BRL", async () => {
    const { screen } = await render();
    // Two matches, not one: with no parceria the comissão total and our part
    // are the same number — which is itself the correct behaviour.
    expect(screen.getAllByText(/R\$\s?30\.000,00/).length).toBe(2);
    expect(screen.getByText(/R\$\s?15\.000,00/)).toBeTruthy();
    expect(screen.getByText(/R\$\s?13\.500,00/)).toBeTruthy();
    expect(screen.getByText(/R\$\s?1\.500,00/)).toBeTruthy();
  });

  it("🔴 says the agents' slice has no destination rather than hiding it", async () => {
    // Folding it into the agency's share would silently pay the agency for
    // work it did not do, and nothing downstream would ever show it.
    const { screen } = await render({ calculo: negociacao().calculo });
    expect(screen.getByTestId("negociacao-sem-agentes")).toBeTruthy();
  });

  it("🔴 says the captação slice has no destination when there is no captador", async () => {
    const { screen } = await render();
    expect(screen.getByTestId("negociacao-sem-captador")).toBeTruthy();
  });

  it("names each agent when the card has membros", async () => {
    const { screen, queryByTestId } = await render({
      calculo: {
        ...negociacao().calculo,
        agentes: [
          { id: "1", nome: "Bia", valor: "6750.00" },
          { id: "2", nome: "Caio", valor: "6750.00" },
        ],
      },
    });
    expect(screen.getByText("Bia")).toBeTruthy();
    expect(screen.getByText("Caio")).toBeTruthy();
    expect(queryByTestId("negociacao-sem-agentes")).toBeNull();
  });

  it("🔴 distinguishes 'not enough information' from a zero split", async () => {
    // Zeroes would claim a split had been computed. Terms are routinely
    // drafted before a price is agreed.
    const { screen } = await render({
      valor_negociado: null,
      calculo: {
        calculavel: false,
        motivo: "informe valor negociado e % de comissão",
        comissao_total: null,
        parceria: null,
        nossa_parte: null,
        agencia: null,
        agentes_total: null,
        agentes: [],
        captador_total: null,
        captador: null,
      },
    });
    expect(screen.getByTestId("negociacao-nao-calculavel")).toBeTruthy();
    expect(screen.queryByText(/R\$\s?0,00/)).toBeNull();
  });

  it("shows the parceria line only when there is a parceria", async () => {
    const { queryByText } = await render({ tem_parceria: false });
    expect(queryByText("Parceria")).toBeNull();
  });

  it("🔴 refuses to save an in-house split that does not total 100%", async () => {
    const { screen, fireEvent, onSave } = await render();
    fireEvent.change(screen.getByLabelText("Agentes"), {
      target: { value: "40" },
    });
    expect(screen.getByTestId("negociacao-split-invalido")).toBeTruthy();
    fireEvent.click(screen.getByTestId("negociacao-salvar"));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("🔴 clears FGTS when financiamento is turned off", async () => {
    // The record must not keep claiming "will use FGTS" on a deal with no
    // financing — the UI enforces the flow the schema deliberately does not.
    const { screen, fireEvent, onSave } = await render({
      financiamento: true,
      fgts: true,
    });
    fireEvent.click(screen.getByLabelText(/vai usar financiamento/i));
    fireEvent.click(screen.getByTestId("negociacao-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ financiamento: false, fgts: false }),
    );
  });

  it("sends empty fields as null, never as an empty string", async () => {
    const { screen, fireEvent, onSave } = await render({ valor_negociado: null });
    fireEvent.click(screen.getByTestId("negociacao-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ valor_negociado: null }),
    );
  });

  it("🔴 survives numerics arriving as NUMBERS, not strings", async () => {
    // The live bug: PostgREST returns `numeric` as a JSON number, the type
    // said `string`, and `submit()`'s `.trim()` threw
    // `TypeError: e.trim is not a function` — losing whatever was typed.
    // Fixtures written against the declared type could never have caught it.
    const { screen, fireEvent, onSave } = await render({
      valor_negociado: 500000 as unknown as string,
      pct_comissao: 6 as unknown as string,
      pct_agencia: 50 as unknown as string,
      pct_agentes: 45 as unknown as string,
      pct_captador: 5 as unknown as string,
      pct_parceria: 50 as unknown as string,
    });
    fireEvent.click(screen.getByTestId("negociacao-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ valor_negociado: "500000", pct_comissao: "6" }),
    );
  });

  it("marks the defaults as the agency's, not as agreed terms", async () => {
    const { screen } = await render({ existe: false });
    expect(screen.getByText(/percentuais padrão da agência/i)).toBeTruthy();
  });
});

// ─── Dinheiro legível e divisão ao vivo (2026-08-25) ────────────────────────
describe("NegociacaoPanel — o dinheiro na tela", () => {
  it("mostra o valor formatado em vez do que o banco devolve", async () => {
    // 🔴 `NUMERIC(14,2)` devolve `850000.00`, que a tela exibia como
    // `850000.0` — ambíguo justamente no campo onde o erro custa mais caro.
    const { getByTestId } = await render({ valor_negociado: "850000.00" });

    expect((getByTestId("negociacao-valor") as HTMLInputElement).value).toBe(
      "850.000,00",
    );
  });

  it("percentuais não voltam como 50.0", async () => {
    const { container } = await render({
      valor_negociado: "850000.00",
      pct_comissao: "6.000",
      pct_agencia: "50.0",
    });

    expect(container.textContent).not.toContain("50.0");
    expect(container.textContent).not.toContain("6.000");
  });

  it("aceita o separador decimal brasileiro", async () => {
    const { getByTestId, fireEvent } = await render();
    const campo = getByTestId("negociacao-valor") as HTMLInputElement;

    fireEvent.focus(campo);
    fireEvent.change(campo, { target: { value: "850.000,50" } });
    fireEvent.blur(campo);

    expect(campo.value).toBe("850.000,50");
  });

  it("calcula a divisão enquanto a pessoa digita, antes de salvar", async () => {
    // Esta era a tela cuja única razão de existir ficava muda até salvar.
    const { getByTestId, container, fireEvent } = await render({
      valor_negociado: null,
      pct_comissao: null,
    });

    fireEvent.focus(getByTestId("negociacao-valor"));
    fireEvent.change(getByTestId("negociacao-valor"), {
      target: { value: "850000" },
    });
    fireEvent.change(getByTestId("negociacao-pct-comissao"), {
      target: { value: "6" },
    });

    expect(container.textContent).toContain("51.000,00");
    expect(getByTestId("negociacao-previa")).toBeTruthy();
  });

  it("diz que é prévia até salvar", async () => {
    const { getByTestId, queryByTestId, fireEvent } = await render({
      valor_negociado: "500000.00",
      pct_comissao: "6",
    });

    expect(queryByTestId("negociacao-previa")).toBeNull();

    fireEvent.change(getByTestId("negociacao-pct-comissao"), {
      target: { value: "7" },
    });

    expect(getByTestId("negociacao-previa")).toBeTruthy();
  });
});

/**
 * 🔴 THE DEAL IS NOT THE ANÚNCIO — and the shortcut does not blur that.
 *
 * `leads.codigo_imovel` is the listing the person ENQUIRED about;
 * `atendimento_negociacao.imovel_codigo` is the property being SOLD. The
 * owner: "not necessarily that ref is the one that will have the proposta."
 *
 * It CAN be the same property and often is, so the origin sits beside the
 * picker with a one-click "Usar este imóvel". The distinction preserved is WHO
 * ASSERTED IT: the system offering a shortcut is fine, the system deciding on
 * the operator's behalf is not. These tests hold both halves — that nothing is
 * prefilled, and that one click does fill it.
 *
 * The other half of the pair lives in the backend suite
 * (`test_negociacao.py::TestTheLeadOriginIsNeverTheDeal`).
 */
function origem(codigo = "ONE10337", over: Record<string, unknown> = {}) {
  return {
    codigo,
    titulo: "Apartamento",
    empreendimento: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: "Pinheiros",
    cidade: "São Paulo",
    uf: null,
    cep: null,
    foto_destaque: null,
    captacao: null,
    corretores: [],
    ativo_no_vista: true,
    fonte: "imoveis" as const,
    ...over,
  };
}

describe("NegociacaoPanel — o imóvel do negócio vs o anúncio de origem", () => {
  it("does NOT prefill the deal's imóvel from the lead's origin", async () => {
    const { screen } = await render({
      imovel_codigo: null,
      lead_imovel: origem(),
    });

    // The picker is degraded to the plain input here (no `renderImovelPicker`
    // in this test's render helper) — which is the same field, writing through
    // the same endpoint.
    const campo = screen.getByTestId("negociacao-imovel-input") as HTMLInputElement;
    expect(campo.value).toBe("");
  });

  it("shows the origin as labelled context beside it", async () => {
    const { screen } = await render({
      imovel_codigo: null,
      lead_imovel: origem(),
    });

    const bloco = screen.getByTestId("negociacao-imovel-origem");
    expect(bloco.textContent).toContain("Veio do anúncio");
    expect(bloco.textContent).toContain("ONE10337");
    expect(bloco.textContent).toContain("Pinheiros");
  });

  it("fills the picker on one click, and only then", async () => {
    const { screen, fireEvent } = await render({
      imovel_codigo: null,
      lead_imovel: origem(),
    });

    const campo = screen.getByTestId("negociacao-imovel-input") as HTMLInputElement;
    expect(campo.value).toBe("");

    fireEvent.click(screen.getByTestId("negociacao-imovel-origem-usar"));

    expect(
      (screen.getByTestId("negociacao-imovel-input") as HTMLInputElement).value,
    ).toBe("ONE10337");
  });

  it("saves the código the click put there", async () => {
    const { screen, fireEvent, onSave } = await render({
      imovel_codigo: null,
      lead_imovel: origem(),
    });

    fireEvent.click(screen.getByTestId("negociacao-imovel-origem-usar"));
    fireEvent.click(screen.getByTestId("negociacao-salvar"));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].imovel_codigo).toBe("ONE10337");
  });

  it("renders nothing there when the lead has no origin código", async () => {
    const { screen } = await render({ imovel_codigo: null, lead_imovel: null });

    // An affordance for a value that does not exist is a control that does
    // nothing.
    expect(screen.queryByTestId("negociacao-imovel-origem")).toBeNull();
  });

  it("says so instead of offering the button when they are the same imóvel", async () => {
    const { screen } = await render({
      imovel_codigo: "ONE10337",
      lead_imovel: origem(),
    });

    expect(screen.getByTestId("negociacao-imovel-origem-em-uso")).toBeTruthy();
    expect(screen.queryByTestId("negociacao-imovel-origem-usar")).toBeNull();
  });

  it("keeps a deal imóvel that differs from the origin, and still offers the swap", async () => {
    const { screen } = await render({
      imovel_codigo: "ONE9002",
      lead_imovel: origem(),
    });

    expect(
      (screen.getByTestId("negociacao-imovel-input") as HTMLInputElement).value,
    ).toBe("ONE9002");
    expect(screen.getByTestId("negociacao-imovel-origem-usar")).toBeTruthy();
  });

  it("marks an origin that has left the Vista catalog", async () => {
    const { screen } = await render({
      imovel_codigo: null,
      lead_imovel: origem("ONE4770", { ativo_no_vista: false, fonte: "registry" }),
    });

    expect(screen.getByTestId("negociacao-imovel-origem").textContent).toContain(
      "fora do catálogo",
    );
  });
});
