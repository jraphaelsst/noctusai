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

/** `POST /api/studio/agents/{key}/draft/mecanismo-runs` (202): the run is booked and executes in the background. */
export interface MecanismoRunIniciada {
  run_id: string;
  compiled_hash: string;
  driver: string;
  status: "executando";
}

export type MecanismoRunStatus = "executando" | "concluida" | "falhou" | "cancelada";

export interface MecanismoFalha {
  /** The assert name (a CODE, never reply text). */
  assert: string;
  codigo: string;
}

export interface MecanismoExecucao {
  indice: number;
  status: string;
  falhas: MecanismoFalha[];
}

export interface MecanismoCaso {
  slug: string;
  passou: boolean;
  taxa: number;
  execucoes: MecanismoExecucao[];
}

/** `GET /api/studio/agents/{key}/mecanismo-runs/{run_id}`; `casos` is filled once `concluida`. */
export interface MecanismoRun {
  run_id: string;
  version_id: string;
  compiled_hash: string;
  driver: string;
  status: MecanismoRunStatus;
  aprovado: boolean;
  completo: boolean;
  orcamento_excedido: boolean;
  custo_usd: number | null;
  total_casos: number;
  casos_aprovados: number;
  erro: string | null;
  casos: MecanismoCaso[];
}
