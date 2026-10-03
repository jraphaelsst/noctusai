/**
 * TestemunhasSelectContainer — a contract with NO witnesses yet (owner bug,
 * 2026-10-03): the count selector read "2" but no slot rendered until the
 * count was changed and changed back. The default count's slots must render,
 * and picking a witness in each must save the pair. Synthetic data only.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange: disabled ? undefined : onValueChange } },
        React.createElement("div", { "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children, disabled }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", disabled, onClick: () => !disabled && ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

const mockDefinir = vi.fn();
const mockSelecao = vi.fn();
vi.mock("@/hooks/useContratoTestemunhas", () => ({
  useContratoTestemunhas: () => mockSelecao(),
  useDefinirContratoTestemunhas: () => ({ mutate: mockDefinir, isPending: false }),
}));

function testemunha(id: string, nome: string) {
  return {
    id, nome, cpf: "111.222.333-44", rg: null, celular: null, email: null,
    cpf_pendente: false, contratos_em_uso: 0, created_at: null, updated_at: null,
  };
}

vi.mock("@/hooks/useTestemunhas", () => ({
  useTestemunhas: () => ({
    data: { items: [testemunha("t1", "Maria Souza"), testemunha("t2", "João Lima")] },
  }),
}));

import { TestemunhasSelectContainer } from "./TestemunhasSelectContainer";

beforeEach(() => {
  vi.clearAllMocks();
  mockSelecao.mockReturnValue({ data: { items: [] } });
});

describe("contrato sem testemunhas", () => {
  it("🔴 a quantidade padrão (2) renderiza 2 slots e preenchê-los salva o par", async () => {
    const { render, fireEvent, within, screen } = await import("@testing-library/react");
    render(<TestemunhasSelectContainer clienteId="cli-1" contratoId="ct-1" aberto />);

    const quantidade = screen.getByTestId("testemunhas-quantidade").parentElement as HTMLElement;
    expect(quantidade.getAttribute("data-value")).toBe("2");
    const slot0 = screen.getByTestId("testemunhas-slot-0").parentElement as HTMLElement;
    const slot1 = screen.getByTestId("testemunhas-slot-1").parentElement as HTMLElement;

    fireEvent.click(within(slot0).getByText("Maria Souza"));
    expect(mockDefinir).not.toHaveBeenCalled(); // slot 1 still empty
    fireEvent.click(within(slot1).getByText("João Lima"));

    expect(mockDefinir).toHaveBeenCalledTimes(1);
    expect(mockDefinir.mock.calls[0][0]).toEqual(["t1", "t2"]);
  });

  it("uma seleção salva é relida nos seus slots", async () => {
    mockSelecao.mockReturnValue({
      data: { items: [{ testemunha: testemunha("t2", "João Lima") }, { testemunha: testemunha("t1", "Maria Souza") }, { testemunha: testemunha("t3", "Ana Reis") }] },
    });
    const { render, screen } = await import("@testing-library/react");
    render(<TestemunhasSelectContainer clienteId="cli-1" contratoId="ct-1" aberto />);
    const quantidade = screen.getByTestId("testemunhas-quantidade").parentElement as HTMLElement;
    expect(quantidade.getAttribute("data-value")).toBe("3");
    expect((screen.getByTestId("testemunhas-slot-0").parentElement as HTMLElement).getAttribute("data-value")).toBe("t2");
  });
});
