/**
 * `useEdicaoRoteiro` reconciles the local edit against the POLLED server row
 * (2026-10-13 data-loss regression): a roteiro that finishes generating at the
 * same `versao` must reach the editor, and an edit must never be silently lost
 * nor silently overwrite a newer server text.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const salvar = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  useSalvarRoteiro: () => ({ mutateAsync: salvar, isPending: false }),
}));

import type { Roteiro } from "@/types/geracao";
import { useEdicaoRoteiro } from "./RoteiroEdicao";

const GERADO = "## Capa\nTexto gerado pela IA";
const row = (over: Partial<Roteiro> = {}) =>
  ({ id: "r1", nome: "Roteiro: x", status: "completo", conteudo: GERADO, versao: 1, ...over }) as Roteiro;

function montar(inicial: Roteiro | undefined) {
  return renderHook(({ r }: { r: Roteiro | undefined }) => useEdicaoRoteiro(r), { initialProps: { r: inicial } });
}

// Block body: a function returned from a hook is run by vitest as its teardown.
beforeEach(() => {
  salvar.mockReset();
});

describe("useEdicaoRoteiro — reconciliação com o servidor", () => {
  it("criando (conteudo null) → completo (conteudo X) na MESMA versao mostra X e não marca alteração", () => {
    const h = montar(row({ status: "criando", conteudo: null }));
    expect(h.result.current.conteudo).toBe("");
    h.rerender({ r: row({ status: "perguntas", conteudo: null }) });
    h.rerender({ r: row({ status: "processando", conteudo: null }) });
    h.rerender({ r: row() });
    expect(h.result.current.conteudo).toBe(GERADO);
    expect(h.result.current.alterou).toBe(false);
    expect(h.result.current.conflito).toBe(false);
  });

  it("sem edição local, uma mudança do servidor (outra aba / reprocesso) é adotada", () => {
    const h = montar(row());
    h.rerender({ r: row({ conteudo: "versão da outra aba", nome: "Outro nome", versao: 2 }) });
    expect(h.result.current.conteudo).toBe("versão da outra aba");
    expect(h.result.current.nome).toBe("Outro nome");
    expect(h.result.current.alterou).toBe(false);
    expect(h.result.current.conflito).toBe(false);
  });

  it("texto digitado + mudança do servidor: mantém o digitado, sinaliza conflito e o save não sobrescreve às cegas", async () => {
    const h = montar(row());
    act(() => h.result.current.setConteudo("meu texto"));
    h.rerender({ r: row({ conteudo: "salvo em outra aba", versao: 2 }) });
    expect(h.result.current.conteudo).toBe("meu texto");
    expect(h.result.current.conflito).toBe(true);
    // The save carries the versao the edit was based on, so the server answers 409, not an overwrite.
    salvar.mockImplementation(async () => {
      throw Object.assign(new Error("[409] conflito"), { status: 409 });
    });
    await act(async () => {
      await h.result.current.salvar();
    });
    expect(salvar).toHaveBeenCalledWith(expect.objectContaining({ conteudo: "meu texto", expected_versao: 1 }));
    expect(h.result.current.conflito).toBe(true);
    // "Recarregar" discards the local edit and takes the server row.
    act(() => h.result.current.recarregar());
    expect(h.result.current.conteudo).toBe("salvo em outra aba");
    expect(h.result.current.conflito).toBe(false);
    expect(h.result.current.alterou).toBe(false);
  });

  it("mudança só no campo não editado é adotada sem conflito", () => {
    const h = montar(row());
    act(() => h.result.current.setConteudo("meu texto"));
    h.rerender({ r: row({ nome: "Renomeado", versao: 2 }) });
    expect(h.result.current.nome).toBe("Renomeado");
    expect(h.result.current.conteudo).toBe("meu texto");
    expect(h.result.current.conflito).toBe(false);
  });

  it("o próprio save, ao voltar do servidor, não vira conflito e avança a versao base", async () => {
    const h = montar(row());
    act(() => h.result.current.setConteudo("editado"));
    salvar.mockResolvedValue(row({ conteudo: "editado", versao: 2 }));
    await act(async () => {
      await h.result.current.salvar();
    });
    expect(salvar).toHaveBeenLastCalledWith(expect.objectContaining({ conteudo: "editado", expected_versao: 1 }));
    h.rerender({ r: row({ conteudo: "editado", versao: 2 }) });
    expect(h.result.current.conflito).toBe(false);
    expect(h.result.current.alterou).toBe(false);
    act(() => h.result.current.setConteudo("editado de novo"));
    await act(async () => {
      await h.result.current.salvar();
    });
    expect(salvar).toHaveBeenLastCalledWith(expect.objectContaining({ expected_versao: 2 }));
  });

  it("apagar todo o conteúdo de um roteiro completo é inválido (nunca envia vazio)", async () => {
    const h = montar(row());
    act(() => h.result.current.setConteudo("   "));
    expect(h.result.current.alterou).toBe(true);
    expect(h.result.current.valido).toBe(false);
    await act(async () => {
      await h.result.current.salvar();
    });
    expect(salvar).not.toHaveBeenCalled();
  });

  it("trocar de roteiro reinicia o estado a partir do novo", () => {
    const h = montar(row());
    act(() => h.result.current.setConteudo("rascunho"));
    h.rerender({ r: row({ id: "r2", conteudo: "outro roteiro" }) });
    expect(h.result.current.conteudo).toBe("outro roteiro");
    expect(h.result.current.conflito).toBe(false);
  });
});
