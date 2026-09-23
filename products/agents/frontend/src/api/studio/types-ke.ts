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

export type EvalRunStatus = "pendente" | "executando" | "concluida" | "falhou" | "cancelada";

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

export interface EvalRunDetail extends EvalRun {
  resultados: EvalResult[];
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
}

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
