/**
 * PerderAtendimentoDialog.test.tsx — the reason gate before a deal is marked
 * lost. Radix Select needs pointer-capture APIs jsdom lacks, so the select
 * primitive is swapped for a native <select> (the dialog's logic, not Radix,
 * is under test).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/ui/select", () => ({
  Select: ({ value, onValueChange, children }: any) => (
    <select data-testid="perder-categoria" value={value} onChange={(e) => onValueChange(e.target.value)}>
      <option value="" />
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ value, children }: any) => <option value={value}>{children}</option>,
}));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { PerderAtendimentoDialog } from "./PerderAtendimentoDialog";

async function setup(props: Partial<React.ComponentProps<typeof PerderAtendimentoDialog>> = {}) {
  const rtl = await import("@testing-library/react");
  const onConfirm = vi.fn();
  rtl.render(
    <PerderAtendimentoDialog open pending={false} onOpenChange={vi.fn()} onConfirm={onConfirm} {...props} />,
  );
  return { ...rtl, onConfirm };
}

describe("PerderAtendimentoDialog", () => {
  it("keeps confirm disabled until a reason is chosen", async () => {
    const { screen } = await setup();
    expect((screen.getByTestId("perder-atendimento-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("confirms with just the category for a non-'outro' reason", async () => {
    const { screen, fireEvent, onConfirm } = await setup();
    fireEvent.change(screen.getByTestId("perder-categoria"), { target: { value: "preco_acima_mercado" } });
    fireEvent.click(screen.getByTestId("perder-atendimento-confirm"));
    expect(onConfirm).toHaveBeenCalledWith({ categoria: "preco_acima_mercado", motivo: undefined });
  });

  it("requires the note for 'outro'", async () => {
    const { screen, fireEvent, onConfirm } = await setup();
    fireEvent.change(screen.getByTestId("perder-categoria"), { target: { value: "outro" } });
    const btn = screen.getByTestId("perder-atendimento-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("perder-observacao"), { target: { value: "  mudou de cidade " } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledWith({ categoria: "outro", motivo: "mudou de cidade" });
  });

  it("shows the pending state and blocks confirm", async () => {
    const { screen } = await setup({ pending: true });
    const btn = screen.getByTestId("perder-atendimento-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain("Salvando");
  });
});
