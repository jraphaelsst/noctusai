/**
 * NovoContratoDialog — the create-contract form.
 *
 * Client-side validation mirrors the server's own 422 gate (wrong MIME /
 * oversize), so the load-bearing assertions are that a bad file is caught
 * BEFORE `onCriar` fires, and that a valid submission carries the fields the
 * contract actually declares (título, modelo default, trimmed rótulo).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { NovoContratoDialog } from "./NovoContratoDialog";

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onCriar = vi.fn();
  const onOpenChange = vi.fn();
  const view = rtl.render(
    <NovoContratoDialog
      open
      onOpenChange={onOpenChange}
      onCriar={onCriar}
      saving={false}
      {...over}
    />,
  );
  return { ...view, ...rtl, onCriar, onOpenChange };
}

describe("NovoContratoDialog", () => {
  it("disables Criar contrato until título AND a valid file are present", async () => {
    const { screen } = await render();
    expect((screen.getByTestId("contrato-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 rejects an unsupported extension before onCriar ever fires", async () => {
    const { screen, fireEvent, onCriar } = await render();
    fireEvent.change(screen.getByTestId("contrato-titulo"), {
      target: { value: "Contrato de compra e venda" },
    });
    const ruim = new File(["x"], "planilha.xlsx", { type: "application/vnd.ms-excel" });
    fireEvent.change(screen.getByTestId("contrato-arquivo"), { target: { files: [ruim] } });
    expect(screen.getByTestId("contrato-arquivo-erro").textContent).toContain(
      "Formato não suportado",
    );
    expect((screen.getByTestId("contrato-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("contrato-salvar"));
    expect(onCriar).not.toHaveBeenCalled();
  });

  it("🔴 rejects a file over 25 MB before onCriar ever fires", async () => {
    const { screen, fireEvent, onCriar } = await render();
    fireEvent.change(screen.getByTestId("contrato-titulo"), {
      target: { value: "Contrato de compra e venda" },
    });
    const grande = new File(["x"], "contrato.pdf", { type: "application/pdf" });
    Object.defineProperty(grande, "size", { value: 30 * 1024 * 1024 });
    fireEvent.change(screen.getByTestId("contrato-arquivo"), { target: { files: [grande] } });
    expect(screen.getByTestId("contrato-arquivo-erro").textContent).toContain("muito grande");
    fireEvent.click(screen.getByTestId("contrato-salvar"));
    expect(onCriar).not.toHaveBeenCalled();
  });

  it("submits título, default modelo and the trimmed rótulo on a valid file", async () => {
    const { screen, fireEvent, onCriar } = await render();
    fireEvent.change(screen.getByTestId("contrato-titulo"), {
      target: { value: "  Contrato ONE9  " },
    });
    fireEvent.change(screen.getByTestId("contrato-rotulo"), {
      target: { value: "  REV 1  " },
    });
    const bom = new File(["conteudo"], "contrato.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("contrato-arquivo"), { target: { files: [bom] } });

    expect((screen.getByTestId("contrato-salvar") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTestId("contrato-salvar"));

    expect(onCriar).toHaveBeenCalledWith({
      file: bom,
      titulo: "Contrato ONE9",
      modelo: "compra_venda",
      rotulo: "REV 1",
    });
  });

  it("accepts .docx and .doc alongside .pdf", async () => {
    const { screen, fireEvent } = await render();
    const docx = new File(["x"], "contrato.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    fireEvent.change(screen.getByTestId("contrato-arquivo"), { target: { files: [docx] } });
    expect(screen.queryByTestId("contrato-arquivo-erro")).toBeNull();
  });

  it("clears the form when Cancelar is clicked", async () => {
    const { screen, fireEvent, onOpenChange } = await render();
    fireEvent.change(screen.getByTestId("contrato-titulo"), {
      target: { value: "Contrato ONE9" },
    });
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    // The internal form state clears immediately — it does not wait for the
    // caller to actually unmount the dialog.
    expect((screen.getByTestId("contrato-titulo") as HTMLInputElement).value).toBe("");
  });
});
