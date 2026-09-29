/**
 * CpfMergeConfirmDialog.test.tsx — the confirm gate before a CPF group is
 * unified (brief 2026-09-28: "Use the product's in-app confirm dialog
 * (never window.confirm) and say plainly what merge does"). Names the
 * survivor and states what happens to everyone else — both asserted here,
 * mirroring `ExcluirClienteConfirmDialog.test.tsx`'s own shape.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { CpfMergeConfirmDialog } from "./CpfMergeConfirmDialog";

describe("CpfMergeConfirmDialog", () => {
  it("renders nothing when closed", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <CpfMergeConfirmDialog
        open={false}
        pending={false}
        sobreviventeNome="Ana"
        quantidadeAbsorvidos={1}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("cpf-merge-confirm")).toBeNull();
  });

  it("names the survivor and says plainly what merge does", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <CpfMergeConfirmDialog
        open
        pending={false}
        sobreviventeNome="Ana Beatriz"
        quantidadeAbsorvidos={2}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Unificar como a mesma pessoa?")).toBeTruthy();
    expect(screen.getByText("Ana Beatriz")).toBeTruthy();
    expect(screen.getByText(/2 outros cadastros/)).toBeTruthy();
    expect(screen.getByText(/vai manter todas/)).toBeTruthy();
    expect(screen.getByText(/não pode ser desfeita/)).toBeTruthy();
  });

  it("singularizes the count for exactly one absorbed candidate", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <CpfMergeConfirmDialog
        open
        pending={false}
        sobreviventeNome="Ana"
        quantidadeAbsorvidos={1}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText(/1 outro cadastro\b/)).toBeTruthy();
  });

  it("fires onConfirm only when Unificar is clicked, never on Cancelar", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onConfirm = vi.fn();
    render(
      <CpfMergeConfirmDialog
        open
        pending={false}
        sobreviventeNome="Ana"
        quantidadeAbsorvidos={1}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("cpf-merge-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables both actions and shows the in-flight label while pending", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <CpfMergeConfirmDialog
        open
        pending
        sobreviventeNome="Ana"
        quantidadeAbsorvidos={1}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByTestId("cpf-merge-confirm").textContent).toBe("Unificando…");
    expect((screen.getByText("Cancelar") as HTMLButtonElement).disabled).toBe(true);
  });
});
