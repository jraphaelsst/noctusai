/**
 * IdentidadeChecklistRow — the ONE "Documento de identidade (RG e CPF)" item
 * (owner directive, 2026-09-23): CIN + CNH slots under one tick, the
 * "only one is needed" hint, the missing-number readout, legacy rg/cpf files
 * read-only. The file-slot tests moved here from `ChecklistItemRow.test.tsx`
 * together with the `rg`/`cpf` rows they used to pin.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import type { DocumentoChecklistItem, IdentidadeSlot } from "@/types/cardHub";

import { IdentidadeChecklistRow, type IdentidadeChecklistRowProps } from "./IdentidadeChecklistRow";

const DOC = {
  id: "doc-1",
  nome_original: "cnh-frente.pdf",
  mime_type: "application/pdf",
  tamanho_bytes: 1024,
  created_at: "2026-09-01T10:00:00Z",
};

function slot(tipo: string, rotulo: string, over: Partial<IdentidadeSlot> = {}): IdentidadeSlot {
  return { tipo_documento: tipo, rotulo, upload: true, documento: null, ...over };
}

function item(over: Partial<DocumentoChecklistItem> = {}): DocumentoChecklistItem {
  return {
    key: "identidade",
    label: "Documento de identidade (RG e CPF)",
    concluido: false,
    origem: "derivado",
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    documento: null,
    documentos: [slot("cin", "CIN"), slot("cnh", "CNH")],
    faltando: ["rg", "cpf"],
    faltando_rotulos: ["RG", "CPF"],
    dica: "Basta um dos dois (CIN ou CNH), desde que dele se leiam o RG e o CPF.",
    ...over,
  };
}

async function renderRow(props: Partial<IdentidadeChecklistRowProps> & { item: DocumentoChecklistItem }) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const onToggle = vi.fn();
  const utils = rtl.render(
    React.createElement("ul", null, React.createElement(IdentidadeChecklistRow, { onToggle, ...props })),
  );
  return { ...utils, onToggle };
}

const P = "documento-checklist-identidade";

describe("um item, dois campos de envio", () => {
  it("🔴 offers a CIN and a CNH slot and says only one is needed", async () => {
    const { getByTestId } = await renderRow({ item: item(), onUploadDocumento: vi.fn() });
    expect(getByTestId(`${P}-cin-upload`).getAttribute("aria-label")).toBe("Enviar CIN");
    expect(getByTestId(`${P}-cnh-upload`).getAttribute("aria-label")).toBe("Enviar CNH");
    expect(getByTestId(`${P}-dica`).textContent).toContain("Basta um dos dois");
  });

  it("🔴 a file is filed under its SLOT's type, never the item key", async () => {
    const onUploadDocumento = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderRow({ item: item(), onUploadDocumento });
    const file = new File(["x"], "cin.pdf", { type: "application/pdf" });
    rtl.fireEvent.change(getByTestId(`${P}-cin-arquivo-input`), { target: { files: [file] } });
    expect(onUploadDocumento).toHaveBeenCalledWith(expect.objectContaining({ key: "identidade" }), file, "cin");
  });

  it("🔴 names which number is still missing", async () => {
    const { getByTestId } = await renderRow({
      item: item({ faltando: ["rg"], faltando_rotulos: ["RG"] }),
    });
    expect(getByTestId(`${P}-faltando`).textContent).toContain("Falta: RG");
  });

  it("a satisfied item names nothing missing", async () => {
    const { queryByTestId } = await renderRow({
      item: item({ concluido: true, derivado: true, faltando: [], faltando_rotulos: [] }),
    });
    expect(queryByTestId(`${P}-faltando`)).toBeNull();
  });
});

describe("um documento já entregue não oferece mais o upload", () => {
  it("🔴 an ANSWERED slot drops the upload button entirely", async () => {
    // It used to stay, relabelled "Substituir" — the control that silently
    // overwrites the answer. Replacing is the deliberate two-step now.
    const { queryByTestId } = await renderRow({
      item: item({ documentos: [slot("cin", "CIN"), slot("cnh", "CNH", { documento: DOC })] }),
      onUploadDocumento: vi.fn(),
    });
    expect(queryByTestId(`${P}-cnh-upload`)).toBeNull();
    expect(queryByTestId(`${P}-cin-upload`)).not.toBeNull();
  });

  it("🔴 keeps its own file input mounted even while answered", async () => {
    const { getByTestId } = await renderRow({
      item: item({ documentos: [slot("cnh", "CNH", { documento: DOC })] }),
      onUploadDocumento: vi.fn(),
    });
    expect(getByTestId(`${P}-cnh-arquivo-input`)).toBeTruthy();
  });

  it("an answered slot offers view, download and discard instead", async () => {
    const onVisualizarDocumento = vi.fn();
    const onBaixarDocumento = vi.fn();
    const onRemoverDocumento = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderRow({
      item: item({ documentos: [slot("cnh", "CNH", { documento: DOC })] }),
      onUploadDocumento: vi.fn(),
      onVisualizarDocumento,
      onBaixarDocumento,
      onRemoverDocumento,
    });

    rtl.fireEvent.click(getByTestId(`${P}-cnh-visualizar`));
    expect(onVisualizarDocumento).toHaveBeenCalledWith("doc-1");
    rtl.fireEvent.click(getByTestId(`${P}-cnh-baixar`));
    expect(onBaixarDocumento).toHaveBeenCalledWith("doc-1", "cnh-frente.pdf");
    rtl.fireEvent.click(getByTestId(`${P}-cnh-descartar-arquivo`));
    expect(onRemoverDocumento).toHaveBeenCalled();
  });
});

describe("arquivos legados (rg/cpf)", () => {
  it("🔴 a legacy rg file is listed read-only — never an upload target", async () => {
    const { getByTestId, queryByTestId } = await renderRow({
      item: item({
        documentos: [
          slot("cin", "CIN"),
          slot("cnh", "CNH"),
          slot("rg", "Arquivado como RG", { upload: false, documento: { ...DOC, nome_original: "CNH_Rodrigo.pdf" } }),
        ],
      }),
      onUploadDocumento: vi.fn(),
      onVisualizarDocumento: vi.fn(),
    });
    expect(getByTestId(`${P}-rg-valor`).textContent).toContain("CNH_Rodrigo.pdf");
    expect(queryByTestId(`${P}-rg-upload`)).toBeNull();
    expect(queryByTestId(`${P}-rg-arquivo-input`)).toBeNull();
    expect(getByTestId(`${P}-rg-visualizar`)).toBeTruthy();
  });
});
