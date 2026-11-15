/**
 * The admin editor: unsaved-draft honesty, save order (PATCH header → PUT blocks with the fresh version),
 * the 409 conflict dialog, per-field Confirmar / Confirmar todos, Publicar (+ `faltando`), reorder (buttons),
 * the catalog type select, and the destructive confirmations. Mutations are spied at the hook boundary;
 * the cache-write behaviour itself is pinned in useEstruturas.test.tsx.
 */
import { ConfirmProvider } from "@noctusai/lib/components";
import * as rtl from "@testing-library/react";
const { within } = rtl;
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = vi.hoisted(() => ({
  atualizar: vi.fn(),
  substituir: vi.fn(),
  confirmar: vi.fn(),
  publicar: vi.fn(),
  arquivar: vi.fn(),
  excluir: vi.fn(),
}));
vi.mock("@/hooks/geracao/useEstruturas", () => {
  const hook = (f: (v: unknown) => unknown) => () => ({ mutateAsync: (v: unknown) => f(v), isPending: false });
  return {
    useAtualizarEstrutura: hook((v) => m.atualizar(v)),
    useSubstituirBlocos: hook((v) => m.substituir(v)),
    useConfirmarEstrutura: hook((v) => m.confirmar(v)),
    usePublicarEstrutura: hook((v) => m.publicar(v)),
    useArquivarEstrutura: hook((v) => m.arquivar(v)),
    useExcluirEstrutura: hook((v) => m.excluir(v)),
  };
});

import { detalheAdmin, TIPOS } from "@/test/estruturasFixtures";
import type { EstruturaDetalhe } from "@/types/estruturas";
import { EstruturaEditor } from "./EstruturaEditor";

const apiErr = (code: string, extra: Record<string, unknown> = {}, status = 409) =>
  Object.assign(new Error(`[${status}] x`), { code, status, field: (k: string) => extra[k] });

function renderEditor(d: EstruturaDetalhe = detalheAdmin(), over: Partial<React.ComponentProps<typeof EstruturaEditor>> = {}) {
  const props = { detalhe: d, tipos: TIPOS, onRecarregar: vi.fn().mockResolvedValue(d), onExcluida: vi.fn(), ...over };
  const view = rtl.render(
    <ConfirmProvider>
      <EstruturaEditor {...props} />
    </ConfirmProvider>,
  );
  return { ...view, props };
}

beforeEach(() => {
  vi.clearAllMocks();
  m.atualizar.mockImplementation(async (v) => detalheAdmin({ versao: v.expected_versao + 1 }));
  m.substituir.mockImplementation(async (v) => detalheAdmin({ versao: v.expected_versao + 1 }));
  m.confirmar.mockResolvedValue(detalheAdmin());
  m.publicar.mockResolvedValue(detalheAdmin({ status: "ativa" }));
  m.arquivar.mockResolvedValue(detalheAdmin({ status: "arquivada" }));
  m.excluir.mockResolvedValue(undefined);
});

const salvar = () => rtl.screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement;

describe("draft honesty", () => {
  it("starts clean (Salvar disabled), says 'não salvas' on the first edit and clears on Descartar", async () => {
    renderEditor();
    expect(salvar().disabled).toBe(true);
    expect(rtl.screen.queryByText(/Alterações não salvas/)).toBeNull();
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), " extra");
    expect(rtl.screen.getByText(/Alterações não salvas/)).toBeTruthy();
    expect(salvar().disabled).toBe(false);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Descartar alterações" }));
    expect(rtl.screen.queryByText(/Alterações não salvas/)).toBeNull();
    expect((rtl.screen.getByLabelText("Fórmula da headline") as HTMLTextAreaElement).value).toBe("Como [autoridade teórica] resolve [problema]");
  });

  it("shows the [placeholders] hint for the org's brain + bio", () => {
    renderEditor();
    expect(rtl.screen.getByText(/\[autoridade teórica\], \[problema\].*Cérebro e a bio/)).toBeTruthy();
  });
});

describe("save", () => {
  it("PATCHes the header with the loaded versao, then PUTs the blocks with the versao the PATCH answered", async () => {
    renderEditor();
    await userEvent.clear(rtl.screen.getByLabelText("Fórmula da headline"));
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), "Nova fórmula");
    await userEvent.clear(rtl.screen.getByLabelText("Nome do bloco 1"));
    await userEvent.type(rtl.screen.getByLabelText("Nome do bloco 1"), "Gancho novo");
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(m.substituir).toHaveBeenCalled());
    expect(m.atualizar).toHaveBeenCalledWith({ id: "e1", expected_versao: 3, formula_headline: "Nova fórmula" });
    const corpo = m.substituir.mock.calls[0]![0];
    expect(corpo.expected_versao).toBe(4);
    expect(corpo.blocos[0]).toMatchObject({ id: "b1", nome: "Gancho novo", tipo_id: "t1", tempo: "0–3s" });
    expect(corpo.blocos[1]).toMatchObject({ id: "b2", repeticoes: 2, nota: "O vídeo original fecha com uma pergunta." });
    expect(toast.success).toHaveBeenCalledWith("Estrutura salva.");
  });

  it("refuses an invalid draft inline (pt-BR, aria-invalid) without calling the server", async () => {
    renderEditor();
    await userEvent.clear(rtl.screen.getByLabelText("Nome do bloco 1"));
    await userEvent.click(salvar());
    const campo = rtl.screen.getByLabelText("Nome do bloco 1");
    expect(campo.getAttribute("aria-invalid")).toBe("true");
    expect(rtl.screen.getByText("Informe o nome do bloco.")).toBeTruthy();
    expect(m.atualizar).not.toHaveBeenCalled();
    expect(m.substituir).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Revise os campos destacados antes de salvar.");
  });

  it("409 versao_desatualizada opens the conflict dialog; 'Manter minhas alterações' rebases on the fresh versao", async () => {
    const d = detalheAdmin();
    const { props } = renderEditor(d, { onRecarregar: vi.fn().mockResolvedValue(detalheAdmin({ versao: 9 })) });
    m.atualizar.mockRejectedValueOnce(apiErr("versao_desatualizada"));
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), "!");
    await userEvent.click(salvar());
    expect(await rtl.screen.findByText("Esta estrutura foi alterada por outra pessoa")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Manter minhas alterações" }));
    await rtl.waitFor(() => expect(props.onRecarregar).toHaveBeenCalled());
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(m.atualizar).toHaveBeenCalledTimes(2));
    expect(m.atualizar.mock.calls[1]![0].expected_versao).toBe(9);
  });

  it("'Recarregar e descartar' reloads and drops the draft", async () => {
    const { props } = renderEditor();
    m.atualizar.mockRejectedValueOnce(apiErr("versao_desatualizada"));
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), "!");
    await userEvent.click(salvar());
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Recarregar e descartar minhas alterações" }));
    await rtl.waitFor(() => expect(rtl.screen.queryByText(/Alterações não salvas/)).toBeNull());
    expect(props.onRecarregar).toHaveBeenCalled();
  });

  it("any other refusal is a toast with the catalogue's sentence", async () => {
    renderEditor();
    m.atualizar.mockRejectedValueOnce(apiErr("estrutura_inativa"));
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), "!");
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Esta estrutura não está ativa."));
  });
});

describe("provenance (admin)", () => {
  it("badges only the pending fields, with Confirmar per field in the contract's grammar", async () => {
    renderEditor();
    expect(rtl.screen.getAllByTestId("proveniencia-badge")).toHaveLength(3);
    expect(rtl.screen.getAllByText("Preenchido por referência")).toHaveLength(2);
    expect(rtl.screen.getByText("Sugerido pela IA")).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("Confirmar o tipo do bloco 1"));
    await rtl.waitFor(() => expect(m.confirmar).toHaveBeenCalledWith({ id: "e1", expected_versao: 3, campos: ["bloco.b1.tipo"] }));
    await userEvent.click(rtl.screen.getByLabelText("Confirmar a fórmula"));
    await rtl.waitFor(() => expect(m.confirmar).toHaveBeenLastCalledWith({ id: "e1", expected_versao: 3, campos: ["formula_headline"] }));
  });

  it("Confirmar todos sends {todos:true}", async () => {
    renderEditor();
    expect(rtl.screen.getByTestId("confirmar-bar").textContent).toContain("3 campos aguardam revisão");
    await userEvent.click(rtl.screen.getByRole("button", { name: "Confirmar todos" }));
    await rtl.waitFor(() => expect(m.confirmar).toHaveBeenCalledWith({ id: "e1", expected_versao: 3, todos: true }));
  });

  it("confirming waits while a draft is unsaved (it would race the edit)", async () => {
    renderEditor();
    await userEvent.type(rtl.screen.getByLabelText("Fórmula da headline"), "!");
    expect((rtl.screen.getByRole("button", { name: "Confirmar todos" }) as HTMLButtonElement).disabled).toBe(true);
    expect((rtl.screen.getByLabelText("Confirmar o tipo do bloco 1") as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders no bar when nothing is pending", () => {
    renderEditor(detalheAdmin({ proveniencia: { formula_headline: "admin", formato: "admin", objetivos: "admin" }, blocos: [] }));
    expect(rtl.screen.queryByTestId("confirmar-bar")).toBeNull();
  });
});

describe("publish a rascunho", () => {
  const rascunho = () => detalheAdmin({ status: "rascunho" });
  it("is offered only on a rascunho and publishes with the loaded versao", async () => {
    renderEditor(detalheAdmin());
    expect(rtl.screen.queryByTestId("publicar-bar")).toBeNull();
    rtl.cleanup();
    renderEditor(rascunho());
    await userEvent.click(rtl.screen.getByRole("button", { name: "Publicar" }));
    await rtl.waitFor(() => expect(m.publicar).toHaveBeenCalledWith({ id: "e1", expected_versao: 3 }));
  });

  it("422 rascunho_incompleto lists what is missing, inline", async () => {
    renderEditor(rascunho());
    m.publicar.mockRejectedValueOnce(apiErr("rascunho_incompleto", { faltando: ["formato", "blocos"] }, 422));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Publicar" }));
    const alerta = await rtl.screen.findByRole("alert");
    expect(alerta.textContent).toContain("o formato");
    expect(alerta.textContent).toContain("ao menos um bloco");
  });
});

describe("blocks", () => {
  it("reorders with the move buttons (drag is never the only way) and the order reaches the PUT", async () => {
    renderEditor();
    await userEvent.click(rtl.screen.getByLabelText("Mover bloco 1 para baixo"));
    expect((rtl.screen.getByLabelText("Nome do bloco 1") as HTMLInputElement).value).toBe("Chamada final");
    expect((rtl.screen.getByLabelText("Mover bloco 1 para cima") as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(m.substituir).toHaveBeenCalled());
    expect(m.atualizar).not.toHaveBeenCalled(); // header untouched ⇒ no PATCH
    expect(m.substituir.mock.calls[0]![0].blocos.map((b: { id: string }) => b.id)).toEqual(["b2", "b1"]);
  });

  it("offers the catalog (active types + the block's own inactive one) and sends the chosen tipo_id", async () => {
    renderEditor();
    const select = rtl.screen.getByLabelText("Tipo do bloco 1") as HTMLSelectElement;
    expect([...select.options].map((o) => o.text)).toEqual(["Headline", "Revelação", "CTA Salvar", "Outro"]);
    await userEvent.selectOptions(select, "t2");
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(m.substituir).toHaveBeenCalled());
    expect(m.substituir.mock.calls[0]![0].blocos[0].tipo_id).toBe("t2");
  });

  it("adds a block (defaulting to 'Outro', no id) and removes one", async () => {
    renderEditor();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Adicionar bloco" }));
    expect((rtl.screen.getByLabelText("Tipo do bloco 3") as HTMLSelectElement).value).toBe("t4");
    await userEvent.type(rtl.screen.getByLabelText("Nome do bloco 3"), "Extra");
    await userEvent.click(rtl.screen.getByLabelText("Remover bloco 2"));
    await userEvent.click(salvar());
    await rtl.waitFor(() => expect(m.substituir).toHaveBeenCalled());
    const blocos = m.substituir.mock.calls[0]![0].blocos;
    expect(blocos).toHaveLength(2);
    expect(blocos[1]).not.toHaveProperty("id");
    expect(blocos[1]).toMatchObject({ nome: "Extra", tipo_id: "t4" });
  });

  it("shows the type's reference instruction as the placeholder of an empty instrução", () => {
    renderEditor();
    expect((rtl.screen.getByLabelText("Instrução do bloco 2") as HTMLTextAreaElement).placeholder).toBe("Padrão do tipo: Peça para salvar.");
  });
});

describe("archive / delete", () => {
  const dialogo = async () => within(await rtl.screen.findByRole("dialog"));

  it("archive asks first, then archives", async () => {
    renderEditor();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Arquivar" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Arquivar" }));
    await rtl.waitFor(() => expect(m.arquivar).toHaveBeenCalledWith({ id: "e1", acao: "arquivar" }));
  });

  it("an archived estrutura is read-only with a Restaurar path (no confirmation needed)", async () => {
    renderEditor(detalheAdmin({ status: "arquivada" }));
    expect(rtl.screen.getByText(/Restaure-a para editar/)).toBeTruthy();
    expect((rtl.screen.getByLabelText("Fórmula da headline") as HTMLTextAreaElement).disabled).toBe(true);
    expect(rtl.screen.queryByRole("button", { name: "Adicionar bloco" })).toBeNull();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Restaurar" }));
    await rtl.waitFor(() => expect(m.arquivar).toHaveBeenCalledWith({ id: "e1", acao: "restaurar" }));
  });

  it("delete is confirmed (danger) and leaves the page on success", async () => {
    const { props } = renderEditor();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Cancelar" }));
    expect(m.excluir).not.toHaveBeenCalled();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() => expect(props.onExcluida).toHaveBeenCalled());
  });

  it("estrutura_em_uso is explained, not just refused", async () => {
    const { props } = renderEditor();
    m.excluir.mockRejectedValueOnce(apiErr("estrutura_em_uso"));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Esta estrutura já foi usada em headlines ou roteiros. Arquive-a em vez de excluir."),
    );
    expect(props.onExcluida).not.toHaveBeenCalled();
  });
});
