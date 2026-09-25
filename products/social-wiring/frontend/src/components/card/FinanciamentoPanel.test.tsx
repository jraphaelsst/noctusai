/**
 * FinanciamentoPanel — the screen answers "what is still missing", plus
 * (migration 171, `sw-negociacao-extracao-contract.md` §F) the extraction
 * chrome (status / aviso / confirmar / descartar / reler) once a slot's
 * document carries a non-null `extracao_status`.
 *
 * Slots are now built on the shared `DocumentoTipoSlot` — the third
 * consumer (contract §F) — so their DOM/testid shape is that component's,
 * not a bespoke one.
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
  // Migration 171 (contract §A) — guia_itbi/comprovante_itbi join the
  // EXISTING "Escritura" group server-side.
  "guia_itbi",
  "comprovante_itbi",
];
const TIPOS_FGTS = [
  "imposto_renda_com_recibo",
  "carteira_trabalho",
  "extratos_fgts",
  "comprovante_residencia_1ano",
];
const TIPOS_FINANCIAMENTO_DOCS = ["proposta_financiamento", "contrato_financiamento"];

function doc(tipo: string, over: Partial<FinanciamentoDocumento> = {}): FinanciamentoDocumento {
  return {
    id: `d-${tipo}`,
    nome_original: `${tipo}.pdf`,
    mime_type: "application/pdf",
    tamanho_bytes: 1024 * 1024,
    tipo_documento: tipo,
    grupo: TIPOS_FGTS.includes(tipo)
      ? "fgts"
      : TIPOS_FINANCIAMENTO_DOCS.includes(tipo)
        ? "financiamento"
        : "escritura",
    categoria_lgpd: "financeiro",
    retencao_ate: null,
    enviado_por: null,
    created_at: "2026-02-01T00:00:00+00:00",
    extracao_status: null,
    extracao_erro: null,
    extracao_dados: null,
    extracao_aviso: null,
    extracao_descartada_em: null,
    ...over,
  };
}

function financiamento(over: Partial<Financiamento> = {}): Financiamento {
  return {
    atendimento_id: "a1",
    situacao: "pendente",
    situacao_em: null,
    situacao_motivo: null,
    situacao_origem: null,
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
    tipos_financiamento_docs: TIPOS_FINANCIAMENTO_DOCS,
    tem_parcela_financiamento: false,
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
  const onExtrair = vi.fn();
  const onConfirmarExtracao = vi.fn();
  const onDescartarExtracao = vi.fn();
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
      onExtrair={onExtrair}
      onConfirmarExtracao={onConfirmarExtracao}
      onDescartarExtracao={onDescartarExtracao}
      {...props}
    />,
  );
  return {
    ...rtl,
    ...view,
    onSave,
    onUpload,
    onRemove,
    onOpen,
    onExtrair,
    onConfirmarExtracao,
    onDescartarExtracao,
  };
}

describe("FinanciamentoPanel", () => {
  it("🔴 renders a slot for every required document, filled or not", async () => {
    const { screen } = await render();
    for (const t of TIPOS_ESCRITURA) {
      expect(screen.getByTestId(`financiamento-slot-${t}-arquivo-input`)).toBeTruthy();
    }
    // Four escritura slots, all empty (the shared slot's empty marker is "—").
    expect(screen.getAllByTestId(/^financiamento-slot-.*-valor$/).length).toBeGreaterThanOrEqual(4);
  });

  it("hides the FGTS section until FGTS is in play", async () => {
    const { queryByTestId, screen } = await render({ fgts: false });
    expect(queryByTestId("financiamento-slot-carteira_trabalho-arquivo-input")).toBeNull();
    expect(screen.queryByText("FGTS")).toBeNull();
  });

  it("shows the FGTS documents once FGTS is on", async () => {
    const { screen } = await render({ fgts: true });
    expect(screen.getByTestId("financiamento-slot-carteira_trabalho-arquivo-input")).toBeTruthy();
    expect(screen.getByTestId("financiamento-slot-extratos_fgts-arquivo-input")).toBeTruthy();
  });

  it("hides the Financiamento doc section until the deal has a financiamento parcela or the financiamento row exists", async () => {
    const { queryByTestId } = await render({
      tem_parcela_financiamento: false,
      existe: false,
    });
    expect(
      queryByTestId("financiamento-slot-contrato_financiamento-arquivo-input"),
    ).toBeNull();
  });

  it("shows the Financiamento doc section once the deal has a financiamento parcela", async () => {
    const { screen } = await render({ tem_parcela_financiamento: true });
    expect(screen.getByTestId("financiamento-slot-contrato_financiamento-arquivo-input")).toBeTruthy();
    expect(screen.getByTestId("financiamento-slot-proposta_financiamento-arquivo-input")).toBeTruthy();
  });

  it("counts only the documents that are actually required right now", async () => {
    // FGTS off, no financiamento parcela → neither set is outstanding.
    const { screen } = await render({
      fgts: false,
      tem_parcela_financiamento: false,
      documentos: [doc("certidao_casamento")],
    });
    expect(screen.getByTestId("financiamento-faltando").textContent).toMatch(
      new RegExp(`^${TIPOS_ESCRITURA.length - 1} `),
    );
  });

  it("marks a filled slot and offers to open it", async () => {
    // `DocumentoTipoSlot` opens a document through its OWN "Visualizar"
    // action, not by clicking the filename text (unlike the retired local
    // `Slot`).
    const { screen, fireEvent, onOpen } = await render({
      documentos: [doc("certidao_casamento")],
    });
    fireEvent.click(screen.getByTestId("financiamento-slot-certidao_casamento-visualizar"));
    expect(onOpen).toHaveBeenCalledWith("d-certidao_casamento");
  });

  it("🔴 every slot owns its own file input", async () => {
    // A shared input would file every slot's upload onto one type.
    const { container } = await render({ fgts: true, tem_parcela_financiamento: true });
    const inputs = container.querySelectorAll('input[type="file"]');
    expect(inputs.length).toBe(
      TIPOS_ESCRITURA.length + TIPOS_FGTS.length + TIPOS_FINANCIAMENTO_DOCS.length,
    );
  });

  it("removes a document straight from the shared slot's own descartar action", async () => {
    // `DocumentoTipoSlot` (the shared component this panel now consumes,
    // contract §F) has no reason PROMPT of its own — it calls `onRemover`
    // with a fixed "Descartado para reenvio" reason directly. The
    // `window.prompt` "why is this being removed" ritual belonged to the
    // retired local `Slot` only.
    const { screen, fireEvent, onRemove } = await render({
      documentos: [doc("certidao_casamento")],
    });
    fireEvent.click(screen.getByTestId("financiamento-slot-certidao_casamento-descartar"));
    expect(onRemove).toHaveBeenCalledWith(
      "d-certidao_casamento",
      expect.stringContaining("Certidão de casamento"),
    );
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

  describe("H6 — situação provenance", () => {
    it("badges a situação the extraction auto-set from a signed contract", async () => {
      const { screen } = await render({
        situacao: "aprovado",
        situacao_em: "2026-09-20T00:00:00+00:00",
        situacao_origem: "extraido",
      });
      expect(screen.getByTestId("financiamento-situacao-origem-extraido")).toBeTruthy();
    });

    it("no badge for a situação a person chose by hand", async () => {
      const { queryByTestId } = await render({
        situacao: "aprovado",
        situacao_em: "2026-09-20T00:00:00+00:00",
        situacao_origem: "manual",
      });
      expect(queryByTestId("financiamento-situacao-origem-extraido")).toBeNull();
    });
  });

  describe("H7 — agente financeiro auto-criado", () => {
    it("shows that the registry row was created by the extraction, not typed", async () => {
      const { screen } = await render({
        agente_financeiro_id: "ag-1",
        agente_financeiro: {
          id: "ag-1",
          nome: "Itaú",
          codigo_banco: "341",
          agencia: null,
          ativo: true,
          origem: "auto_criado",
        },
      });
      expect(screen.getByTestId("financiamento-agente-auto-criado")).toBeTruthy();
    });
  });

  describe("extraction chrome (contract §F)", () => {
    it("shows a spinner while a document's reading is in flight", async () => {
      const { screen } = await render({
        documentos: [doc("guia_itbi", { extracao_status: "pendente" })],
      });
      expect(screen.getByTestId("financiamento-slot-guia_itbi-processando")).toBeTruthy();
    });

    it("stops the spinner once the status turns terminal", async () => {
      const { queryByTestId } = await render({
        documentos: [doc("guia_itbi", { extracao_status: "ok" })],
      });
      expect(queryByTestId("financiamento-slot-guia_itbi-processando")).toBeNull();
    });

    it("shows the error + a reler action on a failed read", async () => {
      const { screen, fireEvent, onExtrair } = await render({
        documentos: [
          doc("guia_itbi", { extracao_status: "erro", extracao_erro: "Falha ao ler." }),
        ],
      });
      expect(screen.getByText("Falha ao ler.")).toBeTruthy();
      fireEvent.click(screen.getByTestId("financiamento-slot-guia_itbi-reler"));
      expect(onExtrair).toHaveBeenCalledWith("d-guia_itbi");
    });

    it("offers confirmar/descartar only while a reading awaits a decision", async () => {
      const { screen, fireEvent, onConfirmarExtracao, onDescartarExtracao } = await render({
        documentos: [doc("guia_itbi", { extracao_status: "ok" })],
      });
      fireEvent.click(screen.getByTestId("financiamento-slot-guia_itbi-confirmar"));
      expect(onConfirmarExtracao).toHaveBeenCalledWith("d-guia_itbi");
      fireEvent.click(screen.getByTestId("financiamento-slot-guia_itbi-descartar-leitura"));
      expect(onDescartarExtracao).toHaveBeenCalledWith("d-guia_itbi");
    });

    it("an already-discarded reading no longer asks for a decision", async () => {
      const { queryByTestId } = await render({
        documentos: [
          doc("guia_itbi", {
            extracao_status: "ok",
            extracao_descartada_em: "2026-09-25T00:00:00+00:00",
          }),
        ],
      });
      expect(queryByTestId("financiamento-slot-guia_itbi-decisao")).toBeNull();
    });

    it("renders the pt-BR aviso when the reading carries one", async () => {
      const { screen } = await render({
        tem_parcela_financiamento: true,
        documentos: [
          doc("contrato_financiamento", {
            extracao_status: "ok",
            extracao_aviso: "quadro_resumo_soma_divergente",
          }),
        ],
      });
      expect(
        screen.getByTestId("financiamento-slot-contrato_financiamento-aviso").textContent,
      ).toMatch(/Quadro Resumo/);
    });

    it("a document with no registered extractor shows no extraction chrome at all", async () => {
      const { queryByTestId } = await render({
        documentos: [doc("certidao_casamento", { extracao_status: null })],
      });
      expect(queryByTestId("financiamento-slot-certidao_casamento-processando")).toBeNull();
      expect(queryByTestId("financiamento-slot-certidao_casamento-decisao")).toBeNull();
    });
  });
});
