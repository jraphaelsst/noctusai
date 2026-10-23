/**
 * Julia v2 Studio wire types (CONTRACT §2.4, §2.6, §3, §5, §8; D7/D8 skills library).
 *
 * Field names are the routers' (`studio_conteudo_router.py`, `qualificacao_router.py`,
 * `channel_threads_router.py`, `skills_biblioteca_router.py`) byte-for-byte. Types only:
 * no prompt text, no fixtures, no rule content lives in this file (CONTRACT §0.4 IP tiers).
 */
import type { ManifestSection } from "./types";

/** Which Studio surface the SERVER decided this agent row belongs to (`definition_scope`). */
export type DefinitionScope = "org" | "plataforma" | "instancia";
export type ConteudoModo = "linhas" | "legado";

// ── content tables of a version (§2.2/§2.4) ─────────────────────────────────

export interface TextoRow {
  id?: string;
  chave: string;
  conteudo: string;
}
export interface FerramentaRow {
  id?: string;
  ferramenta: string;
  ativo: boolean;
  descricao: string;
  parametros: Record<string, string>;
  obrigatoria_skill: string | null;
}
export interface DecisaoOpcao {
  valor: string;
  rotulo: string;
  padrao: boolean;
}
export interface DecisaoRow {
  id?: string;
  chave: string;
  titulo: string;
  regra: string;
  opcoes: DecisaoOpcao[];
}
export type SpecTipo = string;
export interface SpecDefRow {
  id?: string;
  chave: string;
  rotulo: string;
  descricao: string;
  tipo: SpecTipo;
  obrigatoria: boolean;
  exemplo: string | null;
}

export interface ConteudoSetOut<T> {
  version_id: string;
  itens: T[];
}

export type ConteudoKind = "textos" | "ferramentas" | "decisoes" | "specs";
export interface ConteudoRowByKind {
  textos: TextoRow;
  ferramentas: FerramentaRow;
  decisoes: DecisaoRow;
  specs: SpecDefRow;
}

/** `GET .../versions/{id}/payload`: manifest entries outside the prompt carry `inicio`/`fim` = null. */
export interface PayloadManifestEntry extends Omit<ManifestSection, "inicio" | "fim" | "origem"> {
  inicio: number | null;
  fim: number | null;
  origem: { tipo: string; id: string | null; campo: string | null };
}
export interface PayloadAviso {
  codigo: string;
  mensagem: string;
  bloqueante: boolean;
}
export interface ConteudoPayload {
  version_id: string;
  hash: string;
  texto: string;
  tokens_estimados: number;
  manifest: PayloadManifestEntry[];
  avisos: PayloadAviso[];
  textos: TextoRow[];
  ferramentas: FerramentaRow[];
  decisoes: DecisaoRow[];
  specs: SpecDefRow[];
}

// ── org specs (§2.6) ────────────────────────────────────────────────────────

export interface OrgSpecValor {
  chave: string;
  valor: string;
  updated_at: string | null;
}
export interface OrgSpecs {
  agent_key: string;
  version_id: string | null;
  versao: number | null;
  declaradas: SpecDefRow[];
  valores: OrgSpecValor[];
  faltando: string[];
}
export interface OrgStatus {
  agent_key: string;
  completo: boolean;
  sem_versao: boolean;
  specs_faltando: string[];
}
export interface CompiladoOrg {
  version_id: string;
  versao: number;
  hash: string;
  texto: string;
  tokens_estimados: number;
  manifest: PayloadManifestEntry[];
  avisos: PayloadAviso[];
  specs_faltando: string[];
  completo: boolean;
}
export interface PlataformaTexto {
  chave: string;
  conteudo: string;
  updated_at: string;
}

// ── qualification standard (§3) ─────────────────────────────────────────────

export interface PadraoResumo {
  id: string;
  chave: string;
  nome: string;
  descricao: string | null;
}
export interface PadraoVersaoMeta {
  id: string;
  versao: number;
  status: "rascunho" | "publicada" | "arquivada" | string;
  notas: string | null;
  publicada_em: string | null;
}
export interface QualOpcao {
  valor: string;
  rotulo: string;
  descricao_modelo: string;
  sinonimos: string[];
}
export interface QualCriterio {
  chave: string;
  grupo: string;
  rotulo: string;
  descricao_modelo: string;
  tipo: string;
  opcoes: QualOpcao[];
  unidade: string | null;
  sensivel: "faixa" | "nao_coletar" | null;
  pontuacao: Record<string, unknown> | Array<Record<string, unknown>>;
  ordem: number;
  ativo: boolean;
  eixo: string | null;
  escopo: string | null;
  validade_dias: number | null;
}
export type QualCriterioInput = Omit<QualCriterio, "chave">;
export interface QualEstagio {
  chave: string;
  rotulo: string;
  descricao: string;
  ordem: number;
  regra: Record<string, unknown>;
  conclusivo: boolean;
  terminal: boolean;
}
export type QualEstagioInput = Omit<QualEstagio, "chave">;
export interface QualParametros {
  minimo_para_ofertar: Record<string, unknown>;
  lote_ofertas: number;
  score_max: number;
  eixos: Record<string, unknown>;
  pedir_identificacao_quando: Record<string, unknown> | null;
}
export interface PadraoVersao extends PadraoVersaoMeta {
  padrao: string;
  criterios: QualCriterio[];
  estagios: QualEstagio[];
  parametros: QualParametros;
}
export interface RegraErro {
  code: string;
  path: string;
  detail: string;
}
export interface ValidarResposta {
  ok: boolean;
  erros: RegraErro[];
}

// ── shared skills library (D7/D8; branch feat/julia-v2-a-skills) ────────────

export interface BibliotecaSkill {
  id: string;
  chave: string;
  nome: string;
  descricao: string | null;
  versao_publicada: number | null;
  tem_rascunho: boolean;
}
export interface SkillVersaoMeta {
  id: string;
  versao: number;
  status: "rascunho" | "publicada" | "arquivada";
  notas: string | null;
  publicada_em: string | null;
}
export interface SkillArquivo {
  caminho: string;
  titulo: string | null;
  conteudo: string;
}
export interface SkillVersao extends SkillVersaoMeta {
  skill: string;
  descricao_modelo: string;
  corpo: string;
  arquivos: SkillArquivo[];
}
/** chave of a library skill: lower-case words joined by single hyphens (server-enforced, ≤64). */
export const SKILL_CHAVE_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export interface BibliotecaRef {
  skill: string;
  skill_versao_id: string;
  versao: number;
  obrigatoria_para: string[];
  ordem: number;
  nova_versao: number | null;
  nova_versao_id: string | null;
}
export interface BibliotecaRefs {
  version_id: string;
  items: BibliotecaRef[];
}
export interface BibliotecaRefInput {
  versao?: number;
  obrigatoria_para: string[];
  ordem: number;
}

// ── controls and conversations (§5, §6) ─────────────────────────────────────

export type ModoOperacao = "ligado" | "drenando" | "desligado";
export interface Drenagem {
  abertas: number;
  ociosas: number;
  efetivas: number;
  concluida: boolean;
  idade_max_dias: number;
  idades_dias: number[];
}
export interface Controle {
  agent_key: string;
  modo: ModoOperacao;
  aceita_novos_leads: boolean;
  dreno_inatividade_dias: number;
  threads_abertas: number;
  drenagem: Drenagem;
}
export interface ControleUpdate {
  modo: ModoOperacao;
  dreno_inatividade_dias?: number;
}

export interface CanalConversa {
  id: string;
  agent_key: string;
  titulo: string | null;
  status: string;
  last_message_at: string | null;
  created_at: string;
  channel: string | null;
  contact: Record<string, unknown> | null;
  /**
   * NOC-REMEDIATE[studio-thread-result]: not returned by `/api/conversations/channel` today (the
   * computed stage/score live behind the channel-token route and the violation feed has no route).
   * Rendered as chips only when the server provides it. — 2026-10-20
   */
  resultado?: { estagio: string | null; score: number | null; violacoes: number } | null;
  /** The lead's latest recorded opt-out (`/api/conversations/channel`); `null`/absent = none. */
  opt_out_evento?: OptOutEvento | null;
}
export interface CanalConversas {
  items: CanalConversa[];
  total: number;
}
export type ThreadRole = "user" | "assistant" | "humano" | "evento";
export interface MensagemThread {
  id: string;
  role: ThreadRole;
  texto: string;
  agent_key: string | null;
  agent_nome: string | null;
  autor_user_id: string | null;
  created_at: string;
}
export interface Participante {
  agent_key: string;
  agent_nome: string;
  estado: "ativo" | "pausado" | "concluido" | "encerrado" | "transferido" | string;
  entrou_em: string;
  saiu_em: string | null;
  motivo: string | null;
  ultimo_turno_em: string | null;
  pausado_ate: string | null;
}
export interface ParticipanteEstadoInput {
  estado: "pausado" | "ativo";
  motivo?: string;
}

// NOC-REMEDIATE[julia-studio-conformidade-api]: the backend has the stores
// (`stores/conformidade.py`) but NO HTTP route yet; these shapes are the store's, the paths in
// `hooks/studio/useConformidade.ts` are PROPOSED. — 2026-10-20
export interface ConformidadeRegra {
  regra: string;
  ativo: boolean;
  politica: "registrar" | "bloquear";
  mensagem_correcao_texto_chave: string | null;
}
export interface ConformidadeViolacao {
  id: string;
  regra: string;
  politica: "registrar" | "bloquear" | "sinal";
  bloqueada: boolean;
  thread_id: string | null;
  created_at: string;
}

/** `OptOutEventoOut` -- one lead opt-out (who stopped it, why, what the lead said, did the owner get told). */
export type OptOutOrigem = "agente" | "operador" | "integracao";
export type OptOutTipo = "opt_out" | "reativacao";
export type OptOutNotificacaoStatus = "pendente" | "enviada" | "falhou";
export interface OptOutEvento {
  id: string;
  lead_ref: string | null;
  lead_nome: string | null;
  lead_telefone: string | null;
  thread_id: string | null;
  agent_id: string | null;
  agent_key: string | null;
  agent_nome: string | null;
  ator_user_id: string | null;
  /** `opt_out` (the lead asked to stop) or `reativacao` (an operator put the lead back in the agents flow). */
  tipo: OptOutTipo;
  origem: OptOutOrigem | string;
  motivo: string;
  mensagem_lead: string | null;
  em: string;
  participantes_encerrados: number;
  notificacao_status: OptOutNotificacaoStatus;
  notificacao_erro: string | null;
  notificado_em: string | null;
}
