/**
 * IdentidadeChecklistRow — the ONE "Documento de identidade" item.
 *
 * Owner directives: 2026-09-23 (one item, upload fields per document, one is
 * enough when the data can be read off it) and 2026-09-30 ("rg/cpf" in one
 * slot, then CNH, then CIN; done when the DATA is complete, whichever
 * document supplied it). Pins: the three slots in order, filing under the
 * slot's type, the missing-field readout (incl. a pending reading and the
 * CNH-RG ressalva label), the completed state, legacy `cpf` files read-only.
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

const TRES_SLOTS = () => [slot("rg", "RG/CPF"), slot("cnh", "CNH"), slot("cin", "CIN")];

function item(over: Partial<DocumentoChecklistItem> = {}): DocumentoChecklistItem {
  return {
    key: "identidade",
    label: "Documento de identidade (RG/CPF, CNH ou CIN)",
    concluido: false,
    origem: "derivado",
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    documento: null,
    documentos: TRES_SLOTS(),
    faltando: ["nome_oficial", "rg", "rg_orgao_expedidor", "cpf"],
    faltando_rotulos: ["Nome oficial", "RG", "Órgão expedidor do RG", "CPF"],
    ressalvas: {},
    faltando_com_sugestao: [],
    dica:
      "Basta um documento (RG/CPF, CNH ou CIN), desde que dele se leiam nome, CPF, RG e órgão expedidor; se faltar algum, envie outro.",
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

describe("um item, três campos de envio (RG/CPF, CNH, CIN)", () => {
  it("🔴 offers RG/CPF, then CNH, then CIN — in that order — and says one is enough", async () => {
    const { getByTestId, getAllByTestId } = await renderRow({ item: item(), onUploadDocumento: vi.fn() });
    expect(getAllByTestId(/-slot$/).map((el) => el.getAttribute("data-testid"))).toEqual([
      `${P}-rg-slot`,
      `${P}-cnh-slot`,
      `${P}-cin-slot`,
    ]);
    expect(getByTestId(`${P}-rg-upload`).getAttribute("aria-label")).toBe("Enviar RG/CPF");
    expect(getByTestId(`${P}-cnh-upload`).getAttribute("aria-label")).toBe("Enviar CNH");
    expect(getByTestId(`${P}-cin-upload`).getAttribute("aria-label")).toBe("Enviar CIN");
    expect(getByTestId(`${P}-dica`).textContent).toContain("Basta um documento");
  });

  it("🔴 each slot keeps its own stable file input (rg / cnh / cin)", async () => {
    const { getByTestId } = await renderRow({ item: item(), onUploadDocumento: vi.fn() });
    expect(getByTestId(`${P}-rg-arquivo-input`)).toBeTruthy();
    expect(getByTestId(`${P}-cnh-arquivo-input`)).toBeTruthy();
    expect(getByTestId(`${P}-cin-arquivo-input`)).toBeTruthy();
  });

  it.each([
    ["rg", "rg.pdf"],
    ["cnh", "cnh.pdf"],
    ["cin", "cin.pdf"],
  ])("🔴 a file dropped in the %s slot is filed under that type, never the item key", async (tipo, nome) => {
    const onUploadDocumento = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderRow({ item: item(), onUploadDocumento });
    const file = new File(["x"], nome, { type: "application/pdf" });
    rtl.fireEvent.change(getByTestId(`${P}-${tipo}-arquivo-input`), { target: { files: [file] } });
    expect(onUploadDocumento).toHaveBeenCalledWith(expect.objectContaining({ key: "identidade" }), file, tipo);
  });

  it("disables every upload while a send is in flight", async () => {
    const { getByTestId } = await renderRow({ item: item(), onUploadDocumento: vi.fn(), uploading: true });
    for (const tipo of ["rg", "cnh", "cin"]) {
      expect((getByTestId(`${P}-${tipo}-upload`) as HTMLButtonElement).disabled).toBe(true);
    }
  });
});

describe("conclusão pelos DADOS, venham de qual documento vierem", () => {
  it("🔴 lists every missing field and asks for another document", async () => {
    const { getByTestId } = await renderRow({ item: item() });
    expect(getByTestId(`${P}-faltando-nome_oficial`).textContent).toBe("Nome oficial");
    expect(getByTestId(`${P}-faltando-rg_orgao_expedidor`).textContent).toBe("Órgão expedidor do RG");
    expect(getByTestId(`${P}-faltando-acao`).textContent).toContain("Envie outro documento (RG/CPF, CNH ou CIN)");
  });

  it("🔴 names only what is still missing when one document was not enough", async () => {
    const { getByTestId, queryByTestId } = await renderRow({
      item: item({
        documentos: [slot("rg", "RG/CPF", { documento: DOC }), slot("cnh", "CNH"), slot("cin", "CIN")],
        faltando: ["cpf"],
        faltando_rotulos: ["CPF"],
      }),
    });
    expect(getByTestId(`${P}-faltando-cpf`).textContent).toBe("CPF");
    expect(queryByTestId(`${P}-faltando-rg`)).toBeNull();
    expect(getByTestId(`${P}-faltando-acao`).textContent).toContain("esse dado");
  });

  it("🔴 a field with a pending reading says to confirm it, not to send another document", async () => {
    const { getByTestId, queryByTestId } = await renderRow({
      item: item({
        faltando: ["rg_orgao_expedidor"],
        faltando_rotulos: ["Órgão expedidor do RG"],
        faltando_com_sugestao: ["rg_orgao_expedidor"],
      }),
    });
    expect(getByTestId(`${P}-faltando-rg_orgao_expedidor-sugestao`).textContent).toContain(
      "aguardando confirmação",
    );
    expect(queryByTestId(`${P}-faltando-acao`)).toBeNull();
  });

  it("🔴 an RG read only off the CNH shows the server's explanatory label", async () => {
    const rotulo =
      "RG com dígito verificador (lido só da CNH, que costuma omiti-lo — confirme o número ou envie o RG/CPF)";
    const { getByTestId } = await renderRow({
      item: item({
        documentos: [slot("rg", "RG/CPF"), slot("cnh", "CNH", { documento: DOC }), slot("cin", "CIN")],
        faltando: ["rg"],
        faltando_rotulos: [rotulo],
        ressalvas: { rg: "rg_so_da_cnh" },
      }),
    });
    expect(getByTestId(`${P}-faltando-rg`).textContent).toBe(rotulo);
  });

  it("🔴 complete data — whichever document supplied it — names nothing missing", async () => {
    const { queryByTestId, getByTestId } = await renderRow({
      item: item({
        concluido: true,
        derivado: true,
        documentos: [slot("rg", "RG/CPF"), slot("cnh", "CNH"), slot("cin", "CIN", { documento: DOC })],
        faltando: [],
        faltando_rotulos: [],
      }),
    });
    expect(queryByTestId(`${P}-faltando`)).toBeNull();
    expect(getByTestId(`${P}-completo`).textContent).toContain("completos");
  });

  it("a manual tick over incomplete data does not claim the data is complete", async () => {
    const { queryByTestId } = await renderRow({
      item: item({ concluido: true, origem: "manual", derivado: false, faltando: [], faltando_rotulos: [] }),
    });
    expect(queryByTestId(`${P}-completo`)).toBeNull();
  });
});

describe("um documento já entregue não oferece mais o upload", () => {
  it("🔴 an ANSWERED slot drops the upload button entirely", async () => {
    // It used to stay, relabelled "Substituir" — the control that silently
    // overwrites the answer. Replacing is the deliberate two-step now.
    const { queryByTestId } = await renderRow({
      item: item({ documentos: [slot("rg", "RG/CPF"), slot("cnh", "CNH", { documento: DOC }), slot("cin", "CIN")] }),
      onUploadDocumento: vi.fn(),
    });
    expect(queryByTestId(`${P}-cnh-upload`)).toBeNull();
    expect(queryByTestId(`${P}-rg-upload`)).not.toBeNull();
    expect(queryByTestId(`${P}-cin-upload`)).not.toBeNull();
  });

  it("🔴 keeps its own file input mounted even while answered", async () => {
    const { getByTestId } = await renderRow({
      item: item({ documentos: [slot("cnh", "CNH", { documento: DOC })] }),
      onUploadDocumento: vi.fn(),
    });
    expect(getByTestId(`${P}-cnh-arquivo-input`)).toBeTruthy();
  });

  it.each(["rg", "cnh", "cin"])(
    "an answered %s slot offers view, download and discard instead",
    async (tipo) => {
      const onVisualizarDocumento = vi.fn();
      const onBaixarDocumento = vi.fn();
      const onRemoverDocumento = vi.fn();
      const rtl = await import("@testing-library/react");
      const { getByTestId } = await renderRow({
        item: item({ documentos: [slot(tipo, tipo.toUpperCase(), { documento: DOC })] }),
        onUploadDocumento: vi.fn(),
        onVisualizarDocumento,
        onBaixarDocumento,
        onRemoverDocumento,
      });

      expect(getByTestId(`${P}-${tipo}-valor`).textContent).toContain("cnh-frente.pdf");
      rtl.fireEvent.click(getByTestId(`${P}-${tipo}-visualizar`));
      expect(onVisualizarDocumento).toHaveBeenCalledWith("doc-1");
      rtl.fireEvent.click(getByTestId(`${P}-${tipo}-baixar`));
      expect(onBaixarDocumento).toHaveBeenCalledWith("doc-1", "cnh-frente.pdf");
      rtl.fireEvent.click(getByTestId(`${P}-${tipo}-descartar-arquivo`));
      expect(onRemoverDocumento).toHaveBeenCalled();
    },
  );
});

describe("arquivos legados (cpf)", () => {
  it("🔴 a legacy cpf file is listed read-only — never an upload target", async () => {
    const { getByTestId, queryByTestId } = await renderRow({
      item: item({
        documentos: [
          ...TRES_SLOTS(),
          slot("cpf", "Arquivado como CPF", { upload: false, documento: { ...DOC, nome_original: "cpf.pdf" } }),
        ],
      }),
      onUploadDocumento: vi.fn(),
      onVisualizarDocumento: vi.fn(),
    });
    expect(getByTestId(`${P}-cpf-valor`).textContent).toContain("cpf.pdf");
    expect(queryByTestId(`${P}-cpf-upload`)).toBeNull();
    expect(queryByTestId(`${P}-cpf-arquivo-input`)).toBeNull();
    expect(getByTestId(`${P}-cpf-visualizar`)).toBeTruthy();
  });
});
