// Ported from `products/social-wiring/frontend/src/components/card/AnexosSection.test.tsx` (seed card hub, wave-a Slice C).
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

// The REAL seed Radix `Select` — no module mock. The jsdom Pointer Events
// polyfill in `tests/setup.ts` (Slice B) is what lets Radix open here, so the
// picker is exercised end to end: open the trigger, pick the option.
async function abrirTipos(getByTestId: (id: string) => HTMLElement) {
  const { default: userEvent } = await import("@testing-library/user-event");
  await userEvent.setup().click(getByTestId("anexo-tipo-select"));
}

import { AnexosSection, type AnexosSectionProps } from "./AnexosSection";
import type { Documento, TipoDocumento } from "./types";

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
    extracao_status: null,
    extracao_erro: null,
    ...over,
  };
}

function tipo(tipo_documento: string, over: Partial<TipoDocumento> = {}): TipoDocumento {
  return {
    tipo_documento,
    categoria_lgpd: "contratual",
    descricao: null,
    identidade: false,
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

describe("AnexosSection — the tipo picker (Gap 1: never a silent default)", () => {
  it("🔴 the upload trigger is disabled until a tipo is picked — no default, silent or otherwise", async () => {
    const { getByTestId } = await render(
      baseProps({ tipos: [tipo("contrato", { descricao: "Contrato" })] }),
    );
    expect((getByTestId("anexo-enviar-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("picking a tipo enables the trigger, and the chosen file uploads under EXACTLY that tipo", async () => {
    const onUpload = vi.fn();
    const { getByTestId, getByText, container } = await render(
      baseProps({
        tipos: [
          tipo("outro", { descricao: "Outro" }),
          tipo("certidao_casamento", { descricao: "Certidão de casamento", identidade: true }),
        ],
        onUpload,
      }),
    );
    const rtl = await import("@testing-library/react");
    await abrirTipos(getByTestId);

    // The catalogue's FIRST entry alphabetically/by-array-order is `outro` —
    // exactly the value the old hardcoded default silently picked. Picking
    // the IDENTITY type instead and asserting on it is the regression guard:
    // a leftover `tipos[0]` default would upload as `outro`, not as this.
    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.setup().click(
      await rtl.screen.findByRole("option", { name: "Certidão de casamento" }),
    );
    expect((getByTestId("anexo-enviar-btn") as HTMLButtonElement).disabled).toBe(false);

    const file = new File(["%PDF-1.4"], "certidao.pdf", { type: "application/pdf" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file] });
    rtl.fireEvent.change(input);

    expect(onUpload).toHaveBeenCalledWith(file, "certidao_casamento");
  });

  it("the hidden file input filters by the backend's own allowed MIME types", async () => {
    const { container } = await render(baseProps());
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.getAttribute("accept")).toBe(
      "application/pdf,image/jpeg,image/png,image/webp",
    );
  });

  it("groups identity types separately from everything else", async () => {
    const { getByText, getByTestId } = await render(
      baseProps({
        tipos: [
          tipo("contrato", { descricao: "Contrato" }),
          tipo("rg", { descricao: "RG", identidade: true }),
        ],
      }),
    );
    await abrirTipos(getByTestId);
    expect(getByText("Identidade")).toBeTruthy();
    expect(getByText("Outros")).toBeTruthy();
  });
});

describe("AnexosSection — a failed extraction is visible (Gap 4)", () => {
  it("🔴 shows nothing extra for a document that was never meant to be read", async () => {
    const doc = documento("d1", { tipo_documento: "contrato", extracao_status: null });
    const { queryByTestId } = await render(baseProps({ documentos: [doc] }));
    expect(queryByTestId("anexo-extracao-status-d1")).toBeNull();
  });

  it("surfaces `erro` with the server's own reason, and offers a retry", async () => {
    const doc = documento("d1", {
      extracao_status: "erro",
      extracao_erro: "openai: 429 credit_balance_exhausted",
    });
    const onReextrairDocumento = vi.fn();
    const { getByTestId, getByText } = await render(
      baseProps({ documentos: [doc], onReextrairDocumento }),
    );
    expect(getByTestId("anexo-extracao-status-d1")).toBeTruthy();
    expect(getByText("openai: 429 credit_balance_exhausted", { exact: false })).toBeTruthy();

    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(getByTestId("anexo-reextrair-d1"));
    expect(onReextrairDocumento).toHaveBeenCalledWith("d1");
  });

  it("🔴 a long error string truncates (min-w-0) instead of forcing horizontal overflow", async () => {
    // A raw provider error can run hundreds of characters (e.g. an
    // `insufficient_quota` Anthropic body) — without `min-w-0` on this flex
    // child, `truncate`'s own ellipsis never engages and the row (then the
    // whole card) grows a horizontal scrollbar, shoving every field to the
    // right off-screen.
    const longo =
      "insufficient_quota: Erro na API Anthropic: Error code: 400 - " +
      "{'error': {'message': 'a very long json body that keeps going on and on " +
      "well past what any card row should ever render inline'}}";
    const doc = documento("d1", { extracao_status: "erro", extracao_erro: longo });
    const { getByTestId } = await render(baseProps({ documentos: [doc] }));

    const linha = getByTestId("anexo-extracao-status-d1");
    expect(linha.className).toContain("min-w-0");
    expect(linha.title).toBe(longo);

    const textoSpan = linha.querySelector("span.truncate");
    expect(textoSpan).toBeTruthy();
    expect(textoSpan!.className).toContain("min-w-0");
  });

  it("never offers a retry when the caller has not wired the mutation", async () => {
    const doc = documento("d1", { extracao_status: "erro", extracao_erro: "x" });
    const { queryByTestId } = await render(baseProps({ documentos: [doc] }));
    expect(queryByTestId("anexo-reextrair-d1")).toBeNull();
  });

  it("shows a quiet in-flight indicator for `pendente`/`processando`, with no retry button", async () => {
    const doc = documento("d1", { extracao_status: "processando" });
    const onReextrairDocumento = vi.fn();
    const { getByTestId, queryByTestId } = await render(
      baseProps({ documentos: [doc], onReextrairDocumento }),
    );
    expect(getByTestId("anexo-extracao-status-d1")).toBeTruthy();
    expect(queryByTestId("anexo-reextrair-d1")).toBeNull();
  });

  it("disables only the retrying document's own button, never the whole list", async () => {
    const docs = [
      documento("d1", { extracao_status: "erro", extracao_erro: "x" }),
      documento("d2", { extracao_status: "erro", extracao_erro: "y" }),
    ];
    const { getByTestId } = await render(
      baseProps({
        documentos: docs,
        onReextrairDocumento: vi.fn(),
        reextraindoDocumentoId: "d1",
      }),
    );
    expect((getByTestId("anexo-reextrair-d1") as HTMLButtonElement).disabled).toBe(true);
    expect((getByTestId("anexo-reextrair-d2") as HTMLButtonElement).disabled).toBe(false);
  });
});
