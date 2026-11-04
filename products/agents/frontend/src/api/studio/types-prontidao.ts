/** Agent readiness checklist (`GET /api/studio/agents/{key}/prontidao`) and the skills-refresh result. */
export type ProntidaoGrupo =
  | "conteudo"
  | "avaliacoes"
  | "padrao"
  | "skills"
  | "ferramentas"
  | "specs"
  | "geracao"
  | "controles";
export type ProntidaoSeveridade = "bloqueante" | "aviso" | "ok";

export interface ProntidaoItem {
  codigo: string;
  grupo: ProntidaoGrupo;
  severidade: ProntidaoSeveridade;
  mensagem: string;
  acao_sugerida: string | null;
}

export interface Prontidao {
  pronto_para_publicar: boolean;
  itens: ProntidaoItem[];
}

export const PRONTIDAO_GRUPO_LABEL: Record<ProntidaoGrupo, string> = {
  conteudo: "Conteúdo",
  avaliacoes: "Avaliações",
  padrao: "Padrão de qualificação",
  skills: "Skills",
  ferramentas: "Ferramentas",
  specs: "Especificações",
  geracao: "Geração com IA",
  controles: "Controles",
};

export interface SkillsAtualizadas {
  atualizadas: { skill: string; de: number | string; para: number | string }[];
  sem_mudanca: string[];
}
