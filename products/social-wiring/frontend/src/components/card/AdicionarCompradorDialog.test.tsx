/**
 * AdicionarCompradorDialog — the `"conjuge"` copy variant this slice added
 * (the Cônjuge tab's own empty-state action), alongside the two existing
 * `lado` variants. See the file's own docblock: `lado` is copy-only, so the
 * server-facing shape stays identical across all three — `onCreate` never
 * learns a role, only nome/celular.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { AdicionarCompradorDialog } from "./AdicionarCompradorDialog";

describe("AdicionarCompradorDialog — the conjuge variant", () => {
  it("🔴 titled 'Adicionar cônjuge', not the generic comprador copy", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <AdicionarCompradorDialog
        lado="conjuge"
        open
        onOpenChange={vi.fn()}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByTestId("adicionar-conjuge-dialog")).toBeTruthy();
    expect(screen.getByText("Adicionar cônjuge")).toBeTruthy();
  });

  it("submits {nome, celular} only — never a papel; the container sets papel: \"conjuge\"", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const onCreate = vi.fn();
    render(
      <AdicionarCompradorDialog
        lado="conjuge"
        open
        onOpenChange={vi.fn()}
        onCreate={onCreate}
      />,
    );
    fireEvent.change(screen.getByTestId("comprador-nome-input"), {
      target: { value: "Maria Mauricio" },
    });
    fireEvent.click(screen.getByTestId("comprador-salvar-btn"));
    expect(onCreate).toHaveBeenCalledWith({ nome: "Maria Mauricio", celular: undefined });
  });

  it("defaults to the comprador copy when lado is omitted — unchanged behaviour", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<AdicionarCompradorDialog open onOpenChange={vi.fn()} onCreate={vi.fn()} />);
    expect(screen.getByTestId("adicionar-comprador-dialog")).toBeTruthy();
  });
});
