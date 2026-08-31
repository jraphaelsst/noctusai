/**
 * AnexosSection — the files attached to one person, as files.
 *
 * 🔴 THE LOAD-BEARING TEST is "keeps every attachment mounted during a
 * background refetch" — same class of bug as `DocumentoChecklistSection`
 * (see its docblock): the caller's `documentos.isPending ||
 * documentos.isFetching` stays true through every refetch this list's own
 * mutations trigger, and this component used to treat that ONE boolean as
 * "replace the list with a skeleton bar".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { AnexosSection, type AnexosSectionProps } from "./AnexosSection";
import type { Documento } from "@/types/cardHub";

function documento(id: string, over: Partial<Documento> = {}): Documento {
  return {
    id,
    nome_original: `RG-${id}.pdf`,
    mime_type: "application/pdf",
    tamanho_bytes: 102_400,
    tipo_documento: "rg",
    categoria_lgpd: "identidade",
    retencao_ate: null,
    enviado_por: { id: "corretor-1", nome: "Ana Prado" },
    created_at: "2026-08-25T12:00:00+00:00",
    thumbnail_url: null,
    ...over,
  };
}

function baseProps(over: Partial<AnexosSectionProps> = {}): AnexosSectionProps {
  return {
    documentos: [],
    loading: false,
    onUpload: vi.fn(),
    onOpenDocumento: vi.fn(),
    onDeleteDocumento: vi.fn(),
    ...over,
  };
}

async function render(props: AnexosSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(AnexosSection, props));
}

describe("AnexosSection — background refetch never unmounts attachments", () => {
  it("🔴 keeps every attachment mounted while `loading` is true AND they already exist", async () => {
    const docs = [documento("d1"), documento("d2")];
    const { getByTestId, queryByTestId } = await render(baseProps({ documentos: docs, loading: true }));
    expect(getByTestId("anexo-item-d1")).toBeTruthy();
    expect(getByTestId("anexo-item-d2")).toBeTruthy();
    // No skeleton `<div>` sits in place of the list when there is data —
    // the section renders straight to the `<ul>`.
    expect(queryByTestId("anexos-empty")).toBeNull();
  });

  it("shows the skeleton only when there is genuinely nothing to render yet", async () => {
    const { getByTestId } = await render(baseProps({ documentos: [], loading: true }));
    expect(getByTestId("anexos-section")).toBeTruthy();
  });

  it("never renders the empty state over attachments that exist mid-refetch", async () => {
    const { queryByTestId, getByTestId } = await render(
      baseProps({ documentos: [documento("d1")], loading: true }),
    );
    expect(queryByTestId("anexos-empty")).toBeNull();
    expect(getByTestId("anexo-item-d1")).toBeTruthy();
  });

  it("shows the subtle refreshing indicator beside the heading, not over the list", async () => {
    const { getByTestId } = await render(
      baseProps({ documentos: [documento("d1")], refreshing: true }),
    );
    expect(getByTestId("anexos-refreshing")).toBeTruthy();
    expect(getByTestId("anexo-item-d1")).toBeTruthy();
  });

  it("says so when the server sends an empty list (not loading)", async () => {
    const { getByTestId } = await render(baseProps({ documentos: [] }));
    expect(getByTestId("anexos-empty")).toBeTruthy();
  });
});
