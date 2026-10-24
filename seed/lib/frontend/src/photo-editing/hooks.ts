/**
 * Edição de Fotos — TanStack Query hook factory.
 *
 * Wraps `/api/edicao-fotos/...` per
 * `projects/edicao-fotos/EDICAO-FOTOS-CONTRACT.md`. Same shape as `../llm.ts`:
 * `api` is injected so each product's own `createApiClient()` (already
 * authenticated + backend-configured) drives every call — this module owns
 * zero fetch/auth logic of its own.
 *
 * Seed-portable by design: no Social-Wiring coupling anywhere in this file.
 * The owner's phase-2 plan rebuilds the engine in a separate app using this
 * seed feature as the code reference — these hooks travel unchanged; only
 * the `api` client passed in at call time changes.
 *
 * Loading-state contract (CLAUDE.md §1 · `KB § PATTERNS/frontend/lying-loading-state.md`,
 * binding per contract §9): every read hook below returns `showSkeleton` /
 * `isRefreshing` ALREADY COMPUTED —
 *   `showSkeleton = isPending && !data`
 *   `isRefreshing = isFetching && !!data`
 * — so consumers never touch `.isLoading`. Computed HERE (the hook), not
 * per-consumer, so every page gets the correct gate for free. Batch/review
 * queries key on `loteId`; `placeholderData` keeps a key change from
 * unmounting a grid that already has content (contract §9, last line).
 *
 * Scope: originally just the S9 seed organs' routes (capacidades, review +
 * decisions, reference pool). W10a (SW frontend, `pages/edicao-fotos/`)
 * extended this SAME factory with lotes CRUD/upload/vista/submeter/zip and
 * configurações/modelos — per `CLAUDE.md` §1 "products consume canonical
 * organs" this is the required shape (extend, never fork). W6 extended it
 * again with the reference-pool upload (multipart), guias de estilo and the
 * platform settings the pool limit lives in. W7 extended it again with the
 * per-agency learning loop (`/regras`) + the effective-guide view; the
 * notifications slice added curadores (`photo_curator` grants) and
 * notificacoes/preferencias (per-user opt-in, plan §1 "Notifications"); W8
 * added the model catalog admin (rows, versions, per-step models, note
 * rewrite) and the processing panel (pause switch, health, OpenAI probe);
 * W9 added the dashboard (`/painel`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { pageOps } from '../organ-kit/page-ops';
import { handOffToPolling, jobPolling } from '../job-polling';
import type { ApiClient } from '../api';

// ---------------------------------------------------------------------------
// Types — mirror EDICAO-FOTOS-CONTRACT.md response/request shapes
// ---------------------------------------------------------------------------

/**
 * Contract §2 `GET /capacidades`. Server-computed; drives every FE gate.
 * NEVER derive any of these from SSO metadata — see `./permissions.ts`.
 */
export interface Capacidades {
  pode_criar_lote: boolean;
  pode_ver_veredito: boolean;
  pode_gerir_pool: boolean;
  pode_aprovar_regras: boolean;
  pode_ativar_guia: boolean;
  dashboard: 'org' | 'platform' | null;
  modelo_configurado: boolean;
  /**
   * Why a configured image model still cannot run (W8): `sem_modelo`,
   * `modelo_desativado` (switched off in the catalog) or `modelo_sem_preco`
   * (a rate is missing). `null` when the model is usable.
   */
  modelo_bloqueado_motivo?: 'sem_modelo' | 'modelo_desativado' | 'modelo_sem_preco' | null;
  /** Platform admin: may open the model catalog + processing admin pages (W8). */
  pode_administrar_plataforma?: boolean;
  economico_disponivel: boolean;
  economico_bloqueado_motivo: string | null;
  tipos_edicao_ativos: string[];
  limites: { fotos_por_lote: number; bytes_por_foto: number };
}

/** Contract §3 — photo state machine; every transition writes `fotos_eventos`. */
export type EstadoFoto =
  | 'recebida'
  | 'normalizando'
  | 'pronta'
  | 'editando'
  | 'em_lote_openai'
  | 'editada'
  | 'avaliando'
  | 'aguardando_decisao'
  | 'aprovada'
  | 'rejeitada'
  | 'falhou';

export type DecisaoTipo = 'aprovar' | 'rejeitar';

/**
 * Contract §1 — the AI verdict. Hidden from corretores by TABLE SEPARATION
 * server-side (`fotos_avaliacoes` is its own table so RLS withholds the
 * whole row), not by field omission — a response shape that merely omits
 * this field would be a leak waiting for a refactor. `undefined` on
 * `FotoRevisao.avaliacao` means "not visible to this role", never "not yet
 * evaluated" (an unevaluated photo simply hasn't reached `aguardando_decisao`).
 */
export interface AvaliacaoIA {
  veredito: DecisaoTipo;
  /** 0-10 (contract §2 "My technical calls"). */
  score: number;
  motivo: string;
}

/**
 * One photo row from `GET /revisao/{lote_id}` (contract §4). `avaliacao` is
 * present ONLY when the caller's `capacidades.pode_ver_veredito` is true.
 */
export interface FotoRevisao {
  id: string;
  url_antes: string;
  url_depois: string | null;
  comodo?: string | null;
  estado: EstadoFoto;
  /** Present when `estado === 'falhou'` — technical failure, not a quality rejection (contract §3). */
  falha_motivo?: string | null;
  decisao: DecisaoTipo | null;
  /** Required by the backend when `decisao === 'rejeitar'` (422 otherwise — contract §4). */
  comentario: string | null;
  avaliacao?: AvaliacaoIA | null;
}

export interface DecisaoBody {
  decisao: DecisaoTipo;
  /** Required when `decisao === 'rejeitar'`; null otherwise. */
  comentario: string | null;
}

/** Contract §5 — reference pool pair (platform scope, not `org_id`-scoped). */
export interface ReferenciaPar {
  id: string;
  /** Short-lived signed URL (the pool bucket is private). */
  antes_url: string;
  /** Short-lived signed URL (the pool bucket is private). */
  depois_url: string;
  comodo: string;
  tipos_edicao: string[];
  nota: string | null;
  /** Set once archived — archived pairs are kept for history and excluded from the pair-limit count (contract §5). */
  arquivada_em?: string | null;
  criado_em?: string | null;
  criado_por?: string | null;
}

/**
 * `POST /referencias` — multipart: the two image FILES plus the tags
 * (contract §5). Sent via `api.upload`, never `api.post` (FormData through
 * `post` silently becomes `{}` — see `../api.ts`).
 */
export interface NovaReferenciaBody {
  antes: File;
  depois: File;
  /** One of `ReferenciasPage.opcoes.comodos` (fixed list). */
  comodo: string;
  /** Subset of `ReferenciasPage.opcoes.tipos_edicao`. */
  tipos_edicao: string[];
  nota?: string | null;
}

/** Pool occupancy — the limit is counted in PAIRS; `limite_pares: null` = unlimited (contract §5). */
export interface PoolReferencias {
  pares_ativos: number;
  limite_pares: number | null;
  /** `true` ⇒ uploads are refused with 409 `pool_cheio` until a pair is archived or the limit raised. */
  cheio: boolean;
}

/** `GET /referencias` — paginated pairs + pool occupancy + the fixed upload vocabularies. */
export interface ReferenciasPage {
  items: ReferenciaPar[];
  page: number;
  page_size: number;
  total: number;
  pool: PoolReferencias;
  opcoes: { comodos: string[]; tipos_edicao: string[] };
}

/** Contract §6 — style-guide version lifecycle. */
export type GuiaStatus = 'rascunho' | 'ativa' | 'substituida';

/** How a version came to be: AI builder, hand-written, or a restore (clone of an older version). */
export type GuiaOrigem = 'ia' | 'manual' | 'restaurada';

/** One company style-guide version (contract §6). Versions are immutable. */
export interface GuiaEstiloVersao {
  id: string;
  versao: number;
  status: GuiaStatus;
  texto: string;
  sha256: string;
  gerado_de_versao: number | null;
  origem: GuiaOrigem;
  criado_por: string | null;
  criado_em: string | null;
  ativado_por: string | null;
  ativado_em: string | null;
}

/** `GET /guias` — versions newest first + the active version number (null = none active ⇒ batches cannot be submitted). */
export interface GuiasPage {
  items: GuiaEstiloVersao[];
  page: number;
  page_size: number;
  total: number;
  versao_ativa: number | null;
}

/** `POST /guias` — a manually written DRAFT (activation is a separate call). */
export interface NovoGuiaBody {
  texto: string;
}

/** `POST /guias/regenerar` → 202: the AI rebuild was queued; the draft shows up in `GET /guias` once it runs. */
export interface RegenerarGuiaResposta {
  job_id: string;
  status: string;
}

/** `GET|PUT /configuracoes/plataforma` (contract §8) — platform admin only. */
export interface PlataformaConfiguracoes {
  velocidade_default: LoteVelocidade;
  notificacoes_globais_ativas: boolean;
  /** Decimal as string (USD per GB-month); null = not configured. */
  preco_storage_gb_mes_usd: string | null;
  /** Reference-pool limit in pairs; null (or 0 on write) = unlimited. */
  limite_pares_referencia: number | null;
  /**
   * Rule-proposer tunables (W7 panel, contract §7) — `fotos_platform_settings`
   * columns since SW 130 (W8). `GET` returns the effective value; `PUT`
   * writes them only when sent (0-604800 s / 1-500), `null` = engine default.
   * Optional so an older client that omits them never resets them.
   */
  rule_proposal_debounce_seconds?: number | null;
  max_rejections_per_proposal?: number | null;
}

/** Contract §7 — status of a per-agency "don't do this" rule. */
export type RegraStatus = 'proposta' | 'aprovada' | 'rejeitada';

/**
 * One learning rule (contract §7). Manual create (`POST /regras`) lands
 * directly `aprovada` — the admin writing it down IS the approval;
 * "archive" reuses `POST /{id}/rejeitar`. `override_platform_admin` is set
 * the moment a SECOND decided-state change happens — i.e. someone (always
 * a platform admin) is overriding a prior decision.
 */
export interface RegraOrg {
  id: string;
  texto: string;
  status: RegraStatus;
  /** `{decisao_id, foto_id, comentario}` snapshots the AI proposer drew this rule from; `[]` for a manual rule. */
  origem_comentarios: Array<Record<string, unknown>>;
  decidido_por: string | null;
  decidido_em: string | null;
  override_platform_admin: boolean;
  criado_em: string | null;
}

/** `GET /regras` — unpaginated (org-scoped rule counts stay small, same shape as `/curadores`). */
export interface RegrasPage {
  items: RegraOrg[];
  total: number;
}

/** `POST /regras` body — the manually written rule text. */
export interface NovaRegraBody {
  texto: string;
}

/** `POST /regras/propor-agora` → 202: the AI proposer was queued to run NOW. */
export interface ProporRegrasResposta {
  job_id: string;
  status: string;
}

/**
 * One effective-guide snapshot (contract §6/§7) — the composed company
 * guide + this org's APPROVED rules, versioned by content sha256, the SAME
 * shape `POST /lotes/{id}/submeter` freezes onto a batch.
 */
export interface GuiaEfetivo {
  id: string;
  guia_estilo_id: string;
  conjunto_regras_id: string | null;
  texto: string;
  sha256: string;
  criado_em: string | null;
}

/**
 * `GET /regras/guia-efetivo` — the CURRENT effective guide (`atual: null`
 * while no company guide is active yet — never an error) + this org's
 * version history, newest first.
 */
export interface GuiaEfetivoView {
  atual: GuiaEfetivo | null;
  historico: { items: GuiaEfetivo[]; page: number; page_size: number; total: number };
}

/** Contract §3 — speed mode (Urgente = sync; Econômico = Batch API, 50% off, ≤24h). */
export type LoteVelocidade = 'urgente' | 'economico';

/** Optional link to a Vista/CRM imóvel carried on a batch (contract §3 `POST /lotes` body). */
export interface LoteImovelRef {
  org_id: string;
  codigo: string;
}

/**
 * Aggregate batch status for the list view. NOT literally typed by the
 * contract (§3 lists routes, not the list-row shape) — inferred from the
 * per-photo state machine. 🔴 FLAG: the backend (built in parallel) may
 * compute + return a differently-named/shaped field — if `GET /lotes` ships
 * something else, update this type + `Lotes.tsx`'s badge mapping together.
 */
export type EstadoLoteAgregado = 'rascunho' | 'processando' | 'aguardando_revisao' | 'concluido' | 'com_falhas';

/** One row from `GET /lotes` (contract §3) — batch list. */
export interface LoteResumo {
  id: string;
  nome: string;
  criado_em: string;
  imovel: LoteImovelRef | null;
  velocidade: LoteVelocidade;
  estado_agregado: EstadoLoteAgregado;
  total_fotos: number;
  fotos_decididas: number;
}

/** Paginated envelope — contract §0 convention (`?page=&page_size=` → `{items,page,page_size,total}`). */
export interface LotesPage {
  items: LoteResumo[];
  page: number;
  page_size: number;
  total: number;
}

/** `POST /lotes` body (contract §3) — metadata only; photos follow via upload or Vista pull. */
export interface NovoLoteBody {
  nome: string;
  imovel: LoteImovelRef | null;
  /** Per-batch speed (W4). Omitted = the org default. `economico` needs `capacidades.economico_disponivel`. */
  velocidade?: LoteVelocidade;
}

/** `POST /lotes` response — minimal id so the caller can chain upload/vista/submeter. */
export interface LoteCriado {
  id: string;
  nome: string;
}

/**
 * `POST /lotes/{id}/vista` body (contract §10, C5 resolved) — `codigo` only;
 * `org_id` is resolved server-side from the session, never sent by the FE.
 */
export interface VistaLoteBody {
  codigo: string;
}

/** `GET /lotes/{id}` (contract §3) — batch header + per-photo state, reusing `FotoRevisao`. */
export interface LoteDetalhe {
  id: string;
  nome: string;
  velocidade: LoteVelocidade;
  imovel: LoteImovelRef | null;
  criado_em: string;
  fotos: FotoRevisao[];
}

/** `GET|PUT /configuracoes` (contract §8) — org edit types, image model, speed override. */
export interface OrgConfiguracoes {
  tipos_edicao_ativos: string[];
  modelo_editor_imagem: string | null;
  velocidade_padrao: LoteVelocidade;
  /** Plan §1 "Notifications" — the org-level on/off layer (agency admin ∨
   * platform admin); the platform switch lives on `PlataformaConfiguracoes`,
   * the per-user opt-in on `NotificacaoPreferencia`. */
  notificacoes_ativas: boolean;
}

/** `GET|POST /curadores` row — a `photo_curator` grant (Core
 * `public.user_permission_grants`), platform admin only. */
export interface Curador {
  user_id: string;
  nome: string | null;
  email: string | null;
  concedido_por: string | null;
  created_at: string | null;
}

/** `GET /curadores` — not paginated (the roster is small; platform admin only). */
export interface CuradoresPage {
  items: Curador[];
  total: number;
}

/** `POST /curadores` body — grants `photo_curator` to this user. */
export interface CuradorCreateBody {
  user_id: string;
}

/**
 * `GET|PUT /notificacoes/preferencias` — self-service per-user opt-in for
 * the "batch ready" notification (plan §1 "Notifications"). The creator of
 * a batch is ALWAYS notified regardless of `ativo`; this only decides
 * whether an AGENCY ADMIN also gets notified for batches they did not
 * create. `whatsapp_number` (E.164, e.g. `+5511999998888`) is used for
 * BOTH the WhatsApp channel when opted in AND — if this member later
 * creates a batch themselves — their own creator notification.
 */
export interface NotificacaoPreferencia {
  ativo: boolean;
  whatsapp_number: string | null;
}

export type TagPerformance = 'performance' | 'economico';

/**
 * `GET /modelos` (contract §8) — the EFFECTIVE image-model catalog (the
 * platform admin's overrides applied); drives Configuracoes' picker + the
 * Econômico lock. `metricas` / `nota_recomendacao` are `null` for callers
 * who may not see them (corretores) and while there is no data / no note.
 */
export interface ModeloCatalogoItem {
  id: string;
  nome: string;
  versao: string;
  tag_performance: TagPerformance | null;
  suporta_batch: boolean;
  /** `false` ⇒ a rate is missing; selecting this model is refused (W8). */
  com_preco?: boolean;
  nota_recomendacao: string | null;
  nota_gerada_em?: string | null;
  metricas: {
    total_fotos?: number;
    /** 0-1; null = no decided photo yet ("no data" is not "0%"). */
    taxa_aprovacao: number | null;
    score_medio_ia: number | null;
    /** USD; null while no photo was approved. */
    custo_por_foto_aprovada: number | null;
  } | null;
}

/** Per-1M-token USD rates of one model; `null` = no published rate. */
export interface ModeloPrecos {
  entrada_texto: number | null;
  saida_texto: number | null;
  entrada_imagem: number | null;
  saida_imagem: number | null;
}

export type ModeloKind = 'image_edit' | 'vision' | 'chat';

/** One row of `GET /modelos/catalogo` (platform admin, W8). */
export interface ModeloCatalogoAdmin {
  id: string;
  kind: ModeloKind;
  nome: string;
  descricao: string | null;
  snapshot: string | null;
  versao: string;
  habilitado: boolean;
  precos: ModeloPrecos;
  suporta_batch: boolean;
  tag_performance: TagPerformance | null;
  com_preco: boolean;
  /** `catalogo` = static row untouched · `personalizado` = static row edited · `adicionado` = operator-only row. */
  origem: 'catalogo' | 'personalizado' | 'adicionado';
  /** The static catalog's rates, for comparison (null for an added row). */
  precos_padrao: ModeloPrecos | null;
  /** Override version (null = never edited). */
  revisao: number | null;
  atualizado_em: string | null;
  atualizado_por: string | null;
}

export interface ModelosCatalogoPage {
  items: ModeloCatalogoAdmin[];
}

/**
 * `PUT /modelos/catalogo/{id}` — a FULL row. Prices travel as decimal
 * strings; `null` = "no rate" (the model is then refused where it would be
 * billed), never "keep the previous value".
 */
export interface ModeloCatalogoBody {
  kind: ModeloKind;
  nome: string | null;
  descricao: string | null;
  snapshot: string | null;
  habilitado: boolean;
  preco_entrada_texto_1m: string | null;
  preco_saida_texto_1m: string | null;
  preco_entrada_imagem_1m: string | null;
  preco_saida_imagem_1m: string | null;
  suporta_batch: boolean;
  tag_performance: TagPerformance | null;
}

/** `PUT` answer: the saved row + whether this server already serves it. */
export interface ModeloCatalogoSalvo extends ModeloCatalogoAdmin {
  recarregado: boolean;
}

/** One immutable history row of a model (`GET /modelos/catalogo/{id}/versoes`). */
export interface ModeloCatalogoVersao {
  revisao: number;
  habilitado: boolean;
  nome: string | null;
  snapshot: string | null;
  precos: ModeloPrecos;
  suporta_batch: boolean;
  tag_performance: TagPerformance | null;
  atualizado_em: string | null;
  atualizado_por: string | null;
}

export type EtapaModelo = 'guia' | 'avaliador' | 'regras' | 'notas';

/** `GET|PUT /modelos/etapas` — the model each engine step calls. */
export interface ModelosEtapas {
  etapas: {
    etapa: EtapaModelo;
    tipo: 'vision' | 'chat';
    modelo: string;
    padrao: string;
    personalizado: boolean;
  }[];
}

/** `PUT /modelos/etapas` — only keys sent are written; `null` = back to the default. */
export type ModelosEtapasBody = Partial<Record<EtapaModelo, string | null>>;

export type SondaStatus = 'ok' | 'sem_credito' | 'chave_invalida' | 'sem_chave' | 'limite' | 'erro';

/** `POST /processamento/sonda` — OpenAI key/credit probe (costs one token). */
export interface SondaResultado {
  status: SondaStatus;
  mensagem: string;
  verificado_em: string | null;
  modelo: string | null;
  http_status: number | null;
}

/** `GET|PUT /processamento` — the worker's switch + health (platform admin, W8). */
export interface ProcessamentoPainel {
  /** The live pause switch ("processamento ativo"). */
  ativo: boolean;
  /** The process that answered — not the whole fleet. */
  worker: {
    escopo: 'este_processo';
    kill_switch_ativo: boolean;
    rodando: boolean;
    pausado: boolean;
    worker_id: string | null;
    iniciado_em: string | null;
    motivo_parado: string | null;
    erro_gate: string | null;
    catalogo_atualizado_em: string | null;
    erro_catalogo: string | null;
  };
  /** The shared job table (every process). */
  fila: {
    pendentes: number;
    prontos_para_rodar: number;
    em_execucao: number;
    lease_expirado: number;
    mortos: number;
    workers_ativos: string[];
  };
  ultimo_erro: { mensagem: string; tipo_job: string | null; em: string | null } | null;
  /** From the last probe OR the latest job error. */
  sem_creditos: boolean;
  sonda: SondaResultado | null;
}

export interface ProcessamentoBody {
  ativo: boolean;
}

// ---------------------------------------------------------------------------
// Dashboard (contract §8 `GET /painel`, W9)
// ---------------------------------------------------------------------------

/** One point of `pipeline.pontos` — a photo count for one state on one day. */
export interface PainelPipelinePonto {
  data: string;
  estado: string;
  total: number;
}

/**
 * Queue & health. ALWAYS platform-wide (`escopo: 'plataforma'`) regardless
 * of the caller's own dashboard scope — `jobs`/`fotos_por_estado` are
 * EXHAUSTIVE maps (every known status/state key present, `0` when there
 * are none), never sparse.
 */
export interface PainelFila {
  escopo: 'plataforma';
  jobs: Record<string, number>;
  travados: number;
  fotos_por_estado: Record<string, number>;
}

export interface PainelAtividadeSerie {
  data: string;
  lotes: number;
  fotos: number;
  decisoes: number;
}

export interface PainelAtividade {
  lotes_criados: number;
  fotos_enviadas: number;
  /** Exhaustive: `{ aprovar, rejeitar }`, always both keys. */
  decisoes: Record<string, number>;
  usuarios_ativos: number;
  serie_diaria: PainelAtividadeSerie[];
}

export interface PainelAprendizado {
  taxa_aprovacao: number;
  /** Exhaustive: `{ aprovar, rejeitar }`, always both keys. */
  veredito_ia: Record<string, number>;
  /** `null` when there is no photo with BOTH a decision and an AI verdict in the window. */
  acerto_ia_pct: number | null;
  regras: { aprovadas: number; pendentes: number };
}

export interface PainelCustoCategoria {
  categoria: string;
  total_brl: number;
}

/**
 * Revenue is billing-sourced (Core, not shipped yet as of W9) —
 * `disponivel` is always `false` and `total_brl` always `0`; render the
 * `nota`, never a fabricated number (contract's "no silent errors" rule).
 */
export interface PainelReceita {
  disponivel: boolean;
  total_brl: number;
  nota: string | null;
}

export interface PainelCustos {
  moeda_base: 'BRL';
  por_categoria: PainelCustoCategoria[];
  total_brl: number;
  fx_pendentes: number;
  receita: PainelReceita;
  margem_brl: number;
}

/**
 * `GET /painel` (contract §8, W9) — pipeline throughput · queue & health ·
 * activity · learning loop · costs. Scope follows `capacidades.dashboard`:
 * a platform admin may pass `org_id` to filter to one org (`escopo` flips
 * to `'organizacao'`); an agency admin always sees their own org
 * (`org_id` is ignored server-side for them, never trusted from the query
 * string) and gets `escopo: 'organizacao'` unconditionally.
 */
export interface Painel {
  periodo: { desde: string; ate: string };
  escopo: 'plataforma' | 'organizacao';
  pipeline: { pontos: PainelPipelinePonto[] };
  fila: PainelFila;
  atividade: PainelAtividade;
  aprendizado: PainelAprendizado;
  custos: PainelCustos;
}

/** `usePainel` filter — an omitted `desde`/`ate` defaults server-side to the last 30 days. */
export interface PainelFiltro {
  desde?: string;
  ate?: string;
  /** Platform admin only; ignored server-side for an agency admin caller. */
  org_id?: string;
}

// ---------------------------------------------------------------------------
// Hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

/** `['edicao-fotos', 'referencias', incluirArquivadas, page, pageSize]` — the archived toggle comes FIRST so a write can address "all active lists" / "all lists with archived" by prefix. */
const REFERENCIAS_KEY = ['edicao-fotos', 'referencias'] as const;
const REVISAO_KEY = (loteId: string | null | undefined) => ['edicao-fotos', 'revisao', loteId] as const;
const LOTE_KEY = (loteId: string | null | undefined) => ['edicao-fotos', 'lote', loteId] as const;
const LOTES_KEY = ['edicao-fotos', 'lotes'] as const;
const GUIAS_KEY = ['edicao-fotos', 'guias'] as const;
/** Reads whose rows a queued worker job produces poll at this pace while a hand-off is pending. */
const JOB_POLL_MS = 4000;
const REGRAS_KEY = ['edicao-fotos', 'regras'] as const;
const REGRA_STATUS: RegraStatus[] = ['proposta', 'aprovada', 'rejeitada'];

/** `PUT /configuracoes` answers with the saved settings when it echoes them; otherwise the body just sent stands. */
function isOrgConfiguracoes(v: unknown): v is OrgConfiguracoes {
  return !!v && typeof v === 'object' && 'tipos_edicao_ativos' in v && 'velocidade_padrao' in v;
}

/** Edit the photo rows of a cached batch detail (`LoteDetalhe.fotos`); anything else passes through. */
const editLoteFotos = (edit: (fotos: FotoRevisao[]) => FotoRevisao[] | undefined) => (old: LoteDetalhe | undefined) =>
  old && Array.isArray(old.fotos) ? listOps.merge(old, { fotos: edit(old.fotos) ?? old.fotos }) : old;

export function createEdicaoFotosHooks(api: ApiClient) {
  /** `GET /capacidades` — drives every FE gate for this feature. */
  function useCapacidades() {
    const query = useQuery<Capacidades>({
      queryKey: ['edicao-fotos', 'capacidades'],
      queryFn: () => api.get('/api/edicao-fotos/capacidades'),
      staleTime: 60 * 1000,
    });
    return {
      capacidades: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `GET /revisao/{lote_id}` — photos for review. Keyed on `loteId`, with
   * `placeholderData` so switching batches never unmounts the grid mid-fetch
   * (contract §9, binding).
   */
  function useRevisao(loteId: string | null | undefined) {
    const query = useQuery<FotoRevisao[]>({
      queryKey: ['edicao-fotos', 'revisao', loteId],
      queryFn: () => api.get(`/api/edicao-fotos/revisao/${loteId}`),
      enabled: !!loteId,
      placeholderData: (prev) => prev,
    });
    return {
      fotos: query.data ?? [],
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `POST /revisao/{lote_id}/fotos/{foto_id}/decisao` — decisions are always
   * changeable, including after the zip has been downloaded (contract §4).
   */
  function useDecidirFoto(loteId: string | null | undefined) {
    // The decision is predictable (the reviewer just made it): drawn on the click in the review grid AND the batch
    // detail, then replaced by the row the server answers with (`estado`, `avaliacao` ...). A refusal (422
    // `comentario_obrigatorio`) rolls it back. The per-batch decided counts on the list are server-derived.
    return useCacheWriteMutation<FotoRevisao, { fotoId: string; body: DecisaoBody }>({
      mutationFn: ({ fotoId, body }) =>
        api.post<FotoRevisao>(`/api/edicao-fotos/revisao/${loteId}/fotos/${fotoId}/decisao`, body),
      targets: ({ fotoId, body }) => [
        {
          queryKey: REVISAO_KEY(loteId),
          optimistic: (old: FotoRevisao[] | undefined) => listOps.patch(old, fotoId, { decisao: body.decisao, comentario: body.comentario }),
          commit: (old: FotoRevisao[] | undefined, saved: FotoRevisao) => listOps.patch(old, fotoId, saved),
        },
        {
          queryKey: LOTE_KEY(loteId),
          optimistic: editLoteFotos((fotos) => listOps.patch(fotos, fotoId, { decisao: body.decisao, comentario: body.comentario })),
          commit: (old: LoteDetalhe | undefined, saved: FotoRevisao) => editLoteFotos((fotos) => listOps.patch(fotos, fotoId, saved))(old),
        },
      ],
      invalidate: [LOTES_KEY],
    });
  }

  /**
   * `POST /lotes/{id}/fotos/{foto_id}/retentar` — manual retry of a
   * `falhou` photo (technical failure, contract §3).
   */
  function useRetentarFoto(loteId: string | null | undefined) {
    // The server answers with the photo row in its new state (back in the pipeline): it replaces the failed one.
    return useCacheWriteMutation<FotoRevisao, string>({
      mutationFn: (fotoId) =>
        api.post<FotoRevisao>(`/api/edicao-fotos/lotes/${loteId}/fotos/${fotoId}/retentar`, {}),
      targets: (fotoId) => [
        { queryKey: REVISAO_KEY(loteId), commit: (old: FotoRevisao[] | undefined, saved: FotoRevisao) => listOps.patch(old, fotoId, saved) },
        { queryKey: LOTE_KEY(loteId), commit: (old: LoteDetalhe | undefined, saved: FotoRevisao) => editLoteFotos((fotos) => listOps.patch(fotos, fotoId, saved))(old) },
      ],
      invalidate: [LOTES_KEY],
    });
  }

  /**
   * `GET /referencias` — platform-scope reference pool (contract §5), paged,
   * with pool occupancy + the fixed upload vocabularies. Keyed on the page
   * and the archived toggle, with `placeholderData` so flipping either never
   * unmounts a grid that already has content.
   */
  function useReferencias(
    params: { page?: number; pageSize?: number; incluirArquivadas?: boolean } = {},
  ) {
    const { page = 1, pageSize = 50, incluirArquivadas = false } = params;
    const query = useQuery<ReferenciasPage>({
      queryKey: [...REFERENCIAS_KEY, incluirArquivadas, page, pageSize],
      queryFn: () =>
        api.get('/api/edicao-fotos/referencias', {
          page,
          page_size: pageSize,
          incluir_arquivadas: incluirArquivadas,
        }),
      staleTime: 30 * 1000,
      placeholderData: (prev) => prev,
    });
    return {
      referencias: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      pool: query.data?.pool,
      opcoes: query.data?.opcoes,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `POST /referencias` — multipart pair upload; 409 `pool_cheio` when the
   * pair limit is reached (contract §5). Fields: `antes`, `depois` (files),
   * `comodo`, `tipos_edicao` (repeated), `nota`.
   */
  function useCriarReferencia() {
    // The pool lists newest first: the new pair is drawn at the top of page 1 (every cached page-1 list, archived toggle
    // either way); the pool occupancy / later pages are server-derived and refresh on the settle.
    return useCacheWriteMutation<ReferenciaPar, NovaReferenciaBody>({
      mutationFn: (body) => {
        const form = new FormData();
        form.append('antes', body.antes);
        form.append('depois', body.depois);
        form.append('comodo', body.comodo);
        body.tipos_edicao.forEach((tipo) => form.append('tipos_edicao', tipo));
        if (body.nota) form.append('nota', body.nota);
        return api.upload<ReferenciaPar>('/api/edicao-fotos/referencias', form);
      },
      targets: [
        {
          queryKey: REFERENCIAS_KEY,
          match: 'prefix',
          commit: (old: unknown, saved: ReferenciaPar) => pageOps.prependNewest(old, saved),
        },
      ],
    });
  }

  /** `DELETE /referencias/{id}` — archive, never a hard delete (contract §5). */
  function useArquivarReferencia() {
    // Archiving is predictable: the pair leaves every active-only list on the click, and shows as archived in the
    // lists that include archived pairs; the server's archived row replaces it on success.
    return useCacheWriteMutation<ReferenciaPar, string>({
      mutationFn: (id) => api.delete<ReferenciaPar>(`/api/edicao-fotos/referencias/${id}`),
      targets: (id) => [
        {
          queryKey: [...REFERENCIAS_KEY, false],
          match: 'prefix',
          optimistic: (old: unknown) => pageOps.remove(old, id),
        },
        {
          queryKey: [...REFERENCIAS_KEY, true],
          match: 'prefix',
          optimistic: (old: unknown) => pageOps.patch(old, id, { arquivada_em: new Date().toISOString() }),
          commit: (old: unknown, saved: ReferenciaPar) => pageOps.replace(old, id, saved),
        },
      ],
      invalidate: [REFERENCIAS_KEY],
    });
  }

  // ---------------------------------------------------------------------
  // Guias de estilo (contract §6), W6
  // ---------------------------------------------------------------------

  /** `GET /guias` — every version, newest first; `placeholderData` across page changes. */
  function useGuias(params: { page?: number; pageSize?: number } = {}) {
    const { page = 1, pageSize = 20 } = params;
    const query = useQuery<GuiasPage>({
      queryKey: [...GUIAS_KEY, page, pageSize],
      queryFn: () => api.get('/api/edicao-fotos/guias', { page, page_size: pageSize }),
      placeholderData: (prev) => prev,
      // A queued AI rebuild (`useRegenerarGuia`) lands later: poll only while that hand-off is pending.
      ...jobPolling<GuiasPage>(() => false, JOB_POLL_MS),
    });
    return {
      guias: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      versaoAtiva: query.data?.versao_ativa ?? null,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** A new version is the highest number and the list is newest first: it is drawn at the top of page 1. */
  const guiaCriada = {
    queryKey: GUIAS_KEY,
    match: 'prefix' as const,
    commit: (old: unknown, saved: GuiaEstiloVersao) => pageOps.prependNewest(old, saved),
  };

  /** `POST /guias` — a manually written DRAFT (the no-AI path, contract §6). */
  function useCriarGuia() {
    return useCacheWriteMutation<GuiaEstiloVersao, NovoGuiaBody>({
      mutationFn: (body) => api.post<GuiaEstiloVersao>('/api/edicao-fotos/guias', body),
      targets: [guiaCriada],
    });
  }

  /** `POST /guias/{versao}/ativar` — this version becomes the one new batches snapshot. */
  function useAtivarGuia() {
    return useCacheWriteMutation<GuiaEstiloVersao, number>({
      mutationFn: (versao) => api.post<GuiaEstiloVersao>(`/api/edicao-fotos/guias/${versao}/ativar`, {}),
      // the activated version replaces its row and becomes `versao_ativa`; the version it superseded is server-derived
      targets: [
        {
          queryKey: GUIAS_KEY,
          match: 'prefix',
          commit: (old: GuiasPage | undefined, saved: GuiaEstiloVersao) => {
            const next = pageOps.replace(old, saved.id, saved);
            return next && typeof next === 'object' && 'items' in next ? { ...next, versao_ativa: saved.versao } : next;
          },
        },
      ],
      invalidate: [['edicao-fotos', 'guia-efetivo']],
    });
  }

  /** `POST /guias/{versao}/restaurar` — clones the version as a NEW draft (versions are immutable). */
  function useRestaurarGuia() {
    return useCacheWriteMutation<GuiaEstiloVersao, number>({
      mutationFn: (versao) => api.post<GuiaEstiloVersao>(`/api/edicao-fotos/guias/${versao}/restaurar`, {}),
      targets: [guiaCriada],
    });
  }

  /**
   * `POST /guias/regenerar` — queue the AI rebuild from the pool (202). The
   * draft appears only after the worker runs it; 409 `pool_vazio` on an
   * empty pool.
   */
  function useRegenerarGuia() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — a 202 that only queues the AI rebuild: the draft does not exist until the worker runs it, so there is no row to place yet
      mutationFn: () =>
        api.post<RegenerarGuiaResposta>('/api/edicao-fotos/guias/regenerar', {}),
      // 202: the draft appears when the worker runs — follow the list until it changes (F87).
      onSuccess: () => handOffToPolling(queryClient, GUIAS_KEY, { until: 'changed' }),
    });
  }

  // ---------------------------------------------------------------------
  // Regras de aprendizado (contract §7), W7
  // ---------------------------------------------------------------------

  /**
   * `GET /regras` — proposed/approved/rejected rules for the caller's org;
   * optional `status` filter. `placeholderData` keeps the list from
   * unmounting while the filter/page changes.
   */
  function useRegras(params: { status?: RegraStatus } = {}) {
    const { status } = params;
    const query = useQuery<RegrasPage>({
      queryKey: [...REGRAS_KEY, status ?? null],
      queryFn: () => api.get('/api/edicao-fotos/regras', status ? { status } : undefined),
      placeholderData: (prev) => prev,
      // The proposer (`useProporRegrasAgora`) runs on the worker: poll only while that hand-off is pending.
      ...jobPolling<RegrasPage>(() => false, JOB_POLL_MS),
    });
    return {
      regras: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** What a rule write changes beyond the rule lists: the effective guide is derived from the approved rules. */
  const REGRAS_DERIVADAS = [['edicao-fotos', 'guia-efetivo']];

  /** Put `saved` into a status-filtered (or unfiltered) rule list: replaced in place if listed, appended otherwise. */
  const upsertRegra = (old: RegrasPage | undefined, saved: RegraOrg): RegrasPage | undefined => {
    if (!old || !Array.isArray(old.items)) return old;
    if (old.items.some((r) => r.id === saved.id)) return pageOps.replace(old, saved.id, saved);
    return { ...old, items: [...old.items, saved], total: old.total + 1 };
  };

  /** One target per rule list (unfiltered + each status): the decided rule is listed where its NEW status says, and leaves the others. */
  const regraNasListas = (regraId: string) =>
    ([null, ...REGRA_STATUS] as (RegraStatus | null)[]).map((filtro) => ({
      queryKey: [...REGRAS_KEY, filtro],
      commit: (old: RegrasPage | undefined, saved: RegraOrg) =>
        filtro === null || filtro === saved.status ? upsertRegra(old, saved) : pageOps.remove(old, regraId),
    }));

  /**
   * `POST /regras` — a manually written "don't do this" rule, created
   * directly APROVADA (the admin writing it down IS the approval).
   */
  function useCriarRegra() {
    return useCacheWriteMutation<RegraOrg, NovaRegraBody>({
      mutationFn: (body) => api.post<RegraOrg>('/api/edicao-fotos/regras', body),
      // rules list oldest first and a manual rule is born approved: it joins the unfiltered and the approved lists
      targets: [null, 'aprovada'].map((filtro) => ({
        queryKey: [...REGRAS_KEY, filtro],
        commit: (old: RegrasPage | undefined, saved: RegraOrg) => upsertRegra(old, saved),
      })),
      invalidate: [REGRAS_KEY, ...REGRAS_DERIVADAS],
    });
  }

  /** `PUT /regras/{id}` — edit a rule's text; 422 `regra_arquivada` once it is REJEITADA. */
  function useEditarRegra() {
    return useCacheWriteMutation<RegraOrg, { regraId: string; texto: string }>({
      mutationFn: ({ regraId, texto }) => api.put<RegraOrg>(`/api/edicao-fotos/regras/${regraId}`, { texto }),
      targets: ({ regraId, texto }) => [
        {
          queryKey: REGRAS_KEY,
          match: 'prefix',
          optimistic: (old: unknown) => pageOps.patch(old, regraId, { texto }),
          commit: (old: unknown, saved: RegraOrg) => pageOps.replace(old, regraId, saved),
        },
      ],
      invalidate: REGRAS_DERIVADAS,
    });
  }

  /** `POST /regras/{id}/aprovar`. */
  function useAprovarRegra() {
    return useCacheWriteMutation<RegraOrg, string>({
      mutationFn: (regraId) => api.post<RegraOrg>(`/api/edicao-fotos/regras/${regraId}/aprovar`, {}),
      targets: (regraId) => regraNasListas(regraId),
      invalidate: [REGRAS_KEY, ...REGRAS_DERIVADAS],
    });
  }

  /**
   * `POST /regras/{id}/rejeitar` — also the "archive" action for an
   * already-approved rule (manual or AI-proposed): a decided rule can only
   * be re-decided by a platform admin (403 otherwise).
   */
  function useRejeitarRegra() {
    return useCacheWriteMutation<RegraOrg, string>({
      mutationFn: (regraId) => api.post<RegraOrg>(`/api/edicao-fotos/regras/${regraId}/rejeitar`, {}),
      targets: (regraId) => regraNasListas(regraId),
      invalidate: [REGRAS_KEY, ...REGRAS_DERIVADAS],
    });
  }

  /**
   * `POST /regras/propor-agora` — the "propor agora" button: run the AI
   * rule proposer NOW instead of waiting for the rejection-settling
   * debounce (`PlataformaConfiguracoes.rule_proposal_debounce_seconds`).
   */
  function useProporRegrasAgora() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — a queued job: the proposed rules do not exist until the worker runs the proposer, so there is nothing to place yet
      mutationFn: () => api.post<ProporRegrasResposta>('/api/edicao-fotos/regras/propor-agora', {}),
      // Follow the rules list until the proposer's rows land (F87).
      onSuccess: () => handOffToPolling(queryClient, REGRAS_KEY, { until: 'changed' }),
    });
  }

  /**
   * `GET /regras/guia-efetivo` — the current effective guide (company
   * guide + this org's approved rules) + its version history.
   */
  function useGuiaEfetivo(params: { page?: number; pageSize?: number } = {}) {
    const { page = 1, pageSize = 20 } = params;
    const query = useQuery<GuiaEfetivoView>({
      queryKey: ['edicao-fotos', 'guia-efetivo', page, pageSize],
      queryFn: () => api.get('/api/edicao-fotos/regras/guia-efetivo', { page, page_size: pageSize }),
      placeholderData: (prev) => prev,
    });
    return {
      atual: query.data?.atual ?? null,
      historico: query.data?.historico?.items ?? [],
      total: query.data?.historico?.total ?? 0,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  // ---------------------------------------------------------------------
  // Configurações da plataforma (contract §8) — platform admin only
  // ---------------------------------------------------------------------

  /** `GET /configuracoes/plataforma`. Pass `enabled: false` for callers that cannot read it (curators get 403). */
  function useConfiguracoesPlataforma(options: { enabled?: boolean } = {}) {
    const { enabled = true } = options;
    const query = useQuery<PlataformaConfiguracoes>({
      queryKey: ['edicao-fotos', 'configuracoes-plataforma'],
      queryFn: () => api.get('/api/edicao-fotos/configuracoes/plataforma'),
      enabled,
    });
    return {
      configuracoes: query.data,
      showSkeleton: enabled && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `PUT /configuracoes/plataforma` — send the WHOLE object (read, change,
   * write): omitted fields fall back to server defaults, except
   * `limite_pares_referencia`, which is left untouched when absent.
   */
  function useAtualizarConfiguracoesPlataforma() {
    // The whole object goes up and comes back: the saved settings replace the cached ones. The reference-pool limit
    // changes the pool occupancy the reference lists show, which is server-derived.
    return useCacheWriteMutation<PlataformaConfiguracoes, PlataformaConfiguracoes>({
      mutationFn: (body) => api.put<PlataformaConfiguracoes>('/api/edicao-fotos/configuracoes/plataforma', body),
      targets: [
        { queryKey: ['edicao-fotos', 'configuracoes-plataforma'], commit: (_old: PlataformaConfiguracoes | undefined, saved: PlataformaConfiguracoes) => saved },
      ],
      invalidate: [REFERENCIAS_KEY],
    });
  }

  // ---------------------------------------------------------------------
  // Lotes — list/create/upload/vista/submeter/zip (contract §3), W10a
  // ---------------------------------------------------------------------

  /** `GET /lotes` — batch list (contract §3). Paginated per contract §0. */
  function useLotes(params: { page?: number; pageSize?: number } = {}) {
    const { page = 1, pageSize = 50 } = params;
    const query = useQuery<LotesPage>({
      queryKey: [...LOTES_KEY, page, pageSize],
      queryFn: () => api.get('/api/edicao-fotos/lotes', { page, page_size: pageSize }),
      placeholderData: (prev) => prev,
    });
    return {
      lotes: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      page: query.data?.page ?? page,
      pageSize: query.data?.page_size ?? pageSize,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `GET /lotes/{id}` — batch header + per-photo state (contract §3). */
  function useLote(loteId: string | null | undefined) {
    const query = useQuery<LoteDetalhe>({
      queryKey: LOTE_KEY(loteId),
      queryFn: () => api.get(`/api/edicao-fotos/lotes/${loteId}`),
      enabled: !!loteId,
      placeholderData: (prev) => prev,
    });
    return {
      lote: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `POST /lotes` — create batch metadata (contract §3). Photos follow via `useUploadFotos`/`useLoteVista`. */
  function useCriarLote() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — the answer is only {id, nome}; the list row (imóvel, velocidade, estado agregado, photo counts) is server-derived, so the batch list re-reads
      mutationFn: (body: NovoLoteBody) => api.post<LoteCriado>('/api/edicao-fotos/lotes', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: LOTES_KEY });
      },
    });
  }

  /**
   * `POST /lotes/{id}/fotos` — multipart upload (contract §3). Takes
   * `loteId` as a MUTATION VARIABLE (not a hook-instantiation parameter,
   * unlike `useRevisao`/`useDecidirFoto`) — the id is typically only known
   * mid-flow, right after `useCriarLote()` resolves (the "create batch, then
   * feed it photos" sequence `NovoLote.tsx` drives), so a hook-time
   * parameter would close over a stale `undefined`. Field name `fotos`
   * (repeated) — 🔴 FLAG: not specified by the contract; mirrors the
   * FastAPI `List[UploadFile] = File(...)` convention every other seed
   * multi-file upload uses (e.g. igig's `usePautas.ts`). Confirm against the
   * real router once W3 lands.
   */
  function useUploadFotos() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — the answer does not carry the stored photos (ids, estado and URLs come from the server's normalisation), so the batch detail and list re-read
      mutationFn: ({ loteId, files }: { loteId: string; files: File[] }) => {
        const form = new FormData();
        files.forEach((file) => form.append('fotos', file));
        return api.upload(`/api/edicao-fotos/lotes/${loteId}/fotos`, form);
      },
      onSuccess: (_data, { loteId }) => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lote', loteId] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/vista` — pull photos from a Vista imóvel by `codigo`
   * (contract §3, §10 C5). `loteId` is a mutation variable — same
   * just-created-mid-flow reasoning as `useUploadFotos`.
   */
  function useLoteVista() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — the photos are pulled from the Vista gallery server-side and the answer does not carry them, so the batch detail and list re-read
      mutationFn: ({ loteId, body }: { loteId: string; body: VistaLoteBody }) =>
        api.post(`/api/edicao-fotos/lotes/${loteId}/vista`, body),
      onSuccess: (_data, { loteId }) => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lote', loteId] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/submeter` — snapshot the effective guide + enqueue
   * jobs (contract §3). `loteId` is a mutation variable — same reasoning.
   */
  function useSubmeterLote() {
    // The server answers with the batch summary (new aggregate state, counts): it replaces the list row. The photos'
    // own states (queued jobs) are server-derived, so the batch detail re-reads.
    return useCacheWriteMutation<LoteResumo, string>({
      mutationFn: (loteId) => api.post<LoteResumo>(`/api/edicao-fotos/lotes/${loteId}/submeter`, {}),
      targets: (loteId) => [
        { queryKey: LOTES_KEY, match: 'prefix', commit: (old: unknown, saved: LoteResumo) => pageOps.replace(old, loteId, saved) },
        { queryKey: LOTE_KEY(loteId) },
      ],
    });
  }

  /**
   * `GET /lotes/{id}/zip` — binary download, **409 until every photo is
   * decided** (contract §3). Goes through `api.download()` (the `ApiClient`
   * binary-GET primitive — see `../api.ts`) rather than a raw `fetch`, so it
   * gets the SAME auth header + 401-retry path as every JSON call, and a
   * 409 surfaces as a normal `ApiError` with `.status === 409` the caller
   * can branch on (e.g. "ainda há fotos sem decisão"). Triggers the browser
   * download itself (`URL.createObjectURL` + a synthetic `<a download>`
   * click) — no Social-Wiring-specific helper involved, keeping this organ
   * portable.
   */
  function useBaixarZip() {
    return useMutation({ // noc-allow: invalidate-only — a binary download: it changes no server state and no cached query reads it
      mutationFn: async ({ loteId, nomeArquivo }: { loteId: string; nomeArquivo: string }) => {
        const blob = await api.download(`/api/edicao-fotos/lotes/${loteId}/zip`);
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = nomeArquivo;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      },
    });
  }

  // ---------------------------------------------------------------------
  // Configurações + catálogo de modelos (contract §8), W10a
  // ---------------------------------------------------------------------

  /** `GET /configuracoes` — org edit types, image model, speed override (contract §8). */
  function useConfiguracoes() {
    const query = useQuery<OrgConfiguracoes>({
      queryKey: ['edicao-fotos', 'configuracoes'],
      queryFn: () => api.get('/api/edicao-fotos/configuracoes'),
    });
    return {
      configuracoes: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `PUT /configuracoes` — agency admin / platform admin only server-side (contract §1, §8). */
  function useAtualizarConfiguracoes() {
    // Read-change-write: the body IS the new settings, so it is drawn on the click and rolled back on a refusal.
    // What the capabilities derive from it (editable types, model gates) is server-side and refreshes on the settle.
    return useCacheWriteMutation<unknown, OrgConfiguracoes>({
      mutationFn: (body) => api.put('/api/edicao-fotos/configuracoes', body),
      targets: (body) => [
        {
          queryKey: ['edicao-fotos', 'configuracoes'],
          optimistic: () => body,
          commit: (_old: OrgConfiguracoes | undefined, saved: unknown) => (isOrgConfiguracoes(saved) ? saved : body),
        },
      ],
      invalidate: [['edicao-fotos', 'capacidades']],
    });
  }

  /** `GET /modelos` — image-model catalog (contract §8); drives the Configuracoes picker. */
  function useModelos() {
    const query = useQuery<ModeloCatalogoItem[]>({
      queryKey: ['edicao-fotos', 'modelos'],
      queryFn: () => api.get('/api/edicao-fotos/modelos'),
      staleTime: 60 * 1000,
      // The notes rewrite (`useGerarNotasModelos`) runs on the worker: poll only while that hand-off is pending.
      ...jobPolling<ModeloCatalogoItem[]>(() => false, JOB_POLL_MS),
    });
    return {
      modelos: query.data ?? [],
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  // ---------------------------------------------------------------------
  // Curadores (contract §1/§8, platform admin only)
  // ---------------------------------------------------------------------

  /** `GET /curadores` — the `photo_curator` grant roster. */
  function useCuradores() {
    const query = useQuery<CuradoresPage>({
      queryKey: ['edicao-fotos', 'curadores'],
      queryFn: () => api.get('/api/edicao-fotos/curadores'),
      placeholderData: (prev) => prev,
    });
    return {
      curadores: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  // ---------------------------------------------------------------------
  // Dashboard (contract §8 `GET /painel`), W9
  // ---------------------------------------------------------------------

  /**
   * `GET /painel` — contract §8. `filtro.org_id` matters only for a
   * platform admin caller — an agency admin's request always resolves to
   * their own org server-side (migration 133's header). `placeholderData`
   * so switching the date range or the org filter never blanks the
   * dashboard mid-fetch (contract §9, binding).
   */
  function usePainel(filtro: PainelFiltro = {}) {
    const params: Record<string, string> = {};
    if (filtro.desde) params.desde = filtro.desde;
    if (filtro.ate) params.ate = filtro.ate;
    if (filtro.org_id) params.org_id = filtro.org_id;
    const query = useQuery<Painel>({
      queryKey: [
        'edicao-fotos',
        'painel',
        filtro.desde ?? null,
        filtro.ate ?? null,
        filtro.org_id ?? null,
      ],
      queryFn: () => api.get('/api/edicao-fotos/painel', params),
      placeholderData: (prev) => prev,
    });
    return {
      painel: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  // ---------------------------------------------------------------------
  // Curadores (contract §1/§8, platform admin only), continued
  // ---------------------------------------------------------------------

  /** `POST /curadores` — grant `photo_curator` to a user. */
  function useAdicionarCurador() {
    return useCacheWriteMutation<Curador, CuradorCreateBody>({
      mutationFn: (body) => api.post<Curador>('/api/edicao-fotos/curadores', body),
      targets: [
        {
          queryKey: ['edicao-fotos', 'curadores'],
          commit: (old: CuradoresPage | undefined, saved: Curador) =>
            old && Array.isArray(old.items)
              ? old.items.some((c) => c.user_id === saved.user_id)
                ? pageOps.replace(old, saved.user_id, saved, 'user_id')
                : { ...old, items: [...old.items, saved], total: old.total + 1 }
              : old,
        },
      ],
    });
  }

  /** `DELETE /curadores/{user_id}` — revoke `photo_curator`. */
  function useRemoverCurador() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (userId) => api.delete(`/api/edicao-fotos/curadores/${userId}`),
      targets: (userId) => [
        { queryKey: ['edicao-fotos', 'curadores'], optimistic: (old: unknown) => pageOps.remove(old, userId, 'user_id') },
      ],
    });
  }

  // ---------------------------------------------------------------------
  // Notificações — per-user opt-in (plan §1 "Notifications")
  // ---------------------------------------------------------------------

  /** `GET /notificacoes/preferencias` — the caller's OWN opt-in row. */
  function useNotificacaoPreferencia() {
    const query = useQuery<NotificacaoPreferencia>({
      queryKey: ['edicao-fotos', 'notificacoes-preferencias'],
      queryFn: () => api.get('/api/edicao-fotos/notificacoes/preferencias'),
    });
    return {
      preferencia: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `PUT /notificacoes/preferencias` — send the whole object (read, change, write). */
  function useAtualizarNotificacaoPreferencia() {
    // Read-change-write: the body IS the new preference, drawn on the click; the saved row then replaces it.
    return useCacheWriteMutation<NotificacaoPreferencia, NotificacaoPreferencia>({
      mutationFn: (body) => api.put<NotificacaoPreferencia>('/api/edicao-fotos/notificacoes/preferencias', body),
      targets: (body) => [
        {
          queryKey: ['edicao-fotos', 'notificacoes-preferencias'],
          optimistic: () => body,
          commit: (_old: NotificacaoPreferencia | undefined, saved: NotificacaoPreferencia) => saved,
        },
      ],
    });
  }

  // ---------------------------------------------------------------------
  // Catálogo de modelos + etapas + notas (contract §8), W8 — platform admin
  // ---------------------------------------------------------------------

  /** `GET /modelos/catalogo` — every model row, incl. disabled ones. */
  function useModelosCatalogo(options: { enabled?: boolean } = {}) {
    const { enabled = true } = options;
    const query = useQuery<ModelosCatalogoPage>({
      queryKey: ['edicao-fotos', 'modelos-catalogo'],
      queryFn: () => api.get('/api/edicao-fotos/modelos/catalogo'),
      enabled,
    });
    return {
      modelos: query.data?.items ?? [],
      showSkeleton: enabled && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** What a catalogue write changes beyond the catalogue rows: the pickers, the price history and the capabilities derive from it. */
  const MODELOS_DERIVADOS = [
    ['edicao-fotos', 'modelos'],
    ['edicao-fotos', 'modelo-versoes'],
    ['edicao-fotos', 'capacidades'],
  ];

  /** `PUT /modelos/catalogo/{id}` — save one row (a new immutable version). */
  function useSalvarModeloCatalogo() {
    return useCacheWriteMutation<ModeloCatalogoSalvo, { id: string; body: ModeloCatalogoBody }>({
      mutationFn: ({ id, body }) =>
        api.put<ModeloCatalogoSalvo>(`/api/edicao-fotos/modelos/catalogo/${encodeURIComponent(id)}`, body),
      // the saved row (new revisao, resolved prices, origem) replaces its catalogue row; a model that is not listed yet is added
      targets: [
        {
          queryKey: ['edicao-fotos', 'modelos-catalogo'],
          commit: (old: ModelosCatalogoPage | undefined, saved: ModeloCatalogoSalvo) =>
            old && Array.isArray(old.items)
              ? old.items.some((m) => m.id === saved.id)
                ? pageOps.replace(old, saved.id, saved)
                : { ...old, items: [...old.items, saved] }
              : old,
        },
      ],
      invalidate: MODELOS_DERIVADOS,
    });
  }

  /** `GET /modelos/catalogo/{id}/versoes` — a row's price/flag history, newest first. */
  function useModeloVersoes(modeloId: string | null | undefined, kind: ModeloKind = 'image_edit') {
    const query = useQuery<{ items: ModeloCatalogoVersao[] }>({
      queryKey: ['edicao-fotos', 'modelo-versoes', modeloId, kind],
      queryFn: () =>
        api.get(`/api/edicao-fotos/modelos/catalogo/${encodeURIComponent(modeloId ?? '')}/versoes`, { kind }),
      enabled: !!modeloId,
      placeholderData: (prev) => prev,
    });
    return {
      versoes: query.data?.items ?? [],
      showSkeleton: !!modeloId && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
    };
  }

  /** `GET /modelos/etapas`. */
  function useModelosEtapas(options: { enabled?: boolean } = {}) {
    const { enabled = true } = options;
    const query = useQuery<ModelosEtapas>({
      queryKey: ['edicao-fotos', 'modelos-etapas'],
      queryFn: () => api.get('/api/edicao-fotos/modelos/etapas'),
      enabled,
    });
    return {
      etapas: query.data?.etapas ?? [],
      showSkeleton: enabled && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `PUT /modelos/etapas` — send only the steps that changed. */
  function useAtualizarModelosEtapas() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: ModelosEtapasBody) =>
        api.put<ModelosEtapas>('/api/edicao-fotos/modelos/etapas', body),
      onSuccess: (data) => {
        queryClient.setQueryData(['edicao-fotos', 'modelos-etapas'], data);
      },
    });
  }

  /** `POST /modelos/notas/gerar` → 202: the rewrite runs on the worker (only while processing is active). */
  function useGerarNotasModelos() {
    const queryClient = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — a 202: the notes are rewritten by the worker later, so there is nothing to place yet
      mutationFn: () => api.post<RegenerarGuiaResposta>('/api/edicao-fotos/modelos/notas/gerar', {}),
      // Follow the model list until the rewritten notes land (F87).
      onSuccess: () => handOffToPolling(queryClient, ['edicao-fotos', 'modelos'], { until: 'changed' }),
    });
  }

  // ---------------------------------------------------------------------
  // Processamento (worker control + health), W8 — platform admin
  // ---------------------------------------------------------------------

  /**
   * `GET /processamento`. `refetchInterval` keeps the health panel live;
   * a background refetch reports `isRefreshing`, never a skeleton.
   */
  function useProcessamento(options: { enabled?: boolean; refetchInterval?: number | false } = {}) {
    const { enabled = true, refetchInterval = false } = options;
    const query = useQuery<ProcessamentoPainel>({
      queryKey: ['edicao-fotos', 'processamento'],
      queryFn: () => api.get('/api/edicao-fotos/processamento'),
      enabled,
      refetchInterval,
    });
    return {
      painel: query.data,
      showSkeleton: enabled && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `PUT /processamento` — pause/resume live (no redeploy). */
  function useAtualizarProcessamento() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: ProcessamentoBody) =>
        api.put<ProcessamentoPainel>('/api/edicao-fotos/processamento', body),
      onSuccess: (data) => {
        queryClient.setQueryData(['edicao-fotos', 'processamento'], data);
      },
    });
  }

  /** `POST /processamento/sonda` — spends one token; run on click only. */
  function useSondarOpenAI() {
    // The probe result is exactly the `sonda` block of the processing panel; the credit flag derived from it
    // (`sem_creditos`) is server-side and refreshes on the settle.
    return useCacheWriteMutation<SondaResultado, void>({
      mutationFn: () => api.post<SondaResultado>('/api/edicao-fotos/processamento/sonda', {}),
      targets: [
        {
          queryKey: ['edicao-fotos', 'processamento'],
          commit: (old: ProcessamentoPainel | undefined, sonda: SondaResultado) => listOps.merge(old, { sonda }),
        },
      ],
    });
  }

  return {
    useCapacidades,
    useRevisao,
    useDecidirFoto,
    useRetentarFoto,
    useReferencias,
    useCriarReferencia,
    useArquivarReferencia,
    useGuias,
    useCriarGuia,
    useAtivarGuia,
    useRestaurarGuia,
    useRegenerarGuia,
    useRegras,
    useCriarRegra,
    useEditarRegra,
    useAprovarRegra,
    useRejeitarRegra,
    useProporRegrasAgora,
    useGuiaEfetivo,
    useConfiguracoesPlataforma,
    useAtualizarConfiguracoesPlataforma,
    useLotes,
    useLote,
    useCriarLote,
    useUploadFotos,
    useLoteVista,
    useSubmeterLote,
    useBaixarZip,
    useConfiguracoes,
    useAtualizarConfiguracoes,
    useModelos,
    useCuradores,
    useAdicionarCurador,
    useRemoverCurador,
    useNotificacaoPreferencia,
    useAtualizarNotificacaoPreferencia,
    usePainel,
    useModelosCatalogo,
    useSalvarModeloCatalogo,
    useModeloVersoes,
    useModelosEtapas,
    useAtualizarModelosEtapas,
    useGerarNotasModelos,
    useProcessamento,
    useAtualizarProcessamento,
    useSondarOpenAI,
  };
}

export type EdicaoFotosHooks = ReturnType<typeof createEdicaoFotosHooks>;
