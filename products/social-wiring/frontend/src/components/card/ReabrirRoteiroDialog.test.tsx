/** "Reabrir · confirmação" (state matrix): an alert dialog that warns the PDF goes stale. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ReabrirRoteiroDialog } from "./ReabrirRoteiroDialog";

afterEach(cleanup);

describe("ReabrirRoteiroDialog", () => {
  it("is an alertdialog warning that a downloaded PDF is out of date", () => {
    render(<ReabrirRoteiroDialog open onCancel={vi.fn()} onConfirm={vi.fn()} />);
    const d = screen.getByRole("alertdialog");
    expect(d.textContent).toContain("Reabrir este roteiro como rascunho?");
    expect(d.textContent).toContain("A lista volta a aceitar imóveis novos e remoções.");
    expect(d.textContent).toContain("Quem gerou o roteiro será avisado.");
    expect(d.textContent).toContain("O PDF já baixado fica desatualizado.");
  });

  it("names who generated it, falling back to the generic text when the name is null", () => {
    const a = render(<ReabrirRoteiroDialog open geradoPorNome="Cindy Kumagai" onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByRole("alertdialog").textContent).toContain("Cindy Kumagai, que gerou o roteiro, será avisado(a).");
    a.unmount();
    render(<ReabrirRoteiroDialog open geradoPorNome={null} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByRole("alertdialog").textContent).toContain("Quem gerou o roteiro será avisado.");
  });

  it("'Manter gerado' cancels, the primary action confirms", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<ReabrirRoteiroDialog open onCancel={onCancel} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText("Manter gerado"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("roteiro-confirmar-reabrir-ok"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("renders nothing while closed", () => {
    render(<ReabrirRoteiroDialog open={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
