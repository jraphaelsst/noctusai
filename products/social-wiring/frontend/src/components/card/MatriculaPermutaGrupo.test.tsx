/**
 * MatriculaPermutaGrupo — selecting the acts of an EXCHANGED property's
 * matrícula.
 *
 * The load-bearing assertions: the group is scoped to ONE permuta ativo
 * (picking acts reports that ativo's draft, never the object's), the save is
 * refused until there is something to save, and the backend's imóvel-mismatch
 * 400 is shown verbatim — that message names the only thing the operator can
 * act on.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import MatriculaPermutaGrupo from "./MatriculaPermutaGrupo";
import type { MatriculaExtracaoOpcao } from "./MatriculaAtosSelector";
import type { MatriculaAto } from "@/hooks/useMatriculaEstrutura";

const ATIVO_ID = "ativo-1";

function ato(over: Partial<MatriculaAto> = {}): MatriculaAto {
  return {
    id: "ato-1",
    ordem: 1,
    kind: "R",
    numero: 1,
    char_inicio: 0,
    char_fim: 20,
    header_inicio: null,
    header_fim: null,
    rotulo: "R-1 Compra e venda",
    texto: "R-1  Compra e venda, com  espaços literais.",
    detalhes: null,
    ...over,
  };
}

function extracao(over: Partial<MatriculaExtracaoOpcao> = {}): MatriculaExtracaoOpcao {
  return {
    id: "extracao-7",
    nome_arquivo: "matricula-permuta.pdf",
    status: "concluida",
    created_at: "2026-02-01T00:00:00Z",
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onSelecionarExtracao = vi.fn();
  const onAtoIdsChange = vi.fn();
  const onSalvar = vi.fn();
  const props = {
    permutaAtivoId: ATIVO_ID,
    rotulo: "AP9001 · Apartamento · Centro, São Paulo",
    codigo: "AP9001",
    extracoes: [extracao()],
    extracoesLoading: false,
    extracoesError: false,
    extracaoSelecionadaId: null,
    onSelecionarExtracao,
    atos: [] as MatriculaAto[],
    atosLoading: false,
    atosError: false,
    atoIds: [] as string[],
    onAtoIdsChange,
    saving: false,
    onSalvar,
    ...over,
  };
  const view = rtl.render(
    <MatriculaPermutaGrupo {...(props as unknown as Parameters<typeof MatriculaPermutaGrupo>[0])} />,
  );
  return { ...rtl, ...view, onSelecionarExtracao, onAtoIdsChange, onSalvar };
}

describe("MatriculaPermutaGrupo", () => {
  it("names the property being quoted", async () => {
    const { getByTestId } = await render();
    const grupo = getByTestId(`matricula-permuta-${ATIVO_ID}`);
    expect(grupo.textContent).toContain("AP9001");
    expect(grupo.textContent).toContain("Apartamento");
  });

  it("picks this ativo's matrícula", async () => {
    const { getByTestId, fireEvent, onSelecionarExtracao } = await render();
    fireEvent.click(getByTestId(`matricula-permuta-extracao-${ATIVO_ID}-extracao-7`));
    expect(onSelecionarExtracao).toHaveBeenCalledWith("extracao-7");
  });

  it("does not offer a transcription that is still running", async () => {
    const { getByTestId } = await render({
      extracoes: [extracao({ status: "processando" })],
    });
    const botao = getByTestId(
      `matricula-permuta-extracao-${ATIVO_ID}-extracao-7`,
    ) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });

  it("🔴 reports the selection for THIS ativo", async () => {
    const { getByTestId, fireEvent, onAtoIdsChange } = await render({
      extracaoSelecionadaId: "extracao-7",
      atos: [ato()],
    });
    fireEvent.click(getByTestId(`matricula-permuta-ato-checkbox-${ATIVO_ID}-ato-1`));
    expect(onAtoIdsChange).toHaveBeenCalledWith(["ato-1"]);
  });

  it("deselects an act that was already picked", async () => {
    const { getByTestId, fireEvent, onAtoIdsChange } = await render({
      extracaoSelecionadaId: "extracao-7",
      atos: [ato()],
      atoIds: ["ato-1"],
    });
    fireEvent.click(getByTestId(`matricula-permuta-ato-checkbox-${ATIVO_ID}-ato-1`));
    expect(onAtoIdsChange).toHaveBeenCalledWith([]);
  });

  it("🔴 previews the LITERAL text, spaces and typos included", async () => {
    // Same USER DECISION as the object quote: acts are selected, never edited.
    const { getByTestId } = await render({
      extracaoSelecionadaId: "extracao-7",
      atos: [ato()],
      atoIds: ["ato-1"],
    });
    expect(getByTestId(`matricula-permuta-preview-${ATIVO_ID}`).textContent).toBe(
      "R-1  Compra e venda, com  espaços literais.",
    );
  });

  it("refuses to save an empty selection", async () => {
    const { getByTestId } = await render({ extracaoSelecionadaId: "extracao-7", atos: [ato()] });
    expect(
      (getByTestId(`matricula-permuta-salvar-${ATIVO_ID}`) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("saves once there is a matrícula and at least one act", async () => {
    const { getByTestId, fireEvent, onSalvar } = await render({
      extracaoSelecionadaId: "extracao-7",
      atos: [ato()],
      atoIds: ["ato-1"],
    });
    fireEvent.click(getByTestId(`matricula-permuta-salvar-${ATIVO_ID}`));
    expect(onSalvar).toHaveBeenCalled();
  });

  it("🔴 shows the backend's imóvel-mismatch message verbatim", async () => {
    const { getByTestId } = await render({
      errorMessage:
        "A matrícula selecionada para a permuta pertence a um imóvel diferente do ativo de permuta.",
    });
    expect(getByTestId(`matricula-permuta-erro-${ATIVO_ID}`).textContent).toContain(
      "imóvel diferente do ativo de permuta",
    );
  });

  it("explains an ativo with no catalog imóvel, instead of an empty picker", async () => {
    const { getByTestId } = await render({ codigo: null, extracoes: [] });
    expect(getByTestId(`matricula-permuta-sem-codigo-${ATIVO_ID}`).textContent).toContain(
      "vincule-o",
    );
  });

  it("says when the property has no transcribed matrícula yet", async () => {
    const { getByTestId } = await render({ extracoes: [] });
    expect(getByTestId(`matricula-permuta-vazio-${ATIVO_ID}`)).toBeTruthy();
  });
});
