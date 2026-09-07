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

describe("um documento já entregue não oferece mais o upload", () => {
  const DOC = {
    id: "doc-1",
    nome_original: "rg-frente.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 1024,
    created_at: "2026-09-01T10:00:00Z",
  };

  it("🔴 an ANSWERED document row drops the upload button entirely", async () => {
    // It used to stay, relabelled "Substituir" — so the control that silently
    // overwrites the answer sat where the eye had learned to find "the button
    // for this row", and the displaced file is soft-deleted without saying so.
    // Replacing is the deliberate two-step now: discard, then upload.
    const { queryByTestId } = await renderRow({
      item: item("rg", "RG", { documento: DOC }),
      onUploadDocumento: vi.fn(),
    });
    expect(queryByTestId("documento-checklist-rg-upload")).toBeNull();
  });

  it("a row still ASKING keeps its upload button", async () => {
    const { getByTestId } = await renderRow({
      item: item("rg", "RG"),
      onUploadDocumento: vi.fn(),
    });
    const btn = getByTestId("documento-checklist-rg-upload");
    expect(btn.getAttribute("aria-label")).toBe("Enviar RG");
  });

  it("🔴 keeps its own file input mounted even while answered", async () => {
    // Addressed by ref, and a row whose file was just discarded must accept
    // the next one without waiting for a remount.
    const { getByTestId } = await renderRow({
      item: item("rg", "RG", { documento: DOC }),
      onUploadDocumento: vi.fn(),
    });
    expect(getByTestId("documento-checklist-rg-arquivo-input")).toBeTruthy();
  });

  it("an answered row offers view, download and discard instead", async () => {
    const onVisualizarDocumento = vi.fn();
    const onBaixarDocumento = vi.fn();
    const onRemoverDocumento = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderRow({
      item: item("rg", "RG", { documento: DOC }),
      onUploadDocumento: vi.fn(),
      onVisualizarDocumento,
      onBaixarDocumento,
      onRemoverDocumento,
    });

    rtl.fireEvent.click(getByTestId("documento-checklist-rg-visualizar"));
    expect(onVisualizarDocumento).toHaveBeenCalledWith("doc-1");

    rtl.fireEvent.click(getByTestId("documento-checklist-rg-baixar"));
    expect(onBaixarDocumento).toHaveBeenCalledWith("doc-1", "rg-frente.pdf");

    rtl.fireEvent.click(getByTestId("documento-checklist-rg-descartar-arquivo"));
    expect(onRemoverDocumento).toHaveBeenCalled();
  });
});
