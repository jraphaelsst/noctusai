/**
 * ArquivarAtendimentoConfirmDialog.test.tsx — the confirm gate before a
 * funil card is archived. Mirrors the plain render/fireEvent shape every
 * other alert-dialog test in this product uses (no data-fetching here).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ArquivarAtendimentoConfirmDialog } from "./ArquivarAtendimentoConfirmDialog";

describe("ArquivarAtendimentoConfirmDialog", () => {
  it("renders nothing when closed", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ArquivarAtendimentoConfirmDialog
        open={false}
        pending={false}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("arquivar-atendimento-confirm")).toBeNull();
  });

  it("asks for confirmation when open, in pt-BR", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ArquivarAtendimentoConfirmDialog
        open
        pending={false}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Arquivar este card no funil?")).toBeTruthy();
    expect(screen.getByTestId("arquivar-atendimento-confirm").textContent).toBe("Arquivar");
  });

  it("fires onConfirm only when the destructive action is clicked, never on Cancelar", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onConfirm = vi.fn();
    render(
      <ArquivarAtendimentoConfirmDialog
        open
        pending={false}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("arquivar-atendimento-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables both actions and shows the in-flight label while pending", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ArquivarAtendimentoConfirmDialog
        open
        pending
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByTestId("arquivar-atendimento-confirm").textContent).toBe("Arquivando…");
    expect((screen.getByText("Cancelar") as HTMLButtonElement).disabled).toBe(true);
  });
});
