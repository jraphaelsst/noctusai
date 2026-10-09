import type { PesquisaGrupo, PesquisaVariable } from "@/hooks/usePesquisa";

export const GRUPO_ROTULO: Record<PesquisaGrupo, string> = {
  publico: "Meu Público",
  especialista: "Sobre Mim",
  produto: "Produto",
  global: "Globais",
};

export const GRUPO_ORDEM: PesquisaGrupo[] = ["publico", "especialista", "produto", "global"];

/** Variables bucketed by grupo, each bucket in `sort_order`. Empty groups dropped. */
export function agruparVariaveis(
  vars: PesquisaVariable[],
): Array<{ grupo: PesquisaGrupo; rotulo: string; variaveis: PesquisaVariable[] }> {
  return GRUPO_ORDEM.map((grupo) => ({
    grupo,
    rotulo: GRUPO_ROTULO[grupo],
    variaveis: vars.filter((v) => v.grupo === grupo).sort((a, b) => a.sort_order - b.sort_order),
  })).filter((g) => g.variaveis.length > 0);
}
