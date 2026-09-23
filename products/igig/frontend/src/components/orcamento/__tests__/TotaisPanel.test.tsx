/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { TotaisPanel, nivelDaMargem } from "../TotaisPanel";
import type { Totais } from "@/types/crm";

afterEach(cleanup);

const TOTAIS: Totais = {
  subtotal_criacao: 2400,
  subtotal_gestao: 1000,
  desconto: 200,
  total_mensal: 3200,
  custo_estimado: 1600,
  margem_estimada: 50,
  horas_estimadas: 32.5,
};

// Intl pt-BR uses a NBSP between "R$" and the number.
const norm = (s: string | null | undefined) => (s ?? "").replace(/\s/g, " ");

describe("TotaisPanel — shows the SERVER's /calcular numbers", () => {
  it("renders subtotals, discount, total, cost/hours and the margin badge", () => {
    render(<TotaisPanel totais={TOTAIS} />);
    expect(norm(screen.getByTestId("total-criacao").textContent)).toBe("R$ 2.400,00");
    expect(norm(screen.getByTestId("total-gestao").textContent)).toBe("R$ 1.000,00");
    expect(norm(screen.getByTestId("total-desconto").textContent)).toBe("− R$ 200,00");
    expect(norm(screen.getByTestId("total-mensal").textContent)).toBe("R$ 3.200,00");
    expect(norm(screen.getByTestId("total-custo").textContent)).toContain("R$ 1.600,00");
    expect(norm(screen.getByTestId("total-custo").textContent)).toContain("32,5 h/mês");
    const badge = screen.getByTestId("margem-badge");
    expect(badge).toHaveAttribute("data-nivel", "boa");
    expect(badge.textContent).toContain("50%");
  });

  it("omits the discount line when there is none", () => {
    render(<TotaisPanel totais={{ ...TOTAIS, desconto: 0 }} />);
    expect(screen.queryByTestId("total-desconto")).toBeNull();
  });

  it("flags a thin margin loudly", () => {
    render(<TotaisPanel totais={{ ...TOTAIS, margem_estimada: 12.34 }} />);
    const badge = screen.getByTestId("margem-badge");
    expect(badge).toHaveAttribute("data-nivel", "baixa");
    expect(badge.textContent).toContain("Margem baixa");
    expect(badge.textContent).toContain("12,3%");
  });

  it("empty and error states never show stale zeros", () => {
    const { rerender } = render(<TotaisPanel totais={null} vazio />);
    expect(screen.getByText("Adicione itens para calcular o orçamento.")).toBeInTheDocument();
    expect(screen.queryByTestId("total-mensal")).toBeNull();
    rerender(<TotaisPanel totais={TOTAIS} error="Sem custo/hora cadastrado." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Sem custo/hora cadastrado.");
    expect(screen.queryByTestId("total-mensal")).toBeNull();
  });

  it("margin levels: <20 baixa · 20–40 média · ≥40 boa", () => {
    expect(nivelDaMargem(19.9)).toBe("baixa");
    expect(nivelDaMargem(20)).toBe("media");
    expect(nivelDaMargem(39.9)).toBe("media");
    expect(nivelDaMargem(40)).toBe("boa");
  });
});
