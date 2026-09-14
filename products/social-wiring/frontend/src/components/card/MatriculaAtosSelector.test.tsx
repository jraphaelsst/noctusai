/**
 * MatriculaAtosSelector — select / reorder / save, and the load-bearing
 * assertion for the whole feature: the literal matrícula text renders
 * byte-for-byte, typos and double spaces included, never trimmed or
 * normalised (`white-space: pre-wrap`, USER DECISION per the F2 brief).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import MatriculaAtosSelector from "./MatriculaAtosSelector";
import type { MatriculaAto } from "@/hooks/useMatriculaEstrutura";
import type { MatriculaExtracaoOpcao } from "./MatriculaAtosSelector";

function ato(over: Partial<MatriculaAto> = {}): MatriculaAto {
  return {
    id: "ato-1",
    ordem: 0,
    kind: "R",
    numero: 1,
    char_inicio: 0,
    char_fim: 10,
    header_inicio: null,
    header_fim: null,
    rotulo: "R-1 Compra e venda",
    texto: "R-1 Compra  e venda a Joao da Silva, CPF 000.000.000-00, contrate.",
    ...over,
  };
}

function extracao(over: Partial<MatriculaExtracaoOpcao> = {}): MatriculaExtracaoOpcao {
  return {
    id: "extracao-1",
    nome_arquivo: "matricula-12345.pdf",
    status: "concluida",
    created_at: "2026-02-01T00:00:00Z",
    ...over,
  };
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    contratoId: "contrato-1",
    codigo: null,
    extracoes: [extracao()],
    extracoesLoading: false,
    extracoesError: false,
    buscaExtracao: "",
    onBuscaExtracaoChange: vi.fn(),
    extracaoSelecionadaId: null,
    onSelecionarExtracao: vi.fn(),
    atos: [],
    atosLoading: false,
    atosError: false,
    selecao: undefined,
    selecaoExtracaoId: null,
    selecaoLoading: false,
    selecaoError: false,
    selecionadoPor: null,
    selecionadoEm: null,
    saving: false,
    onSave: vi.fn(),
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const props = baseProps(over);
  const view = rtl.render(
    <MatriculaAtosSelector {...(props as unknown as Parameters<typeof MatriculaAtosSelector>[0])} />,
  );
  return { ...view, ...rtl, props };
}

describe("MatriculaAtosSelector — extraction picker", () => {
  it("prompts to select a matrícula before showing any act", async () => {
    const { screen } = await render();
    expect(screen.getByTestId("matricula-atos-vazio")).toBeTruthy();
  });

  it("picking a concluída extraction calls back with its id", async () => {
    const onSelecionarExtracao = vi.fn();
    const { screen, fireEvent } = await render({ onSelecionarExtracao });
    fireEvent.click(screen.getByTestId("matricula-atos-extracao-extracao-1"));
    expect(onSelecionarExtracao).toHaveBeenCalledWith("extracao-1");
  });

  it("🔴 a non-concluída extraction cannot be picked", async () => {
    const onSelecionarExtracao = vi.fn();
    const { screen, fireEvent } = await render({
      extracoes: [extracao({ id: "extracao-2", status: "processando" })],
      onSelecionarExtracao,
    });
    const row = screen.getByTestId("matricula-atos-extracao-extracao-2") as HTMLButtonElement;
    expect(row.disabled).toBe(true);
    fireEvent.click(row);
    expect(onSelecionarExtracao).not.toHaveBeenCalled();
  });

  it("shows the error branch when the extraction list fails to load", async () => {
    const { screen } = await render({ extracoesError: true, extracoes: [] });
    expect(screen.getByTestId("matricula-atos-extracoes-erro")).toBeTruthy();
  });
});

describe("MatriculaAtosSelector — literal text, byte for byte", () => {
  it("🔴 renders double spaces and a typo unchanged in the expanded act body", async () => {
    const umAto = ato({
      texto: "R-1  Compra  e venda a Joao  da Silva,  CPF 000.000.000-00,  contrate.",
    });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [umAto],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-toggle-ato-1"));
    const corpo = screen.getByTestId("matricula-ato-texto-ato-1");
    expect(corpo.textContent).toBe(umAto.texto);
    // `white-space: pre-wrap` is what makes the double spaces actually
    // VISIBLE rather than collapsed by the browser — assert the class, not
    // just the (already-preserved-in-the-DOM-text) string.
    expect(corpo.className).toContain("whitespace-pre-wrap");
  });

  it("🔴 the live preview concatenates selected acts' literal texto with NO separator", async () => {
    const a1 = ato({ id: "a1", ordem: 0, texto: "Abertura.\n" });
    const a2 = ato({ id: "a2", ordem: 1, texto: "R-1  Compra e venda,  typo incluido." });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1, a2],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a2"));
    const preview = screen.getByTestId("matricula-atos-preview");
    expect(preview.textContent).toBe(a1.texto + a2.texto);
  });
});

describe("MatriculaAtosSelector — select / reorder / save", () => {
  it("checking an act appends it to the ordered selection", async () => {
    const a1 = ato({ id: "a1" });
    const a2 = ato({ id: "a2", numero: 2 });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1, a2],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a2"));
    const selecionados = screen.getAllByTestId(/^matricula-ato-selecionado-/);
    expect(selecionados.map((el) => el.getAttribute("data-testid"))).toEqual([
      "matricula-ato-selecionado-a1",
      "matricula-ato-selecionado-a2",
    ]);
  });

  it("🔴 moving the second act up reorders the selection AND the preview", async () => {
    const a1 = ato({ id: "a1", texto: "PRIMEIRO." });
    const a2 = ato({ id: "a2", numero: 2, texto: "SEGUNDO." });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1, a2],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a2"));
    fireEvent.click(screen.getByTestId("matricula-ato-subir-a2"));

    const selecionados = screen.getAllByTestId(/^matricula-ato-selecionado-/);
    expect(selecionados.map((el) => el.getAttribute("data-testid"))).toEqual([
      "matricula-ato-selecionado-a2",
      "matricula-ato-selecionado-a1",
    ]);
    expect(screen.getByTestId("matricula-atos-preview").textContent).toBe("SEGUNDO.PRIMEIRO.");
  });

  it("unchecking a selected act removes it from the order", async () => {
    const a1 = ato({ id: "a1" });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    expect(screen.queryByTestId("matricula-atos-selecao-vazia")).toBeNull();
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    expect(screen.getByTestId("matricula-atos-selecao-vazia")).toBeTruthy();
  });

  it("removing via the ✕ on the ordered list also unchecks it", async () => {
    const a1 = ato({ id: "a1" });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1],
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    fireEvent.click(screen.getByTestId("matricula-ato-remover-a1"));
    expect(screen.getByTestId("matricula-atos-selecao-vazia")).toBeTruthy();
  });

  it("🔴 saving sends the current extraction id and the draft order", async () => {
    const onSave = vi.fn();
    const a1 = ato({ id: "a1" });
    const a2 = ato({ id: "a2", numero: 2 });
    const { screen, fireEvent } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1, a2],
      onSave,
    });
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a2"));
    fireEvent.click(screen.getByTestId("matricula-ato-checkbox-a1"));
    fireEvent.click(screen.getByTestId("matricula-atos-salvar"));
    expect(onSave).toHaveBeenCalledWith({ extracaoId: "extracao-1", atoIds: ["a2", "a1"] });
  });

  it("seeds the draft from the persisted selection when browsing the same extraction", async () => {
    const a1 = ato({ id: "a1" });
    const a2 = ato({ id: "a2", numero: 2 });
    const { screen } = await render({
      extracaoSelecionadaId: "extracao-1",
      atos: [a1, a2],
      selecaoExtracaoId: "extracao-1",
      selecao: [
        { ato_id: "a2", ordem: 1, kind: "R", numero: 2, char_inicio: 0, char_fim: 1, texto: a2.texto },
        { ato_id: "a1", ordem: 2, kind: "R", numero: 1, char_inicio: 0, char_fim: 1, texto: a1.texto },
      ],
    });
    const selecionados = screen.getAllByTestId(/^matricula-ato-selecionado-/);
    expect(selecionados.map((el) => el.getAttribute("data-testid"))).toEqual([
      "matricula-ato-selecionado-a2",
      "matricula-ato-selecionado-a1",
    ]);
  });

  it("starts empty when browsing a DIFFERENT extraction than the persisted one", async () => {
    const a1 = ato({ id: "a1" });
    const { screen } = await render({
      extracaoSelecionadaId: "extracao-2",
      atos: [a1],
      selecaoExtracaoId: "extracao-1",
      selecao: [
        { ato_id: "a9", ordem: 1, kind: "R", numero: 9, char_inicio: 0, char_fim: 1, texto: "x" },
      ],
    });
    expect(screen.getByTestId("matricula-atos-selecao-vazia")).toBeTruthy();
  });

  it("shows who selected it and when, once persisted", async () => {
    const { screen } = await render({
      extracaoSelecionadaId: "extracao-1",
      selecaoExtracaoId: "extracao-1",
      selecionadoPor: { id: "u1", nome: "Ana Corretora" },
      selecionadoEm: "2026-02-01T10:00:00Z",
    });
    expect(screen.getByText(/Selecionado por Ana Corretora/)).toBeTruthy();
  });

  it("shows the acts error branch — never a silent empty catalog", async () => {
    const { screen } = await render({ extracaoSelecionadaId: "extracao-1", atosError: true });
    expect(screen.getByTestId("matricula-atos-erro")).toBeTruthy();
  });
});
