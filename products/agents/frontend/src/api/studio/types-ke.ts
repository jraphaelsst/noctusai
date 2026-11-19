/**
 * TS mirror of the Agent Studio CONTRACT.md slices owned by FE-KE — §D3
 * (Knowledge), §D4 (Evals), and the §D6 conversation/message field
 * additions the Conversar tab needs. §D2 (Clients) is FE-DEF's — see
 * `../types.ts` — now that both slices share one tree (FE-FIX collapse,
 * `hooks/studio/useClients.ts` is the one client hooks module).
 *
 * Field names are copied VERBATIM from CONTRACT.md — never renamed to a
 * "nicer" JS convention.
 */

// ─── §D3 Knowledge ──────────────────────────────────────────────────────────

export interface KnowledgeCollection {
  id: string;
  slug: string;
  nome: string;
  tag: string | null;
  descricao: string;
  ordem: number;
  total_documentos: number;
}

export interface KnowledgeCollectionsResponse {
  colecoes: KnowledgeCollection[];
}

export type KnowledgeCollectionCreate = {
  slug: string;
  nome: string;
  tag?: string | null;
  descricao?: string;
  ordem?: number;
};

export type KnowledgeCollectionPatch = Partial<
  Omit<KnowledgeCollectionCreate, "slug">
>;

export const DOCUMENT_TIPOS = ["fonte", "sintese", "card", "template", "indice", "outro"] as const;
export type DocumentTipo = (typeof DOCUMENT_TIPOS)[number];

export interface DocumentListItem {
  id: string;
  slug: string;
  titulo: string;
  tipo: DocumentTipo;
  resumo: string | null;
  chars: number;
  ativo: boolean;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
}

export interface Provenance {
  autor?: string;
  origem?: string;
  referencia?: string;
  pagina?: string;
  licenca?: string;
  notas?: string;
}

export interface Document {
  id: string;
  collection_id: string;
  slug: string;
  titulo: string;
  tipo: DocumentTipo;
  resumo: string | null;
  conteudo: string;
  proveniencia: Provenance;
  ativo: boolean;
  chars: number;
  updated_at: string;
}

export type DocumentCreate = {
  slug: string;
  titulo: string;
  tipo: DocumentTipo;
  conteudo: string;
  resumo?: string;
  proveniencia?: Provenance;
};

export type DocumentPatch = Partial<Omit<DocumentCreate, "slug">> & {
  ativo?: boolean;
  motivo?: string;
};

export interface DocumentRevision {
  id: string;
  op: "create" | "update" | "archive" | "import";
  motivo: string | null;
  author_id: string | null;
  created_at: string;
}

export interface DocumentRevisionsResponse {
  items: DocumentRevision[];
}

export interface KnowledgeSearchResult {
  doc_id: string;
  slug: string;
  titulo: string;
  colecao: string;
  tag: string | null;
  tipo: DocumentTipo;
  trecho: string;
  rank: number;
}

export interface KnowledgeSearchResponse {
  items: KnowledgeSearchResult[];
}

// ─── Batch document upload (multi-file, CONTRACT.md §G item 1) ────────────

/**
 * One `documentos[]` entry of `knowledgeDocumentsBatchPath` —
 * `@/api/studio/batchPaths.ts`. `proveniencia` is the SAME structured
 * `Provenance` object as `DocumentCreate.proveniencia` (confirmed against
 * the landed backend — a flat string is rejected). The audit's example
 * front matter shows a single scalar line (`proveniencia: "Curso Audience
 * — aula 1"`); the uploader maps that string onto `Provenance.origem`
 * (`KnowledgeUploadDialog.tsx`) rather than inventing a new front-matter
 * shape for structured provenance.
 */
export interface KnowledgeDocumentBatchItem {
  slug: string;
  titulo: string;
  tipo: DocumentTipo;
  conteudo: string;
  resumo?: string;
  proveniencia?: Provenance;
}

export type KnowledgeDocumentBatchStatus = "criado" | "atualizado" | "inalterado" | "erro";

export interface KnowledgeDocumentBatchResult {
  slug: string;
  status: KnowledgeDocumentBatchStatus;
  doc_id?: string;
  erro?: string;
}

export interface KnowledgeDocumentsBatchResponse {
  resultados: KnowledgeDocumentBatchResult[];
  criados: number;
  atualizados: number;
  inalterados: number;
  erros: number;
}

// ─── §D4 Evals ──────────────────────────────────────────────────────────────

export interface EvalCriterios {
  deve: string[];
  nao_deve: string[];
}

export interface EvalCase {
  id: string;
  slug: string;
  titulo: string;
  entrada: string;
  contexto: string | null;
  criterios: EvalCriterios;
  rubrica: string | null;
  tags: string[];
  ativo: boolean;
}

export interface EvalCaseListResponse {
  items: EvalCase[];
}

export type EvalCaseCreate = Omit<EvalCase, "id">;
/** Slug identifies the case and is never patched (§D4 `PATCH .../evals/cases/{case_id}`). */
export type EvalCasePatch = Partial<Omit<EvalCaseCreate, "slug">>;

/** `erro` = no case produced a verdict (the run could not measure anything: score `null`, never 0); `parcial_com_erros` =
 * some cases errored and the score is over the ones that were measured. Neither is `concluida`. */
export type EvalRunStatus =
  | "pendente"
  | "executando"
  | "concluida"
  | "falhou"
  | "cancelada"
  | "erro"
  | "parcial_com_erros";

export interface EvalRun {
  id: string;
  version_id: string;
  compiled_hash: string;
  status: EvalRunStatus;
  total: number;
  aprovados: number;
  score: number | null;
  limiar: number;
  started_at: string | null;
  finished_at: string | null;
  erro: string | null;
  /** Additive (backend hardening, not yet in §D4's table) — true once every
   * case in the run has a terminal result (`aprovado`/`reprovado`/`erro`),
   * distinct from `status === "concluida"` when the run itself was
   * cancelled mid-way with some results already in. Also `false` for a run
   * the cost cap cut short (§L), even one created over every active case. */
  completa?: boolean;
  /** Contract §L (additive): `null` = the version's own model ran (the
   * publish-gate-eligible shape); otherwise the cheaper-iteration override
   * — a run with this set never satisfies the publish gate. */
  modelo_geracao: EvalRunModel | null;
  /** Contract §L (additive): this run's cost cap in USD. */
  limite_usd: number | null;
  /** Contract §L (additive): the run's accumulated cost (generator + judge,
   * summed over every result) — `null` until the runner has written at
   * least one result. */
  custo_usd: number | null;
  /** Migration 088 (additive): the first errored case's code (e.g. `qualificacao_indisponivel`) and how many cases errored. */
  erro_codigo?: string | null;
  casos_com_erro?: number;
}

/** Live progress of one run (either suite): every number is the server's. `indeterminado` = the mechanism suite while it
 * executes (it stores its executions when it ends) — only status, elapsed time and the cost cap are known then. */
export interface RunProgresso {
  run_id: string;
  suite: EvalLoopSuite;
  status: EvalRunStatus | string;
  ativo: boolean;
  indeterminado: boolean;
  total: number | null;
  concluidos: number | null;
  aprovados: number | null;
  reprovados: number | null;
  erros: number | null;
  pulados: number | null;
  /** Mean score of the MEASURED cases (errored ones are out of the denominator); `null` = nothing measured yet. */
  score_parcial: number | null;
  custo_usd: number | null;
  limite_usd: number | null;
  started_at: string | null;
  finished_at: string | null;
  decorrido_s: number | null;
  eta_s: number | null;
  erro: string | null;
  erro_codigo: string | null;
}

/** Contract §L — deliberately NARROWER than `StudioModel` (`../types.ts`):
 * exists to let a cheaper-iteration run cost LESS than the version's own
 * model, never more. */
export const EVAL_RUN_MODELS = ["claude-sonnet-5", "claude-haiku-4-5"] as const;
export type EvalRunModel = (typeof EVAL_RUN_MODELS)[number];

export interface EvalRunListResponse {
  items: EvalRun[];
}

export interface EvalVeredito {
  criterio: string;
  tipo: "deve" | "nao_deve";
  ok: boolean;
  motivo: string;
}

export interface EvalResult {
  case_id: string;
  case_slug: string;
  case_titulo: string;
  /** `"pulado"` (§L, additive) — the run's cost cap was reached before this
   * case started; `notas_juiz` carries the fixed reason string. */
  status: "pendente" | "aprovado" | "reprovado" | "erro" | "pulado";
  score: number | null;
  saida: string | null;
  veredito: EvalVeredito[] | null;
  notas_juiz: string | null;
  duracao_ms: number | null;
  /** Contract §L (additive): generator + judge cost of this case, summed. */
  custo_usd: number | null;
  tokens_entrada: number | null;
  tokens_saida: number | null;
  tokens_cache_leitura: number | null;
}

/** A case a default run did NOT execute: consolidated and unaffected by the change (queryable per run). */
export interface EvalCasoPulado {
  case_id: string;
  case_slug: string | null;
  estado: ConsolidacaoEstado;
  motivo: "consolidado_nao_afetado";
  sequencia: number;
  limite: number;
}

export interface EvalRunDetail extends EvalRun {
  resultados: EvalResult[];
  casos_pulados?: EvalCasoPulado[];
}

/** Eval consolidation (owner rule 2026-11-09): N consecutive passes (5 normal / 10 critico) consolidate a case;
 * an affected case is `revalidar` and needs 3 / 6. */
export type ConsolidacaoEstado = "em_validacao" | "consolidado" | "revalidar";

export interface ConsolidacaoCaso {
  case_id: string;
  slug: string;
  titulo: string | null;
  suite: "comportamento" | "mecanismo";
  ativo: boolean;
  criticidade: "normal" | "critico";
  criticidade_origem: "padrao" | "sugerida" | "definida";
  depende_de: string[] | null;
  depende_de_origem: "declarada" | "inferida" | null;
  estado: ConsolidacaoEstado;
  sequencia: number;
  limite: number;
}

export interface Consolidacao {
  config: Record<string, number>;
  contagem: Record<string, number>;
  items: ConsolidacaoCaso[];
}

export interface EvalRunCreate {
  version_id: string;
  /** Mutually exclusive with `repetir_falhas_de` (422). */
  case_ids?: string[];
  /** Contract §L: the cheaper-iteration model override. */
  modelo_geracao?: EvalRunModel;
  /** Contract §L: this run's cost cap in USD — omitted ⇒ the backend's
   * `STUDIO_EVAL_RUN_BUDGET_USD` default. */
  limite_usd?: number;
  /** Contract §L: rerun only the failures of a prior run of this agent.
   * Mutually exclusive with `case_ids` (422). */
  repetir_falhas_de?: string;
  /** Omitted/false: only cases that are NOT consolidated-and-unaffected run (the skipped ones are stored with the run).
   * True: run every active case (and the only way to get a publish-gate-eligible complete run). */
  rodar_tudo?: boolean;
  /** Eval-loop round: a whole-suite run stamped with the loop (docs/eval-loop-gate-contract.md). The server then
   * refuses `case_ids`, `repetir_falhas_de` and `modelo_geracao` (422) and clamps `limite_usd` to the budget left. */
  loop_id?: string;
}

// ─── Eval loops (products/agents/docs/eval-loop-gate-contract.md) ──────────

export type EvalLoopSuite = "comportamento" | "mecanismo";
export type EvalLoopStatus = "ativo" | "parado" | "concluido";
export type EvalLoopMotivoParada =
  | "alvo_atingido"
  | "sem_melhora"
  | "orcamento_atingido"
  | "rodadas_esgotadas"
  | "parado_manualmente"
  | "erro";
export type EvalLoopRodadaStatus = "executando" | "concluida" | "falhou" | "cancelada" | "erro" | "parcial_com_erros";
/** What the loop is doing right now (server-derived): a round is open | between rounds (automatic) | idle waiting for a
 * draft edit | waiting for the owner's click | ended. */
export type EvalLoopEstadoDriver = "rodando" | "automatico" | "aguardando_edicao" | "manual" | "encerrado";
export type EvalLoopModo = "automatico" | "manual";

/** What the refine step did AFTER a round (`docs/eval-loop-gate-contract.md` § Refine step): one bounded draft-row edit
 * (`proposto`) or nothing written (`recusado`, with `codigo` + `mensagem`). `diff` is the changed window of the row; the
 * full before/after texts are in the loop events. `melhorou` is set once the next round closed (`avaliado`). */
export interface EvalLoopRefinamento {
  estado: "proposto" | "recusado";
  custo_usd: number;
  modelo: string | null;
  codigo: string | null;
  mensagem: string | null;
  alvo: { tipo: "secao" | "texto" | "ferramenta"; chave: string } | null;
  racional: string | null;
  casos_alvo: string[];
  diff: { antes: string; depois: string } | null;
  avaliado: boolean;
  melhorou: boolean | null;
  score_antes: number | null;
  score_depois: number | null;
}

export interface EvalLoopRefinamentosResumo {
  propostos: number;
  recusados: number;
  avaliados: number;
  melhoraram: number;
  custo_usd: number;
}

export interface EvalLoopRodada {
  rodada: number;
  run_id: string;
  status: EvalLoopRodadaStatus;
  score: number | null;
  custo_usd: number;
  compiled_hash: string | null;
  melhorou: boolean | null;
  overcall: boolean;
  falhas: string[];
  /** A round whose run ERRORED says why — shown as an error, never as failing cases. */
  erro_codigo?: string | null;
  erro_mensagem?: string | null;
  /** The refine decided AFTER this round (based on its failures); `null`/absent = none ran. */
  refinamento?: EvalLoopRefinamento | null;
}

export interface EvalLoopOvercall {
  rodada: number;
  run_id: string;
  score: number | null;
  custo_usd: number;
}

export interface EvalLoopCheckpoint {
  rodada: 5 | 10 | 15;
  atingido: boolean;
  score: number | null;
  gasto_usd: number | null;
  /** Refines proposed up to this round / what the refine step cost up to it. */
  refinamentos?: number;
  gasto_refino_usd?: number;
}

/** `sem_melhora` carries the hash comparison; other motives may send `null` or an arbitrary object. */
export interface EvalLoopDetalheParada {
  seguidas?: number;
  hash_anterior?: string | null;
  hash_atual?: string | null;
  conteudo_mudou?: boolean;
  partes_alteradas?: string[];
  [k: string]: unknown;
}

export interface EvalLoop {
  id: string;
  agente_chave: string;
  suite: EvalLoopSuite;
  status: EvalLoopStatus;
  motivo_parada: EvalLoopMotivoParada | null;
  detalhe_parada: EvalLoopDetalheParada | null;
  rodadas_planejadas: number;
  rodadas_feitas: number;
  alvo: number;
  piso: number;
  orcamento_usd: number;
  gasto_usd: number;
  restante_usd: number;
  melhor_score: number | null;
  score_atual: number | null;
  acima_do_piso: boolean | null;
  started_at: string;
  stopped_at: string | null;
  serie: EvalLoopRodada[];
  overcalls: EvalLoopOvercall[];
  custo_overcalls_usd: number;
  checkpoints: EvalLoopCheckpoint[];
  modo?: EvalLoopModo;
  /** Why an automatic loop is idle right now (e.g. `hash_inalterado`: the content did not change); `null` = nothing to say. */
  aviso?: { codigo: string; mensagem: string } | null;
  estado_driver?: EvalLoopEstadoDriver;
  /** Totals of the refine step between rounds (its cost is INCLUDED in `gasto_usd`). */
  refinamentos?: EvalLoopRefinamentosResumo;
}

export interface EvalLoopListResponse {
  items: EvalLoop[];
}

export interface EvalLoopCreate {
  suite: EvalLoopSuite;
  /** Omitted ⇒ the platform loop config's `rodadas_max`; above it ⇒ 422. */
  rodadas_planejadas?: number;
  /** Omitted ⇒ the platform loop config's `orcamento_usd` (a cap); above it ⇒ 422. */
  orcamento_usd?: number;
  /** `automatico` (default on the server) = the server runs the rounds by itself until a stop condition. */
  modo?: EvalLoopModo;
}

/** Platform-level loop config (GET/PUT, platform admin): the target, the budget cap and the max rounds every loop uses. */
export interface EvalLoopConfig {
  alvo: number;
  orcamento_usd: number;
  rodadas_max: number;
  alterado_por: string | null;
  alterado_em: string | null;
}
export type EvalLoopConfigInput = Omit<EvalLoopConfig, "alterado_por" | "alterado_em">;

// §D2 Clients: collapsed into FE-DEF's `../types.ts` (`Client`,
// `ClientSummary`, `ClientCreateInput`, `ClientPatchInput`, `ClientEntry`,
// `ClientEntryTipo`, `ClientEntryCreateInput`, `ClientEntryPatchInput`) now
// that both slices share one tree — see `hooks/studio/useClients.ts`. The
// duplicate reader (`ClientListItem`/`ClientDetail`/`ClientCreate`/
// `ClientPatch`/`ClientEntryCreate`/`ClientEntryPatch`, and the
// now-superseded `useClientsKe.ts`) is gone; every consumer imports the
// FE-DEF shapes directly.

// ─── §D6 Conversations/messages — studio field additions ───────────────────

export interface StudioConversation {
  id: string;
  agent_id: string;
  agent_key: string;
  owner_user_id: string;
  titulo: string | null;
  sdk_session_id: string | null;
  status: string;
  version_id: string | null;
  client_id: string | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StudioMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  texto: string;
  blocks: unknown[];
  version_id: string | null;
  compiled_hash: string | null;
  token_usage: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  /** Contract §L (additive): an assistant message's turn cost/token counts
   * (SDK ResultMessage) — `null` for user/system rows and for any turn
   * that reported no ResultMessage. */
  custo_usd: number | null;
  tokens_entrada: number | null;
  tokens_saida: number | null;
}

export interface Envelope<T> {
  items: T[];
  total: number;
}
