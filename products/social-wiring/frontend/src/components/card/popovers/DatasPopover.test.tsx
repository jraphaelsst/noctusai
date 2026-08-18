/**
 * DatasPopover.test.tsx — screenshot 06: início/entrega/recorrência/lembrete
 * assembled into one PATCH body, plus the verbatim reminder note and
 * Salvar/Remover actions.
 *
 * `ui/select` stubbed exactly like the house convention
 * (`pages/leads/Configuracao.test.tsx` et al.) — Radix's real `Select`
 * needs pointer-capture APIs jsdom doesn't implement — extended with a tiny
 * context (mirrors `ClientesBoard.test.tsx`'s Tabs stub) so `onValueChange`
 * actually fires from a click.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const SelectCtx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  const Select = ({ onValueChange, children }: any) =>
    React.createElement(SelectCtx.Provider, { value: { onValueChange } }, children);
  const SelectTrigger = ({ children }: any) => React.createElement("div", null, children);
  const SelectValue = () => null;
  const SelectContent = ({ children }: any) => React.createElement("div", null, children);
  const SelectItem = ({ value, children, ...props }: any) => {
    const ctx = React.useContext(SelectCtx);
    return React.createElement(
      "button",
      { type: "button", onClick: () => ctx.onValueChange?.(value), ...props },
      children,
    );
  };
  return { Select, SelectTrigger, SelectValue, SelectContent, SelectItem };
});

import { DatasPopover } from "./DatasPopover";

async function render(props: Partial<React.ComponentProps<typeof DatasPopover>> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const merged: React.ComponentProps<typeof DatasPopover> = {
    open: true,
    onOpenChange: vi.fn(),
    datas: null,
    onSave: vi.fn(),
    onRemove: vi.fn(),
    ...props,
  };
  return rtl.render(React.createElement(DatasPopover, merged));
}

describe("DatasPopover — the verbatim reminder note (screenshot 06)", () => {
  it("shows the exact pt-BR copy", async () => {
    const { getByText } = await render();
    expect(
      getByText("Lembretes serão enviados a todos os membros e seguidores deste cartão."),
    ).toBeTruthy();
  });
});

describe("DatasPopover — Salvar assembles the PATCH body", () => {
  it("sends data_entrega + lembrete when Data de entrega is checked", async () => {
    const onSave = vi.fn();
    const { getByTestId } = await render({ onSave });
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("datas-entrega-checkbox"));
    fireEvent.change(getByTestId("datas-entrega-data-input"), { target: { value: "2026-08-20" } });
    fireEvent.change(getByTestId("datas-entrega-hora-input"), { target: { value: "15:49" } });
    fireEvent.click(getByTestId("datas-lembrete-option-1440")); // "1 dia antes"

    fireEvent.click(getByTestId("datas-salvar"));

    expect(onSave).toHaveBeenCalledOnce();
    const body = onSave.mock.calls[0][0];
    expect(body.data_entrega).toContain("2026-08-20");
    expect(body.data_inicio).toBeNull();
    expect(body.lembrete_minutos_antes).toBe(1440);
  });

  it("sends null data_entrega when the checkbox is left unchecked", async () => {
    const onSave = vi.fn();
    const { getByTestId } = await render({ onSave });
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("datas-salvar"));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ data_entrega: null, data_inicio: null }),
    );
  });

  it("maps the 'Nunca' recorrência default to null, never the literal string", async () => {
    const onSave = vi.fn();
    const { getByTestId } = await render({ onSave });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("datas-salvar"));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ recorrencia: null }));
  });
});

describe("DatasPopover — Remover", () => {
  it("fires onRemove", async () => {
    const onRemove = vi.fn();
    const { getByTestId } = await render({ onRemove });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("datas-remover"));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
