/** The pure rules of the Estrutura selection: max 3, one formato, coded-error readers. */
import { describe, expect, it } from "vitest";

import {
  alternarEstrutura,
  candidatosDoErro,
  formatoDaSelecao,
  mensagemDoForm,
  motivoDeBloqueio,
  sugestoesDoErro,
  type EstruturaEscolhida,
} from "./selecao";

const e = (id: string, formato: EstruturaEscolhida["formato"] = "reels"): EstruturaEscolhida => ({
  id,
  codigo: Number(id.replace(/\D/g, "")) || 1,
  formula_headline: `Fórmula ${id}`,
  formato,
  perfil: { id: "p", handle: "criador", nome: null, foto_url: null },
});

describe("selecao", () => {
  it("adds, removes and never passes 3", () => {
    let sel: EstruturaEscolhida[] = [];
    for (const id of ["e1", "e2", "e3", "e4"]) sel = alternarEstrutura(sel, e(id));
    expect(sel.map((x) => x.id)).toEqual(["e1", "e2", "e3"]);
    expect(alternarEstrutura(sel, e("e2")).map((x) => x.id)).toEqual(["e1", "e3"]);
  });

  it("locks the formato of the first pick and refuses a different one", () => {
    const sel = [e("e1", "carrossel")];
    expect(formatoDaSelecao(sel)).toBe("carrossel");
    expect(motivoDeBloqueio(sel, { formato: "reels" })).toBe("formato");
    expect(motivoDeBloqueio(sel, { formato: "carrossel" })).toBeNull();
    expect(alternarEstrutura(sel, e("e2", "reels"))).toHaveLength(1);
  });

  it("limit wins over formato in the reason; a cap of 1 blocks the second", () => {
    expect(motivoDeBloqueio([e("e1"), e("e2"), e("e3")], { formato: "post" })).toBe("limite");
    expect(motivoDeBloqueio([e("e1")], { formato: "reels" }, 1)).toBe("limite");
  });

  it("reads the flat coded candidates, and only for the matching code", () => {
    const cand = [{ perfil_id: "p1", handle: "ana", nome: "Ana" }];
    const amb = Object.assign(new Error("x"), { code: "perfil_ambiguo", body: { code: "perfil_ambiguo", candidatos: cand } });
    expect(candidatosDoErro(amb)).toEqual(cand);
    expect(sugestoesDoErro(amb)).toEqual([]);
    const nao = Object.assign(new Error("x"), { code: "perfil_nao_encontrado_na_biblioteca", body: { sugestoes: cand } });
    expect(sugestoesDoErro(nao)).toEqual(cand);
    expect(candidatosDoErro(new Error("x"))).toEqual([]);
  });

  it("says each new refusal in pt-BR and strips a status prefix", () => {
    for (const code of ["muitas_estruturas", "formatos_misturados", "formato_diferente_da_estrutura", "estrutura_obrigatoria_invalida", "viral_sem_estrutura"]) {
      const m = mensagemDoForm(Object.assign(new Error("[422] cru"), { code }), "fallback");
      expect(m).not.toBe("fallback");
      expect(m).not.toContain("[422]");
    }
    expect(mensagemDoForm(new Error("[500] falhou"), "fb")).toBe("falhou");
  });
});
