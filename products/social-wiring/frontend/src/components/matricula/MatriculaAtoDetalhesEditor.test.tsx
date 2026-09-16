/**
 * MatriculaAtoDetalhesEditor — the assertions worth having are all about the
 * PATCH BODY, because the body is the feature's contract with the backend and
 * the three cases are indistinguishable on screen:
 *
 *   · nothing edited  -> `{}`            (confirm the suggestion as it stands)
 *   · a field emptied -> `{campo: null}` (the extractor read something absent)
 *   · a field changed -> `{campo: valor}` (and NOTHING else — an absent key
 *     keeps its suggestion, so a full spread would re-stamp every field as
 *     human-typed)
 *
 * Plus the two states the operator has to be able to tell apart: a suggestion
 * nobody has agreed with, and a low-confidence reading.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import MatriculaAtoDetalhesEditor from "./MatriculaAtoDetalhesEditor";
import type { MatriculaAtoDetalhes } from "@/hooks/useMatriculaEstrutura";

const ATO = { id: "ato-1", kind: "R" as const, numero: 1, rotulo: "R-1 Compra e venda" };
const PREFIXO = `ato-detalhes-${ATO.id}`;

function detalhes(over: Partial<MatriculaAtoDetalhes> = {}): MatriculaAtoDetalhes {
  return {
    id: "det-1",
    ato_id: ATO.id,
    natureza: "compra_e_venda",
    natureza_confianca: "alta",
    data_registro: "2001-03-10",
    data_registro_confianca: "alta",
    valor: "250000.00",
    valor_confianca: "baixa",
    transmitentes: [{ nome: "Joao da Silva", cpf_cnpj: "000.000.000-00" }],
    transmitentes_confianca: "alta",
    adquirentes: [],
    adquirentes_confianca: "nenhuma",
    credor: null,
    credor_confianca: "nenhuma",
    instrumento: {
      tipo: "Escritura Publica de Venda e Compra",
      data: "2001-02-01",
      tabelionato: "1o Tabeliao",
      livro: "100",
      folhas: "25",
      cidade: "Sao Paulo",
    },
    instrumento_confianca: "alta",
    atos_referidos: [],
    atos_referidos_confianca: "nenhuma",
    origem: "sugestao",
    confirmado_por: null,
    confirmado_em: null,
    ...over,
  };
}

async function render(over: Partial<MatriculaAtoDetalhes> | null = {}) {
  const rtl = await import("@testing-library/react");
  const onConfirmar = vi.fn();
  const view = rtl.render(
    <MatriculaAtoDetalhesEditor
      ato={ATO}
      detalhes={over === null ? null : detalhes(over)}
      saving={false}
      onConfirmar={onConfirmar}
    />,
  );
  return { ...rtl, ...view, onConfirmar };
}

describe("MatriculaAtoDetalhesEditor — the patch body", () => {
  it("🔴 confirms with an EMPTY patch when nothing was edited", async () => {
    // `{}` is what tells the backend "I reviewed this and it is correct";
    // sending the current values instead would re-stamp every field as
    // human-typed (`confianca: alta`) and erase the extractor's own doubt.
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({});
  });

  it("says so in the button when there is nothing to save", async () => {
    const { getByTestId } = await render();
    expect(getByTestId(`${PREFIXO}-confirmar`).textContent).toContain("Confirmar como está");
  });

  it("🔴 sends `null` — not `\"\"` — for a field the operator cleared", async () => {
    // The backend stores "" as a present, empty value, which then reads as
    // "checked, and really is blank" everywhere downstream.
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId(`${PREFIXO}-valor`), { target: { value: "" } });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({ valor: null });
  });

  it("🔴 sends ONLY the field that changed", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId(`${PREFIXO}-credor`), { target: { value: "Banco X" } });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({ credor: "Banco X" });
  });

  it("trims a value rather than storing the operator's stray spaces", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId(`${PREFIXO}-credor`), { target: { value: "  Banco X  " } });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({ credor: "Banco X" });
  });

  it("edits a party in place, keeping its document number", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId(`${PREFIXO}-transmitentes-nome-0`), {
      target: { value: "João da Silva" },
    });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({
      transmitentes: [{ nome: "João da Silva", cpf_cnpj: "000.000.000-00" }],
    });
  });

  it("adds a party", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.click(getByTestId(`${PREFIXO}-adquirentes-adicionar`));
    fireEvent.change(getByTestId(`${PREFIXO}-adquirentes-nome-0`), {
      target: { value: "Maria" },
    });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({
      adquirentes: [{ nome: "Maria", cpf_cnpj: null }],
    });
  });

  it("🔴 an empty party row is dropped, not sent as a nameless party", async () => {
    // The backend 422s a party without a `nome`; an abandoned empty row must
    // not turn a confirmation into a validation error.
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.click(getByTestId(`${PREFIXO}-adquirentes-adicionar`));
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({});
  });

  it("clears a party list with `[]`", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.click(getByTestId(`${PREFIXO}-transmitentes-remover-0`));
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({ transmitentes: [] });
  });

  it("sends the whole instrumento sub-form when one of its fields changes", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId(`${PREFIXO}-instrumento-livro`), {
      target: { value: "200" },
    });
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({
      instrumento: {
        tipo: "Escritura Publica de Venda e Compra",
        data: "2001-02-01",
        tabelionato: "1o Tabeliao",
        livro: "200",
        folhas: "25",
        cidade: "Sao Paulo",
      },
    });
  });

  it("🔴 an instrumento emptied field-by-field becomes `null`, not an object of nulls", async () => {
    // `frase_titulo_aquisitivo` renders FROM this object, so a
    // present-but-empty instrumento would produce a phrase built from nothing.
    const { getByTestId, fireEvent, onConfirmar } = await render();
    for (const campo of ["tipo", "data", "tabelionato", "livro", "folhas", "cidade"]) {
      fireEvent.change(getByTestId(`${PREFIXO}-instrumento-${campo}`), {
        target: { value: "" },
      });
    }
    fireEvent.click(getByTestId(`${PREFIXO}-confirmar`));
    expect(onConfirmar).toHaveBeenCalledWith({ instrumento: null });
  });
});

describe("MatriculaAtoDetalhesEditor — suggestion vs confirmed", () => {
  it("🔴 says nobody has confirmed a suggestion yet", async () => {
    const { getByTestId } = await render({ origem: "sugestao" });
    const badge = getByTestId(`${PREFIXO}-origem`);
    expect(badge.getAttribute("data-origem")).toBe("sugestao");
    expect(badge.textContent).toContain("ninguém conferiu");
  });

  it("names who confirmed it, once someone has", async () => {
    const { getByTestId } = await render({
      origem: "confirmado",
      confirmado_por: { id: "u1", nome: "Ana" },
      confirmado_em: "2026-03-01T10:00:00Z",
    });
    const badge = getByTestId(`${PREFIXO}-origem`);
    expect(badge.getAttribute("data-origem")).toBe("confirmado");
    expect(getByTestId(PREFIXO).textContent).toContain("Ana");
  });

  it("🔴 highlights a low-confidence field and leaves a high-confidence one plain", async () => {
    // A `baixa` reading that looks like a fact is exactly how a misread
    // becomes an unquestioned one.
    const { getByTestId } = await render();
    expect(getByTestId(`${PREFIXO}-confianca-valor`).getAttribute("data-destaque")).toBe("true");
    expect(getByTestId(`${PREFIXO}-confianca-natureza`).getAttribute("data-destaque")).toBe(
      "false",
    );
  });

  it("highlights a field the extractor found nothing for", async () => {
    const { getByTestId } = await render();
    const badge = getByTestId(`${PREFIXO}-confianca-credor`);
    expect(badge.getAttribute("data-confianca")).toBe("nenhuma");
    expect(badge.textContent).toContain("preencha");
  });

  it("shows the cited acts read-only when the act cites others", async () => {
    const { getByTestId } = await render({
      atos_referidos: [{ kind: "R", numero: 3 }],
      atos_referidos_confianca: "alta",
    });
    expect(getByTestId(`${PREFIXO}-atos-referidos`).textContent).toContain("R-3");
  });

  it("explains the abertura has no details instead of rendering an empty form", async () => {
    const { getByTestId, queryByTestId } = await render(null);
    expect(getByTestId(`${PREFIXO}-ausente`)).toBeTruthy();
    expect(queryByTestId(`${PREFIXO}-confirmar`)).toBeNull();
  });

  it("surfaces the server's refusal verbatim", async () => {
    const rtl = await import("@testing-library/react");
    rtl.render(
      <MatriculaAtoDetalhesEditor
        ato={ATO}
        detalhes={detalhes()}
        saving={false}
        errorMessage="Natureza desconhecida: foo"
        onConfirmar={vi.fn()}
      />,
    );
    expect(rtl.screen.getByTestId(`${PREFIXO}-erro`).textContent).toContain(
      "Natureza desconhecida: foo",
    );
  });
});
