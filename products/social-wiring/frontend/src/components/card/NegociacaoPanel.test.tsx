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
