/**
 * `DocumentoTipoSlot` — the generalized upload slot (tech-lead decision H7).
 * `CertidaoCasamentoSlot.test.tsx` already pins that its own refactor onto
 * this component changed NOTHING observable; this file exercises the
 * GENERIC shape directly with a second `tipoDocumento`/label (Cartão CNPJ),
 * including a document shape narrower than `@/types/cardHub`'s `Documento`
 * (`EmpresaDocumento`-shaped) — the whole point of H7's generalization.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DocumentoTipoSlot, documentoDoTipo } from "./DocumentoTipoSlot";

interface MinimalDoc {
  id: string;
  nome_original: string;
  tamanho_bytes: number;
  tipo_documento: string;
}

function empresaDoc(over: Partial<MinimalDoc> = {}): MinimalDoc {
  return {
    id: "doc-1",
    nome_original: "cartao_cnpj.pdf",
    tamanho_bytes: 4096,
    tipo_documento: "cartao_cnpj",
    ...over,
  };
}

describe("documentoDoTipo", () => {
  it("finds the document of the given tipo among a narrower (empresa-shaped) list", () => {
    const outro = empresaDoc({ id: "d-outro", tipo_documento: "outro" });
    const cartao = empresaDoc({ id: "d-cartao" });
    expect(documentoDoTipo([outro, cartao], "cartao_cnpj")?.id).toBe("d-cartao");
  });

  it("returns undefined when none is on file", () => {
    expect(documentoDoTipo([empresaDoc({ tipo_documento: "outro" })], "cartao_cnpj")).toBeUndefined();
  });
});

describe("DocumentoTipoSlot", () => {
  it("asks for the file when none is on record, under the caller's own label", () => {
    render(
      <DocumentoTipoSlot
        documentos={[]}
        tipoDocumento="cartao_cnpj"
        label="Cartão CNPJ"
        onUpload={vi.fn()}
        testId="empresa-cartao-x"
      />,
    );
    expect(screen.getByTestId("empresa-cartao-x-label").textContent).toContain("Cartão CNPJ");
    expect(screen.getByTestId("empresa-cartao-x-valor").textContent).toContain("—");
    expect(screen.getByTestId("empresa-cartao-x-upload")).toBeTruthy();
    expect(screen.queryByTestId("empresa-cartao-x-visualizar")).toBeNull();
  });

  it("uploads the file typed as the caller's `tipoDocumento`", () => {
    const onUpload = vi.fn();
    render(
      <DocumentoTipoSlot
        documentos={[]}
        tipoDocumento="cartao_cnpj"
        label="Cartão CNPJ"
        onUpload={onUpload}
        testId="empresa-cartao-x"
      />,
    );
    const file = new File(["conteudo"], "cartao.pdf", { type: "application/pdf" });
    const input = screen.getByTestId("empresa-cartao-x-arquivo-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("once on file, offers view/download/discard instead of upload", () => {
    const onVisualizar = vi.fn();
    const onBaixar = vi.fn();
    const onRemover = vi.fn();
    render(
      <DocumentoTipoSlot
        documentos={[empresaDoc()]}
        tipoDocumento="cartao_cnpj"
        label="Cartão CNPJ"
        onUpload={vi.fn()}
        onVisualizar={onVisualizar}
        onBaixar={onBaixar}
        onRemover={onRemover}
        testId="empresa-cartao-x"
      />,
    );
    expect(screen.queryByTestId("empresa-cartao-x-upload")).toBeNull();
    expect(screen.getByTestId("empresa-cartao-x-valor").textContent).toContain("cartao_cnpj.pdf");

    fireEvent.click(screen.getByTestId("empresa-cartao-x-visualizar"));
    expect(onVisualizar).toHaveBeenCalledWith("doc-1");

    fireEvent.click(screen.getByTestId("empresa-cartao-x-baixar"));
    expect(onBaixar).toHaveBeenCalledWith("doc-1", "cartao_cnpj.pdf");

    fireEvent.click(screen.getByTestId("empresa-cartao-x-descartar"));
    expect(onRemover).toHaveBeenCalledWith("doc-1", expect.any(String));
  });
});

afterEach(() => {
  cleanup();
});
