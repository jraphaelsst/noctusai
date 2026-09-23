/**
 * ChecklistItemRow — the inline per-item editor (`salvar()`).
 *
 * 🔴 THE LOAD-BEARING TEST is "an unset Gênero shows an empty placeholder and
 * confirms as null" — a live bug report (contract-gate audit, 2026-09-22):
 * the `Select` for a `select`-typed field (today only `genero`) used to
 * DISPLAY `rascunho || GENEROS[0]`, so an unset item showed "Masculino" the
 * moment the editor opened even though nothing had been picked — and
 * confirming that visible default with no interaction at all WROTE
 * "Masculino" onto a record nobody ever stated the gênero of. The dropdown
 * now shows "Selecione" for an unset value and Save sends exactly what was
 * on screen: null, unless the operator actually picks one.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import type { DocumentoChecklistItem } from "@/types/cardHub";

import { ChecklistItemRow, type ChecklistItemRowProps } from "./ChecklistItemRow";

function item(key: string, label: string, over: Partial<DocumentoChecklistItem> = {}): DocumentoChecklistItem {
  return {
    key,
    label,
    concluido: false,
    origem: "derivado",
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    ...over,
  };
}

async function renderRow(props: Partial<ChecklistItemRowProps> & { item: DocumentoChecklistItem }) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const onToggle = vi.fn();
  const utils = rtl.render(
    React.createElement(ChecklistItemRow, {
      onToggle,
      ...props,
    }),
  );
  return { ...utils, onToggle };
}

describe("ChecklistItemRow — gênero inline editor", () => {
  it("🔴 shows an empty placeholder for an unset gênero, never Masculino", async () => {
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderRow({
      item: item("genero", "Gênero"),
      valor: null,
      onSaveCampo: vi.fn(),
    });

    rtl.fireEvent.click(getByTestId("documento-checklist-genero-editar"));
    expect(getByTestId("documento-checklist-genero-input").textContent).toContain(
      "Selecione",
    );
  });

  it("🔴 confirming with no interaction sends null, never Masculino", async () => {
    const rtl = await import("@testing-library/react");
    const onSaveCampo = vi.fn();
    const { getByTestId } = await renderRow({
      item: item("genero", "Gênero"),
      valor: null, // never set
      onSaveCampo,
    });

    // Open the inline editor…
    rtl.fireEvent.click(getByTestId("documento-checklist-genero-editar"));
    // …and immediately Salvar, with no click on the dropdown at all — the
    // exact operator action the original bug report describes.
    rtl.fireEvent.click(getByTestId("documento-checklist-genero-salvar"));

    expect(onSaveCampo).toHaveBeenCalledTimes(1);
    expect(onSaveCampo).toHaveBeenCalledWith({ genero: null });
  });

  it("still sends Feminino when the operator does pick it", async () => {
    const rtl = await import("@testing-library/react");
    const onSaveCampo = vi.fn();
    const { getByTestId } = await renderRow({
      item: item("genero", "Gênero"),
      valor: "Feminino",
      onSaveCampo,
    });

    rtl.fireEvent.click(getByTestId("documento-checklist-genero-editar"));
    rtl.fireEvent.click(getByTestId("documento-checklist-genero-salvar"));

    expect(onSaveCampo).toHaveBeenCalledWith({ genero: "Feminino" });
  });

  it("a text item (profissão) still nulls an emptied field, unaffected by the select fallback", async () => {
    const rtl = await import("@testing-library/react");
    const onSaveCampo = vi.fn();
    const { getByTestId } = await renderRow({
      item: item("profissao", "Profissão"),
      valor: "Corretora",
      onSaveCampo,
    });

    rtl.fireEvent.click(getByTestId("documento-checklist-profissao-editar"));
    rtl.fireEvent.change(getByTestId("documento-checklist-profissao-input"), {
      target: { value: "" },
    });
    rtl.fireEvent.click(getByTestId("documento-checklist-profissao-salvar"));

    expect(onSaveCampo).toHaveBeenCalledWith({ profissao: null });
  });
});

// The file-slot rows (upload only while empty, input stays mounted,
// view/download/discard) moved with `rg`/`cpf` into the one identity item —
// `IdentidadeChecklistRow.test.tsx`.
