/**
 * FinanciamentoPanel — the screen answers "what is still missing".
 *
 * The assertions worth having are about the SLOTS. A plain uploads list shows
 * what has arrived and says nothing about what has not, which is the one
 * question this screen exists to answer.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import FinanciamentoPanel from "./FinanciamentoPanel";
import type { Financiamento, FinanciamentoDocumento } from "@/hooks/useFinanciamento";

const TIPOS_ESCRITURA = [
  "certidao_casamento",
  "escritura_pacto",
  "registro_pacto",
  "comprovante_residencia",
];
const TIPOS_FGTS = [
  "imposto_renda_com_recibo",
  "carteira_trabalho",
  "extratos_fgts",
  "comprovante_residencia_1ano",
];

function doc(tipo: string, over: Partial<FinanciamentoDocumento> = {}): FinanciamentoDocumento {
  return {
    id: `d-${tipo}`,
    nome_original: `${tipo}.pdf`,
    mime_type: "application/pdf",
    tamanho_bytes: 1024 * 1024,
    tipo_documento: tipo,
    grupo: TIPOS_FGTS.includes(tipo) ? "fgts" : "escritura",
    categoria_lgpd: "financeiro",
    retencao_ate: null,
    enviado_por: null,
    created_at: "2026-02-01T00:00:00+00:00",
    ...over,
  };
}

function financiamento(over: Partial<Financiamento> = {}): Financiamento {
  return {
    atendimento_id: "a1",
    situacao: "pendente",
    situacao_em: null,
    situacao_motivo: null,
    fgts: false,
    observacoes: null,
    // Migration 100 — no agent chosen is the ordinary state of a deal that
    // has not reached a bank yet, so that is what the fixture defaults to.
    agente_financeiro_id: null,
    agente_financeiro: null,
    numero_proposta: null,
    created_at: null,
    updated_at: null,
    existe: false,
    tipos_escritura: TIPOS_ESCRITURA,
    tipos_fgts: TIPOS_FGTS,
    documentos: [],
    ...over,
  };
}

async function render(over: Partial<Financiamento> | undefined = {}, props = {}) {
  const rtl = await import("@testing-library/react");
  const onSave = vi.fn();
  const onUpload = vi.fn();
  const onRemove = vi.fn();
  const onOpen = vi.fn();
  const view = rtl.render(
    <FinanciamentoPanel
      financiamento={over === undefined ? undefined : financiamento(over)}
      loading={false}
      saving={false}
      uploading={false}
      onSave={onSave}
      onUpload={onUpload}
      onRemove={onRemove}
      onOpen={onOpen}
      {...props}
    />,
  );
  return { ...rtl, ...view, onSave, onUpload, onRemove, onOpen };
}

describe("FinanciamentoPanel", () => {
  it("🔴 renders a slot for every required document, filled or not", async () => {
    const { screen } = await render();
    for (const t of TIPOS_ESCRITURA) {
      expect(screen.getByTestId(`financiamento-input-${t}`)).toBeTruthy();
    }
    // Four escritura slots, all empty. Matched exactly — the summary line
    // below also contains "não enviado", so an unanchored count sees five.
    expect(screen.getAllByText("Não enviado").length).toBe(4);
  });

  it("hides the FGTS section until FGTS is in play", async () => {
    const { screen, queryByTestId } = await render({ fgts: false });
    expect(queryByTestId("financiamento-input-carteira_trabalho")).toBeNull();
    expect(screen.queryByText("FGTS")).toBeNull();
  });

  it("shows the FGTS documents once FGTS is on", async () => {
    const { screen } = await render({ fgts: true });
    expect(screen.getByTestId("financiamento-input-carteira_trabalho")).toBeTruthy();
    expect(screen.getByTestId("financiamento-input-extratos_fgts")).toBeTruthy();
  });

  it("counts only the documents that are actually required right now", async () => {
    // FGTS off → the four FGTS types are not outstanding, they are irrelevant.
    const { screen } = await render({
      fgts: false,
      documentos: [doc("certidao_casamento")],
    });
    expect(screen.getByTestId("financiamento-faltando").textContent).toMatch(/^3 /);
  });

  it("counts the FGTS set once it becomes required", async () => {
    const { screen } = await render({
      fgts: true,
      documentos: [doc("certidao_casamento")],
    });
    expect(screen.getByTestId("financiamento-faltando").textContent).toMatch(/^7 /);
  });

  it("marks a filled slot and offers to open it", async () => {
    const { screen, fireEvent, onOpen } = await render({
      documentos: [doc("certidao_casamento")],
    });
    fireEvent.click(screen.getByText(/certidao_casamento\.pdf/));
    expect(onOpen).toHaveBeenCalledWith("d-certidao_casamento");
  });

  it("🔴 every slot owns its own file input", async () => {
    // A shared input would file every slot's upload onto one type.
    const { container } = await render({ fgts: true });
    const inputs = container.querySelectorAll('input[type="file"]');
    expect(inputs.length).toBe(TIPOS_ESCRITURA.length + TIPOS_FGTS.length);
  });

  it("does not delete when the reason prompt is cancelled", async () => {
    const { screen, fireEvent, onRemove } = await render({
      documentos: [doc("certidao_casamento")],
    });
    vi.spyOn(window, "prompt").mockReturnValue("");
    fireEvent.click(screen.getByLabelText(/remover certidão de casamento/i));
    expect(onRemove).not.toHaveBeenCalled();
  });

  it("records the three situações and reports the current one", async () => {
    const { screen, fireEvent, onSave } = await render({ situacao: "aprovado" });
    expect(
      screen.getByTestId("financiamento-situacao-aprovado").getAttribute("aria-pressed"),
    ).toBe("true");
    fireEvent.click(screen.getByTestId("financiamento-situacao-recusado"));
    expect(onSave).toHaveBeenCalledWith({ situacao: "recusado" });
  });

  it("🔴 pendente is presented as its own state, not as a refusal", async () => {
    const { screen } = await render({ situacao: "pendente" });
    expect(
      screen.getByTestId("financiamento-situacao-pendente").getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByTestId("financiamento-situacao-recusado").getAttribute("aria-pressed"),
    ).toBe("false");
  });
});
