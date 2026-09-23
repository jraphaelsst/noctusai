import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import {
  CertidaoCasamentoSlot,
  TIPO_CERTIDAO_CASAMENTO,
  certidaoCasamentoDe,
} from "./CertidaoCasamentoSlot";
import type { Documento } from "@/types/cardHub";

afterEach(() => {
  cleanup();
});

function documento(over: Partial<Documento> = {}): Documento {
  return {
    id: "doc-1",
    nome_original: "certidao.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 2048,
    tipo_documento: TIPO_CERTIDAO_CASAMENTO,
    categoria_lgpd: "identidade",
    retencao_ate: null,
    enviado_por: { id: "u-1", nome: "Operador" } as Documento["enviado_por"],
    created_at: "2026-09-01T00:00:00Z",
    thumbnail_url: null,
    extracao_status: "ok",
    extracao_erro: null,
    ...over,
  };
}

describe("certidaoCasamentoDe", () => {
  it("finds the certidao_casamento document among a party's documentos", () => {
    const outro = documento({ id: "d-outro", tipo_documento: "outro" });
    const casamento = documento({ id: "d-cert" });
    expect(certidaoCasamentoDe([outro, casamento])?.id).toBe("d-cert");
  });

  it("returns undefined when none is on file", () => {
    expect(certidaoCasamentoDe([documento({ tipo_documento: "rg" })])).toBeUndefined();
  });
});

describe("CertidaoCasamentoSlot", () => {
  it("asks for the file when none is on record", () => {
    render(
      <CertidaoCasamentoSlot documentos={[]} onUpload={vi.fn()} testId="certidao-x" />,
    );
    expect(screen.getByTestId("certidao-x-label").textContent).toContain(
      "Certidão de casamento",
    );
    expect(screen.getByTestId("certidao-x-valor").textContent).toContain("—");
    expect(screen.getByTestId("certidao-x-upload")).toBeTruthy();
    expect(screen.queryByTestId("certidao-x-visualizar")).toBeNull();
  });

  it("🔴 uploads the file typed as `certidao_casamento` — never a generic anexo", () => {
    const onUpload = vi.fn();
    render(
      <CertidaoCasamentoSlot documentos={[]} onUpload={onUpload} testId="certidao-x" />,
    );
    const file = new File(["conteudo"], "certidao.pdf", { type: "application/pdf" });
    const input = screen.getByTestId("certidao-x-arquivo-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("once on file, offers view/download/discard instead of upload", () => {
    const onVisualizar = vi.fn();
    const onBaixar = vi.fn();
    const onRemover = vi.fn();
    render(
      <CertidaoCasamentoSlot
        documentos={[documento()]}
        onUpload={vi.fn()}
        onVisualizar={onVisualizar}
        onBaixar={onBaixar}
        onRemover={onRemover}
        testId="certidao-x"
      />,
    );
    expect(screen.queryByTestId("certidao-x-upload")).toBeNull();
    expect(screen.getByTestId("certidao-x-valor").textContent).toContain("certidao.pdf");

    fireEvent.click(screen.getByTestId("certidao-x-visualizar"));
    expect(onVisualizar).toHaveBeenCalledWith("doc-1");

    fireEvent.click(screen.getByTestId("certidao-x-baixar"));
    expect(onBaixar).toHaveBeenCalledWith("doc-1", "certidao.pdf");

    fireEvent.click(screen.getByTestId("certidao-x-descartar"));
    expect(onRemover).toHaveBeenCalledWith("doc-1", expect.any(String));
  });
});
