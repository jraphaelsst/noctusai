/**
 * ChecklistItemRow — the inline per-item editor (`salvar()`).
 *
 * 🔴 THE LOAD-BEARING TEST is "confirming the visible Gênero default sends
 * Masculino, not null" — a live bug report ("gênero not setting masculino,
 * only feminino"). The `Select` for a `select`-typed field (today only
 * `genero`) DISPLAYS `rascunho || GENEROS[0]`, so an unset item shows
 * "Masculino" the moment the editor opens — but `rascunho` itself only
 * changes if the operator actually clicks the dropdown. Confirming what
 * is already on screen with no interaction used to send the RAW `rascunho`
 * (still `""`), which `salvar()` then nulled — silently clearing the field
 * instead of saving the value the operator just confirmed. Picking
 * "Feminino" always fires `onValueChange` first, which is why only
 * Masculino ever failed to round-trip.
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
  it("🔴 sends Masculino when the operator confirms the shown default without touching the dropdown", async () => {
    const rtl = await import("@testing-library/react");
    const onSaveCampo = vi.fn();
    const { getByTestId } = await renderRow({
      item: item("genero", "Gênero"),
      valor: null, // never set — the row shows the "Masculino" fallback
      onSaveCampo,
    });

    // Open the inline editor…
    rtl.fireEvent.click(getByTestId("documento-checklist-genero-editar"));
    // …and immediately Salvar, with no click on the dropdown at all — the
    // exact operator action the bug report describes.
    rtl.fireEvent.click(getByTestId("documento-checklist-genero-salvar"));

    expect(onSaveCampo).toHaveBeenCalledTimes(1);
    expect(onSaveCampo).toHaveBeenCalledWith({ genero: "Masculino" });
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
