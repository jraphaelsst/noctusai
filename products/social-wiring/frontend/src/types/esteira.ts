/** Esteira de Reels — types per esteira-contract.md §5.4 (BE schemas mirror these). */
/** Stage roles (criacao-pipeline-contract.md §1). `gravacao` is the legacy alias of `criacao` (kept one release). */
export type PapelEsteira =
  | "roteiro" | "criacao" | "gravacao" | "edicao" | "aprovacao_midia" | "pronto" | "postado" | "cancelado";

/** `cs_posts.criacao_estado` (contract §1): the sub-state of a card inside the criação pipeline. */
export type CriacaoEstado =
  | "aguardando_aprovacao" | "refinando" | "aprovado" | "na_fila" | "gerando" | "aguardando_edicao"
  | "aguardando_aprovacao_midia" | "midia_aprovada" | "midia_reprovada" | "falhou" | "cancelado";

/** What an approval acts on: the headline, the roteiro or the final media. */
export type AlvoAprovacao = "headline" | "roteiro" | "midia";
export type DecisaoAprovacao = "aprovar" | "reprovar";

/** Live per-step progress of a post's criação run (`JobProgress` frame, contract §3). */
export interface CriacaoProgresso {
  /** Current step key (`tts`, `render_motion`, ...); the label is the server's `mensagem`. */
  passo: string | null;
  /** pt-BR sentence of what the agent is doing right now ("Sintetizando voz (2/3)"). */
  mensagem: string | null;
  /** 0..1, weighted by expected step duration; `null` = unknown (never an invented number). */
  progresso: number | null;
  terminal: boolean;
}

/** Org monthly vendor-cost cap (contract M-E): default US$15, editable by org admins. */
export interface CotaCriacao {
  limite_usd_mes: number;
  gasto_usd_mes: number | null;
  padrao_usd_mes: number;
}
/** `acima_recomendado` / `recomendado_max_texto`: computed length warning (never a block). */
export interface ResumoHeadline { id: string; texto: string; favorita: boolean; acima_recomendado: boolean; recomendado_max_texto: number }
export interface ResumoRoteiro { id: string; nome: string; status: "criando"|"perguntas"|"processando"|"completo"|"falha"; headline_id: string | null; headline_diferente: boolean }
export interface LinkProducao { rotulo: string; url: string }
export interface PostCard {
  id: string; marca_id: string; marca_nome: string; titulo: string; formato: "reel" | "carrossel" | "story" | "feed";
  etapa_id: string; kanban_pos: string;               // numeric serialized as string
  headline: ResumoHeadline | null; roteiro: ResumoRoteiro | null;
  membros: { id: string; nome: string; cor: string | null }[];
  gravacao_em: string | null; data_entrega: string | null; entrega_concluida: boolean;
  postado_em: string | null; motivo_bloqueio: string | null; arquivado: boolean;
  /** Criação pipeline sub-state; absent on cards the server has not migrated yet. */
  criacao_estado?: CriacaoEstado | null; criacao_rota?: string | null; falha_codigo?: string | null;
  /** Set once headline AND roteiro are approved (`aprovado_em`). */
  aprovado_em?: string | null;
  /** Per-target approval (server-derived), so the UI never infers it from the stage. */
  headline_aprovada?: boolean; roteiro_aprovado?: boolean; midia_aprovada?: boolean;
  checklist: { feitos: number; total: number };      // from the hub badges
  comentarios: number;
}
export interface PostDetalhe extends PostCard {
  conta: { id: string; account_label: string } | null;
  legenda: string | null; hashtags: string[]; primeiro_comentario: string | null;
  links_producao: LinkProducao[]; permalink: string | null; ig_media_id: string | null;
  lote_ativo: { id: string; status: string; etapa: string | null } | null; // latest batch with post_id still criando/processando
  created_at: string; updated_at: string;
}
export interface PostCreate { marca_id: string; titulo?: string; headline_id?: string; etapa_id?: string; conta_id?: string; gravacao_em?: string; data_entrega?: string }
export type RecorrenciaPost = "diaria" | "semanal" | "mensal" | "anual";
/**
 * `PATCH /posts/{id}` (§5.1 #5). An explicit `null` clears a nullable field; `entrega_concluida`
 * is NOT NULL server-side, so `null` is ignored. `lembrete_minutos_antes` is 0..525600.
 * `gravacao_em` is a DATE (`YYYY-MM-DD`), `data_inicio`/`data_entrega` are datetimes with offset.
 */
export type PostUpdate = Partial<Pick<PostDetalhe, "titulo"|"legenda"|"hashtags"|"primeiro_comentario"|"links_producao"|"permalink"|"ig_media_id"|"gravacao_em"|"arquivado"|"entrega_concluida">> & {
  conta_id?: string | null;
  data_inicio?: string | null;
  data_entrega?: string | null;
  lembrete_minutos_antes?: number | null;
  recorrencia?: RecorrenciaPost | null;
};
export interface MembroEquipe { id: string; nome: string; funcao: string | null; cor: string | null; user_id: string | null; ativo: boolean }
export interface PendenciasErro { code: "pendencias"; faltando: ("headline"|"roteiro"|"roteiro_incompleto"|"headline_nao_aprovado"|"roteiro_nao_aprovado")[] }
