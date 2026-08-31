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
