/**
 * ParcelaFormDialog — the migration-192 payment shapes
 * (contrato-pagamentos-CONTRACT §1): a parcela split among several
 * favorecidos (value OR percentage, exclusive with the single favorecido),
 * and `valor_fgts` on the financing parcela. Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, children }: any) =>
      React.createElement(Ctx.Provider, { value: { onValueChange } }, React.createElement("div", { "data-value": value }, children)),
    SelectTrigger: ({ children, ...rest }: any) => React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement("button", { type: "button", "data-value": value, onClick: () => ctx.onValueChange?.(value) }, children);
    },
  };
});

import { ParcelaFormDialog, type ParcelaEditavel } from "./ParcelaFormDialog";

const FAVS = [
  { id: "f1", nome: "Vendedora Um" },
  { id: "f2", nome: "Vendedor Dois" },
];

function parcela(over: Partial<ParcelaEditavel> = {}): ParcelaEditavel {
  return {
    tipo: "sinal",
    valor: "60000.00",
    vencimento: null,
    evento: "na assinatura",
    forma_pagamento: "PIX",
    favorecido_id: "f1",
    confissao_divida: false,
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onSubmit = vi.fn();
  rtl.render(
    <ParcelaFormDialog
      open
      onOpenChange={vi.fn()}
      parcela={null}
      favorecidos={FAVS}
      permutaAtivos={[]}
      permitePagamentoDetalhado
      onSubmit={onSubmit}
      saving={false}
      error={null}
      {...over}
    />,
  );
  const escolher = (testId: string, value: string) =>
    rtl.fireEvent.click(
      (rtl.screen.getByTestId(testId).parentElement as HTMLElement).querySelector(
        `button[data-value="${value}"]`,
      ) as HTMLElement,
    );
  return { ...rtl, onSubmit, escolher };
}

describe("ParcelaFormDialog — divisão entre favorecidos", () => {
  it("🔴 switching a single-payee parcela to a split sends favorecido_id: null + the shares in ONE request", async () => {
    const { screen, fireEvent, onSubmit, escolher } = await render({ parcela: parcela() });
    fireEvent.click(screen.getByTestId("parc-dividir"));
    // The current payee seeds the first share.
    escolher("parc-divisao-favorecido-1", "f2");
    fireEvent.change(screen.getByTestId("parc-divisao-valor-0"), { target: { value: "30.000,00" } });
    fireEvent.change(screen.getByTestId("parc-divisao-valor-1"), { target: { value: "30.000,00" } });
    expect(screen.getByTestId("parc-divisao-conciliacao").textContent).toContain("o valor da parcela");
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.favorecido_id).toBeNull();
    expect(payload.favorecidos_divisao).toEqual([
      { favorecido_id: "f1", valor: "30000.00" },
      { favorecido_id: "f2", valor: "30000.00" },
    ]);
  });

  it("by percentage: a share that does not close yet is saveable, and says so", async () => {
    const { screen, fireEvent, onSubmit, escolher } = await render({ parcela: parcela() });
    fireEvent.click(screen.getByTestId("parc-dividir"));
    escolher("parc-divisao-modo", "percentual");
    escolher("parc-divisao-favorecido-1", "f2");
    fireEvent.change(screen.getByTestId("parc-divisao-valor-0"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("parc-divisao-valor-1"), { target: { value: "40" } });
    expect(screen.getByTestId("parc-divisao-conciliacao").textContent).toContain("devem somar 100%");
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));
    expect(onSubmit.mock.calls[0][0].favorecidos_divisao).toEqual([
      { favorecido_id: "f1", percentual: "50" },
      { favorecido_id: "f2", percentual: "40" },
    ]);
  });

  it("refuses what the server would: one share, a repeated favorecido", async () => {
    const { screen, fireEvent, escolher } = await render({ parcela: parcela() });
    fireEvent.click(screen.getByTestId("parc-dividir"));
    escolher("parc-divisao-favorecido-1", "f1");
    expect(screen.getByTestId("parc-divisao-erros").textContent).toContain("aparece duas vezes");
    expect((screen.getByTestId("negest-parcela-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 turning a stored split off sends favorecidos_divisao: [] with the single payee", async () => {
    const { screen, fireEvent, onSubmit } = await render({
      parcela: parcela({
        favorecido_id: null,
        favorecidos_divisao: [
          { id: "d1", favorecido_id: "f1", valor: "30000.00", percentual: null, ordem: 0 },
          { id: "d2", favorecido_id: "f2", valor: "30000.00", percentual: null, ordem: 1 },
        ],
      }),
    });
    expect((screen.getByTestId("parc-divisao-valor-0") as HTMLInputElement).value).toBe("30.000,00");
    fireEvent.click(screen.getByTestId("parc-dividir"));
    fireEvent.click(screen.getByText("Vendedor Dois"));
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.favorecidos_divisao).toEqual([]);
    expect(payload.favorecido_id).toBe("f2");
  });

  it("is not offered on a tipo that is not paid into an account, nor without the feature", async () => {
    const a = await render({ parcela: parcela({ tipo: "financiamento" }) });
    expect(a.screen.queryByTestId("parc-dividir")).toBeNull();
    a.cleanup();
    const b = await render({ parcela: parcela(), permitePagamentoDetalhado: false });
    expect(b.screen.queryByTestId("parc-dividir")).toBeNull();
  });
});

describe("ParcelaFormDialog — FGTS", () => {
  it("🔴 valor_fgts on the financing parcela must be below its value", async () => {
    const { screen, fireEvent, onSubmit } = await render({
      parcela: parcela({ tipo: "financiamento", valor: "400000.00", favorecido_id: null }),
    });
    fireEvent.change(screen.getByTestId("parc-valor-fgts"), { target: { value: "400.000,00" } });
    expect(screen.getByTestId("parc-valor-fgts-erro")).toBeTruthy();
    expect((screen.getByTestId("negest-parcela-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("parc-valor-fgts"), { target: { value: "100.000,00" } });
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));
    expect(onSubmit.mock.calls[0][0].valor_fgts).toBe("100000.00");
  });

  it("moving away from financiamento clears a stored valor_fgts in the same request", async () => {
    const { screen, fireEvent, onSubmit, escolher } = await render({
      parcela: parcela({ tipo: "financiamento", valor_fgts: "100000.00", favorecido_id: null }),
    });
    escolher("parc-tipo", "direta");
    fireEvent.click(screen.getByTestId("negest-parcela-salvar"));
    expect(onSubmit.mock.calls[0][0].valor_fgts).toBeNull();
  });

  it("the separate 'fgts' tipo is offered again", async () => {
    const { screen } = await render();
    const tipos = screen.getByTestId("parc-tipo").parentElement as HTMLElement;
    expect(tipos.querySelector('button[data-value="fgts"]')).toBeTruthy();
  });
});
