/**
 * ExcluirClienteConfirmDialog.test.tsx — the confirm gate before a cliente
 * is hard-deleted (owner directive, 2026-09-24). Names the client and
 * states the action is permanent — both asserted here, since that is the
 * whole point of the brief's requirement.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ExcluirClienteConfirmDialog } from "./ExcluirClienteConfirmDialog";

describe("ExcluirClienteConfirmDialog", () => {
  it("renders nothing when closed", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ExcluirClienteConfirmDialog
        open={false}
        pending={false}
        nome="Ana"
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("excluir-cliente-confirm")).toBeNull();
  });

  it("names the client and states the action is permanent", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ExcluirClienteConfirmDialog
        open
        pending={false}
        nome="Ana Beatriz"
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Excluir cliente?")).toBeTruthy();
    expect(screen.getByText("Ana Beatriz")).toBeTruthy();
    expect(screen.getByText(/não pode ser desfeita/)).toBeTruthy();
  });

  it("fires onConfirm only when the destructive action is clicked, never on Cancelar", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onConfirm = vi.fn();
    render(
      <ExcluirClienteConfirmDialog
        open
        pending={false}
        nome="Ana"
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("excluir-cliente-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables both actions and shows the in-flight label while pending", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ExcluirClienteConfirmDialog
        open
        pending
        nome="Ana"
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByTestId("excluir-cliente-confirm").textContent).toBe("Excluindo…");
    expect((screen.getByText("Cancelar") as HTMLButtonElement).disabled).toBe(true);
  });
});
