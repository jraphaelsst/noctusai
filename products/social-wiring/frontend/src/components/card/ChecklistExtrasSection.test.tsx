/**
 * ChecklistExtrasSection — the rows the OPERATOR creates.
 *
 * 🔴 THE LOAD-BEARING TEST is "keeps every extra row mounted during a
 * background refetch" — same class of bug as `DocumentoChecklistSection`
 * (see its docblock): renaming, saving text, or uploading a file on ONE row
 * invalidates this whole list, and the section used to treat the caller's
 * `isPending || isFetching` as "replace everything with a skeleton bar".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import {
  ChecklistExtrasSection,
  type ChecklistExtrasSectionProps,
} from "./ChecklistExtrasSection";
import type { ChecklistExtra } from "@/types/cardHub";

function extra(id: string, over: Partial<ChecklistExtra> = {}): ChecklistExtra {
  return {
    id,
    label: `Comprovante ${id}`,
    tipo: "texto",
    valor_texto: "Aprovado",
    documento: null,
    concluido: true,
    ordem: 0,
    ...over,
  };
}

function baseProps(over: Partial<ChecklistExtrasSectionProps> = {}): ChecklistExtrasSectionProps {
  return {
    items: [],
    onCriar: vi.fn(),
    onRenomear: vi.fn(),
    onSalvarTexto: vi.fn(),
    onRemover: vi.fn(),
    onUploadDocumento: vi.fn(),
    onRemoverDocumento: vi.fn(),
    ...over,
  };
}

async function render(props: ChecklistExtrasSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(ChecklistExtrasSection, props));
}

describe("ChecklistExtrasSection — background refetch never unmounts rows", () => {
  it("🔴 keeps every row mounted while `loading` is true AND rows already exist", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({ items: [extra("e1"), extra("e2")], loading: true }),
    );
    expect(getByTestId("checklist-extras-e1-row")).toBeTruthy();
    expect(getByTestId("checklist-extras-e2-row")).toBeTruthy();
    expect(queryByTestId("checklist-extras-empty")).toBeNull();
  });

  it("shows the skeleton only when there is genuinely nothing to render yet", async () => {
    const { getByTestId, queryByTestId } = await render(baseProps({ items: [], loading: true }));
    expect(getByTestId("checklist-extras-loading")).toBeTruthy();
    expect(queryByTestId("checklist-extras-lista")).toBeNull();
  });

  it("shows the subtle refreshing indicator beside the heading, not over the rows", async () => {
    const { getByTestId } = await render(baseProps({ items: [extra("e1")], refreshing: true }));
    expect(getByTestId("checklist-extras-refreshing")).toBeTruthy();
    expect(getByTestId("checklist-extras-e1-row")).toBeTruthy();
  });

  it("says so when the server sends an empty list (not loading)", async () => {
    const { getByTestId } = await render(baseProps({ items: [] }));
    expect(getByTestId("checklist-extras-empty")).toBeTruthy();
  });
});

describe("uma linha de arquivo já respondida", () => {
  const DOC = {
    id: "doc-9",
    nome_original: "certidao-casamento.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 2048,
    created_at: "2026-09-01T10:00:00Z",
  };
  const comArquivo = (over: Partial<ChecklistExtra> = {}) =>
    extra("e1", { tipo: "arquivo", valor_texto: null, documento: DOC, ...over });

  it("🔴 offers view and download — they were missing here and present on the mandatory rows", async () => {
    // An extra's file goes through `documentos_service.upload_documento` like
    // any other, so it is an ordinary `cliente_documentos` row reached by the
    // same signed-URL round trip. There was never a second id space; the pair
    // was simply never wired.
    const onVisualizarDocumento = vi.fn();
    const onBaixarDocumento = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await render(
      baseProps({ items: [comArquivo()], onVisualizarDocumento, onBaixarDocumento }),
    );

    rtl.fireEvent.click(getByTestId("checklist-extras-e1-visualizar"));
    expect(onVisualizarDocumento).toHaveBeenCalledWith("doc-9");

    rtl.fireEvent.click(getByTestId("checklist-extras-e1-baixar"));
    expect(onBaixarDocumento).toHaveBeenCalledWith("doc-9", "certidao-casamento.pdf");
  });

  it("🔴 drops the upload button, keeping the two destructive ones apart", async () => {
    // Discard-the-FILE and remove-the-ROW both stay — they mean different
    // things and this section is the one place both are offered. What goes is
    // the silent overwrite.
    const { getByTestId, queryByTestId } = await render(baseProps({ items: [comArquivo()] }));
    expect(queryByTestId("checklist-extras-e1-upload")).toBeNull();
    expect(getByTestId("checklist-extras-e1-descartar-arquivo")).toBeTruthy();
    expect(getByTestId("checklist-extras-e1-remover")).toBeTruthy();
  });

  it("a file row still ASKING keeps its upload button and its own input", async () => {
    const { getByTestId } = await render(
      baseProps({ items: [comArquivo({ documento: null })] }),
    );
    expect(getByTestId("checklist-extras-e1-upload").getAttribute("aria-label")).toBe(
      "Enviar Comprovante e1",
    );
    expect(getByTestId("checklist-extras-e1-arquivo-input")).toBeTruthy();
  });

  it("hideHeader drops the title but never the add-a-row buttons", async () => {
    // The create flow's draft state lives in this component, so the buttons
    // cannot move out with the title without lifting that state to every
    // caller — and the second caller would get it subtly wrong.
    const { getByTestId, queryByText } = await render(
      baseProps({ items: [], hideHeader: true }),
    );
    expect(queryByText("Outros dados")).toBeNull();
    expect(getByTestId("checklist-extras-add-texto")).toBeTruthy();
    expect(getByTestId("checklist-extras-add-arquivo")).toBeTruthy();
  });
});
