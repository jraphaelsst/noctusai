/** Agent readiness checklist (`GET /api/studio/agents/{key}/prontidao`) and the skills-refresh result. */
/** The backend's closed group set (`app/studio/prontidao.py` GRUPOS; a backend test keeps the two equal). */
export type ProntidaoGrupo =
  | "compilador"
  | "conteudo"
  | "padrao"
  | "avaliacao"
  | "skills"
  | "ferramentas"
  | "especificacoes"
  | "seguranca"
  | "geracao"
  | "operacao"
  | "modelo";
export type ProntidaoSeveridade = "bloqueante" | "aviso" | "ok";

export interface ProntidaoItem {
  codigo: string;
  grupo: ProntidaoGrupo;
  severidade: ProntidaoSeveridade;
  mensagem: string;
  acao_sugerida: string | null;
  /** Item-specific facts (keys and counts only). `base_validada` / `base_nao_validada` carry `camadas`. */
  detalhe?: Record<string, unknown> | null;
}

/** One ancestor layer in the chain gate (`detalhe.camadas` of the `base_*` items; `app/studio/camada_validada.py`). */
export interface CamadaBase {
  agent_key: string;
  versao: number | null;
  validada: boolean;
  /** `validada` | `sem_casos` | `criticos_pendentes` | `sem_medicao` | `sem_versao` */
  motivo: string;
  criticos_total: number;
  criticos_consolidados: number;
  criticos_pendentes: string[];
}

export interface Prontidao {
  pronto_para_publicar: boolean;
  itens: ProntidaoItem[];
}

export const PRONTIDAO_GRUPO_LABEL: Record<ProntidaoGrupo, string> = {
  compilador: "Prompt compilado",
  conteudo: "Conteúdo",
  padrao: "Padrão de qualificação",
  avaliacao: "Avaliações",
  skills: "Skills",
  ferramentas: "Ferramentas",
  especificacoes: "Especificações",
  seguranca: "Segurança",
  geracao: "Geração com IA",
  operacao: "Operação",
  modelo: "Modelo canônico",
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
