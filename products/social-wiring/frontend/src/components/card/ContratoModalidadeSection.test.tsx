/**
 * ContratoModalidadeSection — migration 157's Digital/Física gate.
 *
 * Pins: the toggle is a real radiogroup (≥ 40px targets via `min-h-10`);
 * "Baixar para impressão" is only enabled for a version GENERATED as
 * física (never a digital rendering that would print the digital clause);
 * "Marcar como assinado" confirms with or without a scan, refuses a non-PDF
 * scan in-form, and on an already-signed contract becomes "Anexar" with the
 * scan required.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContratoModalidadeSection } from "./ContratoModalidadeSection";
import type { ContratoOut, VersaoOut } from "@/hooks/useContratos";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

function versao(over: Partial<VersaoOut> = {}): VersaoOut {
  return {
    id: "v1",
    nome_original: "contrato-gerado-v1.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 1024,
    tipo_documento: "contrato",
    enviado_por: null,
    created_at: "2026-09-20T00:00:00+00:00",
    numero: 1,
    rotulo: null,
    origem: "gerado",
    docx_disponivel: true,
    modalidade_assinatura: "fisica",
    ...over,
  };
}

function contrato(over: Partial<ContratoOut> = {}): ContratoOut {
  const v = over.versao_atual !== undefined ? over.versao_atual : versao();
  return {
    id: "c1",
    atendimento_id: "a1",
    titulo: "Promessa de Venda e Compra",
    modelo: "compra_venda",
    status: "em_revisao",
    status_em: null,
    status_por: null,
    origem: "gerado",
    created_at: "2026-09-20T00:00:00+00:00",
    updated_at: null,
    versao_atual: v,
    versoes: v ? [v] : [],
    assinatura_data: null,
    prazo_pendencias_dias: null,
    processo_legado: false,
    processo_legado_por: null,
    processo_legado_em: null,
    processo_legado_motivo: null,
    modalidade_assinatura: "fisica",
    ...over,
  };
}

async function render(over: Partial<Parameters<typeof ContratoModalidadeSection>[0]> = {}) {
  const rtl = await import("@testing-library/react");
  const props = {
    contrato: contrato(),
    envelopeVivo: false,
    onPatchModalidade: vi.fn(),
    onBaixarImpressao: vi.fn(),
    onMarcarAssinado: vi.fn(),
    digitalContent: <p data-testid="digital-content">enviar</p>,
    ...over,
  };
  const view = rtl.render(<ContratoModalidadeSection {...props} />);
  return { ...view, ...rtl, props };
}

describe("ContratoModalidadeSection", () => {
  it("renders an accessible two-option radiogroup with ≥40px targets", async () => {
    const { screen } = await render();
    const grupo = screen.getByRole("radiogroup");
    const opcoes = screen.getAllByRole("radio");
    expect(grupo).toBeTruthy();
    expect(opcoes.map((o) => o.textContent)).toEqual(["Digital", "Física"]);
    for (const o of opcoes) expect(o.className).toContain("min-h-10");
    expect(screen.getByTestId("contrato-modalidade-fisica-c1").getAttribute("aria-checked")).toBe("true");
  });

  it("digital renders the digital content and none of the física actions", async () => {
    const { screen } = await render({ contrato: contrato({ modalidade_assinatura: "digital" }) });
    expect(screen.getByTestId("digital-content")).toBeTruthy();
    expect(screen.queryByTestId("contrato-fisica-c1")).toBeNull();
  });

  it("física never renders the digital content", async () => {
    const { screen } = await render();
    expect(screen.queryByTestId("digital-content")).toBeNull();
    expect(screen.getByTestId("contrato-fisica-c1")).toBeTruthy();
  });

  it("🔴 'Baixar para impressão' downloads the física rendering", async () => {
    const onBaixarImpressao = vi.fn();
    const { screen, fireEvent } = await render({ onBaixarImpressao });
    fireEvent.click(screen.getByTestId("contrato-baixar-impressao-c1"));
    expect(onBaixarImpressao).toHaveBeenCalledWith("v1");
    expect(screen.queryByTestId("contrato-impressao-hint-c1")).toBeNull();
  });

  it("🔴 a version generated as DIGITAL is never offered for printing", async () => {
    const { screen } = await render({
      contrato: contrato({ versao_atual: versao({ modalidade_assinatura: "digital" }) }),
    });
    expect((screen.getByTestId("contrato-baixar-impressao-c1") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("contrato-impressao-hint-c1").textContent).toContain("Gere uma nova versão");
  });

  it("an uploaded version is never offered for printing either", async () => {
    const { screen } = await render({
      contrato: contrato({ versao_atual: versao({ origem: "upload", modalidade_assinatura: null }) }),
    });
    expect((screen.getByTestId("contrato-baixar-impressao-c1") as HTMLButtonElement).disabled).toBe(true);
  });

  it("'Marcar como assinado' confirms without a scan", async () => {
    const onMarcarAssinado = vi.fn();
    const { screen, fireEvent } = await render({ onMarcarAssinado });
    fireEvent.click(screen.getByTestId("contrato-marcar-assinado-c1"));
    const confirmar = screen.getByTestId("contrato-marcar-assinado-confirmar-c1") as HTMLButtonElement;
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);
    expect(onMarcarAssinado).toHaveBeenCalledWith(null);
  });

  it("'Marcar como assinado' sends the chosen PDF scan", async () => {
    const onMarcarAssinado = vi.fn();
    const { screen, fireEvent } = await render({ onMarcarAssinado });
    fireEvent.click(screen.getByTestId("contrato-marcar-assinado-c1"));
    const pdf = new File(["%PDF"], "assinado.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("contrato-assinado-arquivo-c1"), { target: { files: [pdf] } });
    fireEvent.click(screen.getByTestId("contrato-marcar-assinado-confirmar-c1"));
    expect(onMarcarAssinado).toHaveBeenCalledWith(pdf);
  });

  it("🔴 a non-PDF scan is refused in the form, before any request", async () => {
    const onMarcarAssinado = vi.fn();
    const { screen, fireEvent } = await render({ onMarcarAssinado });
    fireEvent.click(screen.getByTestId("contrato-marcar-assinado-c1"));
    const docx = new File(["PK"], "assinado.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    fireEvent.change(screen.getByTestId("contrato-assinado-arquivo-c1"), { target: { files: [docx] } });
    expect(screen.getByTestId("contrato-assinado-arquivo-erro-c1").textContent).toContain("PDF");
    expect(
      (screen.getByTestId("contrato-marcar-assinado-confirmar-c1") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(onMarcarAssinado).not.toHaveBeenCalled();
  });

  it("an already-signed contract offers 'Anexar' and requires the scan", async () => {
    const { screen, fireEvent } = await render({
      contrato: contrato({
        status: "assinado",
        status_em: "2026-09-21T12:00:00+00:00",
        status_por: { id: "u1", nome: "Ana Corretora" },
      }),
    });
    expect(screen.getByTestId("contrato-fisica-assinado-c1").textContent).toContain("Ana Corretora");
    fireEvent.click(screen.getByTestId("contrato-marcar-assinado-c1"));
    expect(
      (screen.getByTestId("contrato-marcar-assinado-confirmar-c1") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("🔴 'Física' is disabled under a live digital envelope", async () => {
    const onPatchModalidade = vi.fn();
    const { screen, fireEvent } = await render({
      contrato: contrato({ modalidade_assinatura: "digital" }),
      envelopeVivo: true,
      onPatchModalidade,
    });
    const fisica = screen.getByTestId("contrato-modalidade-fisica-c1") as HTMLButtonElement;
    expect(fisica.disabled).toBe(true);
    fireEvent.click(fisica);
    expect(onPatchModalidade).not.toHaveBeenCalled();
  });

  it("the toggle is read-only when no handler is wired", async () => {
    const { screen } = await render({ onPatchModalidade: undefined });
    expect((screen.getByTestId("contrato-modalidade-digital-c1") as HTMLButtonElement).disabled).toBe(true);
  });
});
