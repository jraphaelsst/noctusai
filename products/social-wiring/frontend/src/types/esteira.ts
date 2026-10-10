/** Esteira de Reels — types per esteira-contract.md §5.4 (BE schemas mirror these). */
export type PapelEsteira = "gravacao" | "postado" | "cancelado";
export interface ResumoHeadline { id: string; texto: string; favorita: boolean }
export interface ResumoRoteiro { id: string; nome: string; status: "criando"|"perguntas"|"processando"|"completo"|"falha"; headline_id: string | null; headline_diferente: boolean }
export interface LinkProducao { rotulo: string; url: string }
export interface PostCard {
  id: string; marca_id: string; marca_nome: string; titulo: string; formato: "reel";
  etapa_id: string; kanban_pos: string;               // numeric serialized as string
  headline: ResumoHeadline | null; roteiro: ResumoRoteiro | null;
  membros: { id: string; nome: string; cor: string | null }[];
  gravacao_em: string | null; data_entrega: string | null; entrega_concluida: boolean;
  postado_em: string | null; motivo_bloqueio: string | null; arquivado: boolean;
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
export type PostUpdate = Partial<Pick<PostDetalhe, "titulo"|"legenda"|"hashtags"|"primeiro_comentario"|"links_producao"|"permalink"|"ig_media_id"|"gravacao_em"|"arquivado">> & { conta_id?: string | null };
export interface MembroEquipe { id: string; nome: string; funcao: string | null; cor: string | null; user_id: string | null; ativo: boolean }
export interface LegendaGerada { legenda: string; hashtags: string[]; primeiro_comentario: string }
export interface PendenciasErro { code: "pendencias"; faltando: ("headline"|"roteiro"|"roteiro_incompleto")[] }
