/**
 * Agent Studio — TS mirror of the HTTP contract.
 *
 * Source: `products/agents/projects/agent-studio-isaia/CONTRACT.md`
 *   §C  (compiler output: `CompiledPrompt`, `ManifestSection`, `OnDemandItem`)
 *   §D1 (agents & versions)
 *   §D2 (clients)
 *
 * Field names are the contract's, byte-for-byte — this file is the FE side of
 * that contract, not a view model. FE-DEF authors it; FE-KE imports it
 * read-only (FE-KE-only shapes live in `types-ke.ts`, §J).
 *
 * Wire notes:
 *   - Every error arrives FLAT as `{detail, code, ...extra}` — the seed
 *     `http_exception_handler` passes a `{"detail", "code"}` dict through
 *     verbatim, so the extra keys of a 409 (`hash_atual`, `ultima_execucao`,
 *     `avisos`) sit next to `code` on `ApiError.body`. See `PublishErrorBody`.
 *   - Timestamps are ISO-8601 strings; UUIDs are strings.
 */

// ── Enumerations (contract §B1 CHECKs / §A10 allowlist) ───────────────────────

export const STUDIO_MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"] as const;
export type StudioModel = (typeof STUDIO_MODELS)[number];

export const STUDIO_EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;
export type StudioEffort = (typeof STUDIO_EFFORTS)[number];

export type DefinitionMode = "legacy" | "studio";

export type VersionStatus = "rascunho" | "ativa" | "substituida";

export const CLIENT_ENTRY_TIPOS = [
  "marca",
  "publico",
  "posicionamento",
  "trava",
  "decisao",
  "aprendizado",
  "evidencia",
  "nota",
] as const;
export type ClientEntryTipo = (typeof CLIENT_ENTRY_TIPOS)[number];

export type ClientEntryStatus = "ativo" | "arquivado";

/** §B1 `max_turns` CHECK. */
export const MAX_TURNS_MIN = 1;
export const MAX_TURNS_MAX = 200;
/** §B1 `agent_skills.nome` / `descricao` CHECKs. */
export const SKILL_NOME_MAX = 64;
export const SKILL_DESCRICAO_MAX = 1024;
/** §B1 slug-shaped CHECK used by `chave`, skill `nome`, client `slug`, agent `key`. */
export const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
/** §B1 `agent_skill_files.caminho` CHECK (plus the `..` ban). */
export const CAMINHO_RE = /^[a-z0-9][a-z0-9._/-]*$/;
/** §H4 — override reason minimum length. */
export const OVERRIDE_REASON_MIN = 20;

// ── §D1 · Agents ──────────────────────────────────────────────────────────────

export interface ToolPolicy {
  web_search: boolean;
  knowledge: boolean;
}

export interface AgentSummary {
  id: string;
  key: string;
  nome: string;
  descricao: string | null;
  definition_mode: DefinitionMode;
  ativo: boolean;
  publicacao_limiar: number;
  versao_ativa: number | null;
  tem_rascunho: boolean;
}

export interface AgentListResponse {
  items: AgentSummary[];
}

export interface VersionSummary {
  id: string;
  versao: number;
  status: VersionStatus;
  notas: string | null;
  model: StudioModel;
  created_at: string;
  published_at: string | null;
  compiled_hash: string | null;
  eval_score: number | null;
}

/** `GET /api/studio/agents/{key}` — `versoes` newest first. */
export interface AgentDetail extends AgentSummary {
  versoes: VersionSummary[];
}

export interface AgentCreateInput {
  key: string;
  nome: string;
  descricao?: string;
}

export interface AgentPatchInput {
  nome?: string;
  descricao?: string;
  ativo?: boolean;
  publicacao_limiar?: number;
}

// ── §D1 · Versions ────────────────────────────────────────────────────────────

export interface Section {
  id: string;
  chave: string;
  titulo: string;
  ordem: number;
  conteudo: string;
  ativo: boolean;
}

export interface SkillFileSummary {
  id: string;
  caminho: string;
  titulo: string | null;
  chars: number;
}

export interface Skill {
  id: string;
  nome: string;
  descricao: string;
  corpo: string;
  ordem: number;
  ativo: boolean;
  arquivos: SkillFileSummary[];
}

export interface VersionDetail extends VersionSummary {
  effort: StudioEffort;
  max_turns: number;
  idioma: string;
  tool_policy: ToolPolicy;
  based_on_version_id: string | null;
  published_by: string | null;
  publish_override_reason: string | null;
  eval_run_id: string | null;
  secoes: Section[];
  skills: Skill[];
  /** Additive (backend hardening, not yet in §D1's table) — the
   * `publicacao_limiar` value the gate actually compared `eval_score`
   * against at publish time (the agent-level limiar can change after
   * publish; this is the frozen value for THIS version). */
  limiar_aplicado?: number | null;
}

export interface DraftCreateInput {
  from_version_id?: string;
}

export interface DraftPatchInput {
  notas?: string | null;
  model?: StudioModel;
  effort?: StudioEffort;
  max_turns?: number;
  idioma?: string;
  tool_policy?: ToolPolicy;
}

/** `PUT .../draft/sections` item — `id` omitted for a new section. Full replace. */
export interface SectionInput {
  id?: string;
  chave: string;
  titulo: string;
  ordem: number;
  conteudo: string;
  ativo: boolean;
}

export interface SectionsReplaceInput {
  secoes: SectionInput[];
}

export interface SkillCreateInput {
  nome: string;
  descricao: string;
  corpo: string;
  ordem?: number;
  ativo?: boolean;
}

export type SkillPatchInput = Partial<Pick<Skill, "nome" | "descricao" | "corpo" | "ordem" | "ativo">>;

/** `PUT .../draft/skills/{skill_id}/files` — upsert by `caminho`. */
export interface SkillFileUpsertInput {
  caminho: string;
  titulo?: string | null;
  conteudo: string;
}

/** `GET .../skills/{skill_id}/files/{file_id}`. */
export interface SkillFile {
  id: string;
  caminho: string;
  titulo: string | null;
  conteudo: string;
}

export interface PublishInput {
  notas?: string;
  override_reason?: string;
}

// ─── Batch skill-file upload (multi-file, CONTRACT.md §G item 2) ───────────

/** One `arquivos[]` entry of `skillFilesBatchPath` — `@/api/studio/batchPaths.ts`. */
export interface SkillFileBatchItem {
  caminho: string;
  titulo?: string | null;
  conteudo: string;
}

/** Confirmed against the landed backend — NO `"inalterado"` for skill files
 * (unlike the knowledge documents batch, which does have one). */
export type SkillFileBatchStatus = "criado" | "atualizado" | "erro";

export interface SkillFileBatchResult {
  caminho: string;
  status: SkillFileBatchStatus;
  id?: string;
  titulo?: string;
  chars?: number;
  erro?: string;
}

/** No `inalterados` tally (matches the landed response shape — the status
 * enum itself has no `"inalterado"` to count). A whole-call 409
 * `version_immutable` (the version is no longer a rascunho) throws instead
 * of resolving this shape — never a per-item failure. */
export interface SkillFilesBatchResponse {
  resultados: SkillFileBatchResult[];
  criados: number;
  atualizados: number;
  erros: number;
}

// ── §C · Compiled prompt ──────────────────────────────────────────────────────

export interface ManifestOrigin {
  tipo: "secao" | "auto";
  id: string | null;
  campo: string | null;
}

/**
 * `inicio`/`fim` are character offsets into `texto`, counted as Python
 * `len(str)` does — Unicode CODE POINTS. JS `.slice`/`.length` count UTF-16
 * code UNITS instead (an astral character, e.g. most emoji, is a surrogate
 * pair — 2 JS units, 1 backend offset), so `texto.slice(inicio, fim)` drifts
 * once an astral character precedes the offset. Slice with
 * `Array.from(texto).slice(inicio, fim).join("")` (see `segmentCompiled` in
 * `components/studio/compiledSegments.ts`), never `texto.slice` directly.
 */
export interface ManifestSection {
  chave: string;
  titulo: string;
  origem: ManifestOrigin;
  inicio: number;
  fim: number;
  chars: number;
  tokens: number;
}

export interface OnDemandItem {
  tipo: "skill" | "arquivo_skill" | "colecao";
  nome: string;
  caminho: string | null;
  chars: number;
  tokens: number;
  gatilho: string;
}

export interface CompileWarning {
  codigo: string;
  mensagem: string;
  bloqueante: boolean;
}

/** `GET .../versions/{vid}/compiled?client_id=`. */
export interface CompiledOut {
  texto: string;
  hash: string;
  tokens_estimados: number;
  manifest: ManifestSection[];
  sob_demanda: OnDemandItem[];
  avisos: CompileWarning[];
  version_id: string;
  client_id: string | null;
}

/** `GET /api/studio/prompts/{hash}` — the stored, write-once text (§A7). */
export interface StoredPrompt {
  hash: string;
  texto: string;
  manifest: ManifestSection[];
  version_id: string;
  client_id: string | null;
  created_at: string;
}

// ── §D1 · Diff ────────────────────────────────────────────────────────────────

export type DiffState = "igual" | "alterada" | "nova" | "removida";

export interface VersionDiff {
  a: { version_id: string; hash: string };
  b: { version_id: string; hash: string };
  texto_a: string;
  texto_b: string;
  secoes: { chave: string; estado: DiffState }[];
  skills: { nome: string; estado: DiffState }[];
  configuracoes: { campo: string; a: unknown; b: unknown }[];
}

// ── §D1 · Publish errors (409 bodies, flat — see header) ──────────────────────

export interface GateLastRun {
  id: string;
  score: number | null;
  limiar: number;
  compiled_hash: string;
}

export interface PublishErrorBody {
  detail: string;
  /** `draft_changed` (backend hardening, additive): the draft's
   * `compiled_hash` moved between the eval run that satisfied the gate and
   * the publish call — recompiling produces a fresh hash to re-gate. */
  code: "eval_required" | "compile_blocked" | "version_immutable" | "draft_changed" | string;
  hash_atual?: string;
  ultima_execucao?: GateLastRun | null;
  avisos?: CompileWarning[];
}

// ── §D2 · Clients ─────────────────────────────────────────────────────────────

export interface ClientEntry {
  id: string;
  tipo: ClientEntryTipo;
  titulo: string;
  conteudo: string;
  status: ClientEntryStatus;
  created_at: string;
}

export interface ClientSummary {
  id: string;
  slug: string;
  nome: string;
  resumo: string;
  ativo: boolean;
  total_entradas: number;
}

export interface ClientListResponse {
  items: ClientSummary[];
}

export interface Client {
  id: string;
  slug: string;
  nome: string;
  resumo: string;
  ativo: boolean;
  entradas: ClientEntry[];
}

/*
 * §D2 names the routes and the `Client` shape but not the request bodies.
 * These are the §B1 `agent_clients` / `agent_client_entries` writable columns
 * (the only fields the tables hold); BE-DEF's `StrictHttpModel` is the arbiter.
 */
export interface ClientCreateInput {
  slug: string;
  nome: string;
  resumo?: string;
  ativo?: boolean;
}

export type ClientPatchInput = Partial<Pick<Client, "slug" | "nome" | "resumo" | "ativo">>;

export interface ClientEntryCreateInput {
  tipo: ClientEntryTipo;
  titulo: string;
  conteudo?: string;
}

export type ClientEntryPatchInput = Partial<Pick<ClientEntry, "tipo" | "titulo" | "conteudo" | "status">>;
