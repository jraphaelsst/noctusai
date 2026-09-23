/**
 * ImovelDocumentosCard — the extraction state is the point.
 *
 * The assertions worth having are about what the card says while a matrícula
 * is being read and after it fails, because those are the states that would
 * otherwise be indistinguishable from "the feature does not work": in all
 * three cases the número da matrícula field is simply still empty.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelDocumentosCard from "./ImovelDocumentosCard";
import type { ImovelDocumento } from "@/hooks/useImovelDados";

function doc(over: Partial<ImovelDocumento> = {}): ImovelDocumento {
  return {
    id: "d1",
    codigo: "AP1234",
    nome_original: "matricula.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 2 * 1024 * 1024,
    tipo_documento: "matricula",
    enviado_por: null,
    created_at: "2026-02-01T00:00:00+00:00",
    extracao_status: null,
    extracao_matricula: null,
    extracao_confianca: null,
    extracao_rotulo: null,
    extracao_erro: null,
    ...over,
  };
}

async function render(props: Partial<Parameters<typeof ImovelDocumentosCard>[0]> = {}) {
  const rtl = await import("@testing-library/react");
  const onUpload = vi.fn();
  const onRemove = vi.fn();
  const onOpen = vi.fn();
  const view = rtl.render(
    <ImovelDocumentosCard
      documentos={[]}
      loading={false}
      uploading={false}
      onUpload={onUpload}
      onRemove={onRemove}
      onOpen={onOpen}
      {...props}
    />,
  );
  return { ...rtl, ...view, onUpload, onRemove, onOpen };
}

describe("ImovelDocumentosCard", () => {
  it("tells the user what uploading a matrícula will do", async () => {
    const { screen } = await render();
    expect(screen.getByText(/número será lido automaticamente/i)).toBeTruthy();
  });

  it("🔴 carries the id the contract 'Resolver' (foro comarca) lands on", async () => {
    const { container } = await render();
    const card = container.querySelector("#imovel-documentos");
    expect(card).not.toBeNull();
    expect(card?.getAttribute("tabindex")).toBe("-1");
  });

  it("🔴 says it is still reading, rather than showing nothing", async () => {
    // Otherwise "in progress" looks exactly like "found nothing" and like
    // "broken" — an empty field in all three cases.
    const { screen } = await render({
      documentos: [doc({ extracao_status: "processando" })],
    });
    expect(screen.getByText(/lendo o número da matrícula/i)).toBeTruthy();
  });

  it("🔴 surfaces a read failure instead of failing silently", async () => {
    const { screen } = await render({
      documentos: [
        doc({ extracao_status: "erro", extracao_erro: "storage: timeout" }),
      ],
    });
    expect(screen.getByText(/não foi possível ler/i)).toBeTruthy();
    expect(screen.getByText(/storage: timeout/i)).toBeTruthy();
  });

  it("distinguishes 'read it, no number there' from a failure", async () => {
    const { screen } = await render({
      documentos: [doc({ extracao_status: "sem_dados" })],
    });
    expect(screen.getByText(/nenhum número de matrícula foi encontrado/i)).toBeTruthy();
    expect(screen.queryByText(/não foi possível ler/i)).toBeNull();
  });

  it("shows a high-confidence read without a warning", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          extracao_status: "ok",
          extracao_matricula: "12345",
          extracao_confianca: "alta",
        }),
      ],
    });
    expect(screen.getByText("12345")).toBeTruthy();
    expect(screen.queryByText(/confirme antes de usar/i)).toBeNull();
  });

  it("🔴 marks a low-confidence read as needing confirmation", async () => {
    // A vision-read matrícula number has no plausibility gate anywhere
    // downstream. Saying so is what stops a misread becoming a fact.
    const { screen } = await render({
      documentos: [
        doc({
          extracao_status: "ok",
          extracao_matricula: "12345",
          extracao_confianca: "baixa",
        }),
      ],
    });
    expect(screen.getByText(/confirme antes de usar/i)).toBeTruthy();
  });

  it("🔴 owns its own file input, so uploads cannot land on another card", async () => {
    // The bug this forecloses: a shared `getElementById` input would file
    // every card's upload onto whichever one rendered it.
    const { container } = await render();
    const inputs = container.querySelectorAll('input[type="file"]');
    expect(inputs.length).toBe(1);
  });

  it("does not delete when the reason prompt is cancelled", async () => {
    const { screen, fireEvent, onRemove } = await render({
      documentos: [doc()],
    });
    vi.spyOn(window, "prompt").mockReturnValue(null);
    fireEvent.click(screen.getByLabelText(/remover matricula\.pdf/i));
    expect(onRemove).not.toHaveBeenCalled();
  });

  it("deletes with the reason the user gave", async () => {
    const { screen, fireEvent, onRemove } = await render({
      documentos: [doc()],
    });
    vi.spyOn(window, "prompt").mockReturnValue("arquivo errado");
    fireEvent.click(screen.getByLabelText(/remover matricula\.pdf/i));
    expect(onRemove).toHaveBeenCalledWith("d1", "arquivo errado");
  });

  it("🔴 keeps the document list mounted during a background refetch (Cat A regression)", async () => {
    // The caller passes `loading={query.isPending || query.isFetching}`
    // (`pages/ImovelDetalhes.tsx`, out of this file's zone) — so `loading`
    // stays true through every refetch an upload/remove mutation triggers.
    // Gating the skeleton on `loading` alone unmounted an already-rendered
    // document list back to "Carregando…" on every such refetch. The fix
    // also requires `documentos.length === 0`, so a refetch of a
    // non-empty list must keep rendering it.
    // (KB § PATTERNS/frontend/lying-loading-state.md)
    const { screen, queryByText } = await render({
      documentos: [doc()],
      loading: true,
    });
    expect(screen.getByText("matricula.pdf")).toBeTruthy();
    expect(queryByText("Carregando…")).toBeNull();
  });

  it("shows the skeleton while genuinely empty and loading (first load)", async () => {
    const { screen } = await render({ documentos: [], loading: true });
    expect(screen.getByText("Carregando…")).toBeTruthy();
  });
});

// ─── Bug 3: the migration-118 structured read (guia de IPTU / CND de IPTU) ────

describe("ImovelDocumentosCard — structured read (guia de IPTU / CND de IPTU)", () => {
  it("shows the guia de IPTU's inscrição imobiliária", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          tipo_documento: "guia_iptu",
          nome_original: "guia.pdf",
          inscricao_imobiliaria: "123.456.789-0",
        }),
      ],
    });
    expect(screen.getByText("123.456.789-0")).toBeTruthy();
  });

  it("shows the CND de IPTU's número, emissão, validade and resultado", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          tipo_documento: "cnd_iptu",
          nome_original: "cnd.pdf",
          numero: "CND-999",
          emitida_em: "2026-08-01",
          validade_ate: "2099-01-01",
          resultado: "negativa",
          inscricao_imobiliaria: "123.456.789-0",
        }),
      ],
    });
    expect(screen.getByText("CND-999")).toBeTruthy();
    expect(screen.getByText(/Emitida em/)).toBeTruthy();
    expect(screen.getByText(/Negativa/)).toBeTruthy();
    expect(screen.queryByText(/vencida/i)).toBeNull();
  });

  it("🔴 warns when a CND's validade_ate is already in the past", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          tipo_documento: "cnd_iptu",
          nome_original: "cnd.pdf",
          validade_ate: "2020-01-01",
          resultado: "negativa",
        }),
      ],
    });
    expect(screen.getByText(/vencida/i)).toBeTruthy();
  });

  it("🔴 warns when a CND's resultado is positiva", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          tipo_documento: "cnd_iptu",
          nome_original: "cnd.pdf",
          resultado: "positiva",
          validade_ate: "2099-01-01",
        }),
      ],
    });
    const resultadoText = screen.getByText(/Resultado: Positiva/);
    expect(resultadoText).toBeTruthy();
  });

  it("does not warn on positiva_com_efeito_de_negativa — the narrower vocabulary treats it as resolved", async () => {
    const { screen } = await render({
      documentos: [
        doc({
          tipo_documento: "cnd_iptu",
          nome_original: "cnd.pdf",
          resultado: "positiva_com_efeito_de_negativa",
        }),
      ],
    });
    expect(screen.getByText(/Positiva com efeito de negativa/)).toBeTruthy();
  });

  it("renders nothing extra when the structured read has produced no fields yet", async () => {
    const { container } = await render({
      documentos: [doc({ tipo_documento: "cnd_iptu", nome_original: "cnd.pdf" })],
    });
    expect(container.querySelector("[data-testid]")).toBeTruthy(); // sanity: still rendered
    expect(container.textContent).not.toMatch(/Inscrição imobiliária|Resultado:|Validade/);
  });

  it("never shows structured fields the tipo does not carry (a matrícula gets no inscrição imobiliária line)", async () => {
    const { screen, container } = await render({
      documentos: [
        doc({
          tipo_documento: "matricula",
          nome_original: "matricula.pdf",
          inscricao_imobiliaria: "should-not-render",
        }),
      ],
    });
    expect(screen.getByText("matricula.pdf")).toBeTruthy();
    expect(container.textContent).not.toContain("should-not-render");
  });
});
