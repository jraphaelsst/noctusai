/**
 * Imóveis hooks — TanStack Query wrappers over /api/imoveis.
 *
 * These read the LOCAL mirror (`social_wiring.imoveis`), never Vista. Only
 * `useAtualizarVista` (alias `useSyncImoveis`) reaches the CRM, and it is a deliberate
 * admin action that queues a server-side refresh (minutes) — polled via `useUltimaAtualizacaoVista`.
 *
 * Field semantics that look like bugs and are not (all measured against the
 * live tenant on 2026-08-03 — see the roadmap):
 *   · `valor_locacao: null` is normal — 77.5% of the catalog is sale-only.
 *   · `area_construida: null` is near-universal (99.9%) on this tenant.
 *   · `dormitorios: 0` is a REAL zero on a Terreno, NOT missing data.
 *     Render "0" for it; render "—" only for null.
 *   · `latitude`/`longitude` are null on 36.8% — any map needs a fallback.
 *   · `corretores` can hold 2-3 entries (13.1% of imóveis do).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import type { CondominioResumo } from "@/hooks/useCondominios";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Corretor {
  codigo: string | null;
  nome: string | null;
  email: string | null;
  fone: string | null;
}

/** `referencias` on every imóvel (S6): the deal pointers authored on
 *  `imovel_dados`, valid for Vista and manual imóveis alike. */
export interface ImovelReferencias {
  processo_atual_numero: string | null;
  drive_folder_url: string | null;
  drive_folder_id: string | null;
}

export interface Imovel {
  /** "manual" = registered on the platform (no Vista row, no photos, often no
   *  price). Absent on an older backend, so treat undefined as "vista". */
  fonte?: "vista" | "manual";
  referencias?: ImovelReferencias;
  /** S6 dup (CONTRACT §8.6/§8.7). Absent on an older backend. */
  duplicatas_pendentes?: { id: string; outro_codigo: string; score: number }[];
  vinculo?: { manual_codigo: string; vista_codigo: string } | null;
  /** List items only. */
  possivel_duplicado?: boolean;
  /** Migration 300 — the condomínio answer, returned for every imóvel.
   *  `em_condominio` is DERIVED (attached → true, casa de rua → false). */
  condominio_id?: string | null;
  condominio?: CondominioResumo | null;
  casa_de_rua?: boolean;
  em_condominio?: boolean | null;
  codigo: string;
  codigo_imobiliaria: string | null;
  titulo: string | null;
  categoria: string | null;
  status: string | null;
  finalidades: string[];
  cep: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
  empreendimento: string | null;
  latitude: number | null;
  longitude: number | null;
  valor_venda: number | null;
  valor_locacao: number | null;
  area_total: number | null;
  area_privativa: number | null;
  area_construida: number | null;
  dormitorios: number | null;
  suites: number | null;
  vagas: number | null;
  banheiro_social: boolean | null;
  foto_destaque: string | null;
  fotos: string[];
  corretores: Corretor[];
  construtora: string | null;
  data_cadastro: string | null;
  data_atualizacao: string | null;
  caracteristicas: string[];
  sincronizado_em: string | null;

  // ── CONTRACT § 1 — the Vista field surface (29 fields; 32 minus the
  // `lavabo`/`copa`/`escritorio` correction below) ──
  //
  // `Lavabo`/`Copa`/`Escritorio` are DELIBERATELY absent: measured live,
  // Vista SHADOWS them — they are also `Caracteristicas` keys, and our sync
  // always requests `Caracteristicas`, so Vista returns null for all three
  // at top level whenever it does. A column that reads null in production
  // forever is worse than not having it; the same three values are already
  // available as amenity slugs (`lavabo`/`copa`/`escritorio` in
  // `CARACTERISTICA_LABEL` below). `elevador`/`portaria` are NOT shadowed
  // (verified live) and keep their columns.
  descricao_web: string | null;
  observacoes: string | null;
  valor_condominio: number | null;
  valor_iptu: number | null;
  ano_construcao: number | null;
  situacao: string | null;
  ocupacao: string | null;
  pavimentos: number | null;
  posicao: string | null;
  elevador: boolean | null;
  portaria: boolean | null;
  exclusivo: boolean | null;
  aceita_permuta: boolean | null;
  aceita_financiamento: boolean | null;
  destaque_web: boolean | null;
  super_destaque_web: boolean | null;
  exibir_no_site: boolean | null;
  chave: string | null;
  zona: string | null;
  regiao: string | null;
  area_terreno: number | null;
  closet: number | null;
  frente: number | null;
  fundos: number | null;
  referencia: string | null;
  /** Vista-sourced matrícula. NOT the cartório-authored `matricula` that
   *  `social_wiring.imovel_dados` owns (migration 075) — two distinct
   *  `origem`s in the schema, kept namespaced apart on purpose. */
  matricula_vista: string | null;
  inscricao_municipal: string | null;
  video_destaque: string | null;
  tour_360: string | null;

  // ── CONTRACT § 3 — derived / presentation-only, no columns ──
  dias_desde_atualizacao: number | null;
  /** `Norte`/`Sul`/`Leste`/`Oeste` — split out of `caracteristicas`
   *  server-side; not an amenity, rendered as its own group. */
  orientacao_solar: string[];
}

/**
 * `GET /api/imoveis/{codigo}/registro` — does a REGISTRY identity exist for
 * this código, independent of the Vista mirror `useImovel` reads? A manually
 * registered imóvel (`useRegistrarImovelManual`, migration 149) answers 200
 * here with `origem: "manual"` long before (if ever) Vista's own sync mirrors
 * it — that gap is exactly what leaves `useImovel` 404ing on a código the
 * operator DID create. 404 here too means neither the mirror nor the
 * registry has ever seen this código.
 */
export interface ImovelRegistro {
  codigo: string;
  registrado: boolean;
  origem: "manual" | "vista";
  criado_em: string | null;
}

export interface ImovelPage {
  items: Imovel[];
  total: number;
  page: number;
  pages: number;
}

export interface ImovelFilters {
  page?: number;
  page_size?: number;
  status?: string;
  categoria?: string;
  cidade?: string;
  bairro?: string;
  search?: string;
  caracteristicas?: string[];
  possivel_duplicado?: boolean;
}

export interface FiltroOptions {
  status: string[];
  categoria: string[];
  cidade: string[];
  bairro: string[];
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const IMOVEIS_KEY = (f: ImovelFilters) => ["sw", "imoveis", f] as const;
const IMOVEL_KEY = (codigo: string) => ["sw", "imoveis", "detail", codigo] as const;
const IMOVEL_REGISTRO_KEY = (codigo: string) =>
  ["sw", "imoveis", "registro", codigo] as const;
const FILTROS_KEY = ["sw", "imoveis", "filtros"] as const;
const CARACTERISTICAS_KEY = ["sw", "imoveis", "caracteristicas"] as const;

function buildQuery(f: ImovelFilters): string {
  const params = new URLSearchParams();
  if (f.page) params.set("page", String(f.page));
  if (f.page_size) params.set("page_size", String(f.page_size));
  if (f.status) params.set("status", f.status);
  if (f.categoria) params.set("categoria", f.categoria);
  if (f.cidade) params.set("cidade", f.cidade);
  if (f.bairro) params.set("bairro", f.bairro);
  if (f.search) params.set("search", f.search);
  if (f.possivel_duplicado) params.set("possivel_duplicado", "true");
  // Repeated key, not comma-joined — FastAPI's `Query(None)` on a list
  // parses `?caracteristicas=a&caracteristicas=b`, and a comma-joined
  // string would arrive as one slug named "a,b" that matches nothing.
  (f.caracteristicas ?? []).forEach((c) => params.append("caracteristicas", c));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** Money/area come back as numbers or decimal strings; the UI formats numbers. */
const NUMERIC_FIELDS = [
  "valor_venda",
  "valor_locacao",
  "valor_condominio",
  "valor_iptu",
  "area_total",
  "area_privativa",
  "area_construida",
  "area_terreno",
  "dormitorios",
  "suites",
  "vagas",
] as const;

/**
 * Tolerates the manual-imóvel shape (no photos, no price, no Vista flags):
 * decimal strings become numbers, missing arrays become [] so every consumer
 * can `.length`/`.map` without a guard.
 */
export function normalizarImovel<T extends Partial<Imovel>>(raw: T): T {
  const out: Record<string, unknown> = { ...raw };
  for (const k of NUMERIC_FIELDS) {
    const v = out[k];
    if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) out[k] = Number(v);
  }
  for (const k of ["fotos", "corretores", "caracteristicas", "orientacao_solar", "finalidades"]) {
    if (!Array.isArray(out[k])) out[k] = [];
  }
  return out as T;
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function useImoveis(filters: ImovelFilters = {}) {
  return useQuery({
    queryKey: IMOVEIS_KEY(filters),
    queryFn: async () => {
      const res = await api.get<ImovelPage>(`/api/imoveis${buildQuery(filters)}`);
      return res
        ? { ...res, items: (res.items ?? []).map((i) => normalizarImovel(i)) }
        : { items: [], total: 0, page: 1, pages: 1 };
    },
    // Keeps the previous page on screen while the next one loads, so
    // paginating doesn't flash an empty grid.
    placeholderData: (prev) => prev,
  });
}

export function useImovel(codigo: string | null) {
  return useQuery({
    queryKey: IMOVEL_KEY(codigo ?? ""),
    queryFn: async () => {
      const res = await api.get<Imovel>(`/api/imoveis/${codigo}`);
      return res ? normalizarImovel(res) : res;
    },
    enabled: Boolean(codigo),
    // Retry: the seed query-client default (`@noctusai/lib` retry policy) —
    // a 404 here means "this código was never synced from Vista" (a
    // manually-registered imóvel is the common case), a STABLE state the
    // policy never retries; a 5xx/network/timeout gets the paced automatic
    // attempts (1s/3s/9s), then `ImovelDetalhes` shows the "Tentar
    // novamente" button. No per-hook override needed any more.
    // Same reasoning extends to the global error toast (`query-client.ts`):
    // this specific 404 is an expected, already-handled state — not a
    // failure the user needs to be told about. A genuine 5xx/network error
    // on this same query still surfaces loudly.
    meta: { suppressErrorToastStatuses: [404] },
  });
}

/**
 * The registry-identity check `ImovelDetalhes` falls back to when
 * `useImovel` 404s — see `ImovelRegistro` above. Deliberately NOT `enabled`
 * on `useImovel`'s own error: both queries fire together (cheap, parallel,
 * and both are needed anyway to tell "manually registered, not yet mirrored"
 * apart from "genuinely unknown código" without an extra render round-trip).
 */
export function useImovelRegistro(codigo: string | null) {
  return useQuery({
    queryKey: IMOVEL_REGISTRO_KEY(codigo ?? ""),
    queryFn: async () => api.get<ImovelRegistro>(`/api/imoveis/${codigo}/registro`),
    enabled: Boolean(codigo),
    // Retry: the seed default (404 never retried; transient paced) — see
    // `useImovel`.
    // A genuinely unknown código (neither mirror nor registry has ever
    // seen it) is the SAME expected/handled 404 shape `useImovel` opts out
    // of — see its comment and `query-client.ts`.
    meta: { suppressErrorToastStatuses: [404] },
  });
}

export function useImovelFiltros() {
  return useQuery({
    queryKey: FILTROS_KEY,
    queryFn: async () => {
      const res = await api.get<FiltroOptions>("/api/imoveis/filtros");
      return res ?? { status: [], categoria: [], cidade: [], bairro: [] };
    },
  });
}

/** Amenity slug → count, already ordered by usage server-side. */
export function useCaracteristicas() {
  return useQuery({
    queryKey: CARACTERISTICAS_KEY,
    queryFn: async () => {
      const res = await api.get<Record<string, number>>("/api/imoveis/caracteristicas");
      return res ?? {};
    },
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

// ─── Vista refresh: queued run + "Última atualização" ─────────────────────

/** `GET /api/imoveis/sync/ultimo` — the last refresh run of the org (any member may read it). */
export interface UltimaAtualizacaoVista {
  execucao_id: string | null;
  em_andamento: boolean;
  /** em_andamento | ok | incompleto | listar_vazio | removidos_excessivos | falhou | ignorada */
  status: string | null;
  /** Which path ran: Vista's listar, or the per-code (detalhes) refresh used while listar is silent. */
  caminho: "listar" | "detalhes" | null;
  origem: "agendado" | "manual" | null;
  iniciado_em: string | null;
  finalizado_em: string | null;
  novos: number;
  atualizados: number;
  inalterados: number;
  removidos: number;
  falhas: number;
  chamadas: Record<string, number>;
  /** Newest `sincronizado_em` of the mirror (shown when no run was recorded yet). */
  sincronizado_em: string | null;
}

/** `POST /api/imoveis/sync` answers 202 at once: the refresh runs on the server (minutes) — poll `ultimo`. */
export interface AtualizacaoVistaIniciada {
  execucao_id: string;
  status: string;
  ja_em_andamento: boolean;
}

export type ModoAtualizacaoVista = "auto" | "listar" | "detalhes";

export const ULTIMA_ATUALIZACAO_KEY = ["sw", "imoveis", "sync", "ultimo"] as const;
const POLL_MS = 5000;

/**
 * useUltimaAtualizacaoVista — GET /api/imoveis/sync/ultimo, polled every 5 s WHILE a run is going (the hand-off of the
 * queued job). Two loading signals, never `isLoading`: `showSkeleton` on the first load only, `isRefreshing` for a refetch
 * over data already on screen.
 */
export function useUltimaAtualizacaoVista() {
  const query = useQuery({
    queryKey: ULTIMA_ATUALIZACAO_KEY,
    queryFn: () => api.get<UltimaAtualizacaoVista>("/api/imoveis/sync/ultimo"),
    // poll-budget: 5s only while a Vista sync runs, stops when em_andamento=false; ~5 calls/tick; worst 5/tick (bounded by the run); hidden=paused
    refetchInterval: (q) => (q.state.data?.em_andamento ? POLL_MS : false),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * useAtualizarVista — POST /api/imoveis/sync?modo=… (org admin). The answer is the QUEUED run, so it is written straight into
 * the "ultimo" entry as `em_andamento` — that is what hands the screen off to polling; the imóveis list is refetched by
 * the caller when the run finishes (the rows change then, not now).
 */
export function useAtualizarVista() {
  return useCacheWriteMutation<AtualizacaoVistaIniciada, { modo?: ModoAtualizacaoVista } | void>({
    mutationFn: (vars) =>
      api.post<AtualizacaoVistaIniciada>(
        `/api/imoveis/sync?modo=${(vars && vars.modo) || "auto"}`,
        {},
      ),
    targets: [
      {
        queryKey: ULTIMA_ATUALIZACAO_KEY,
        commit: (old: UltimaAtualizacaoVista | undefined, saved) => ({
          ...(old ?? {
            origem: null, caminho: null, iniciado_em: null, finalizado_em: null, novos: 0, atualizados: 0, inalterados: 0,
            removidos: 0, falhas: 0, chamadas: {}, sincronizado_em: null,
          }),
          execucao_id: saved.execucao_id,
          em_andamento: true,
          status: "em_andamento",
        }),
      },
    ],
  });
}

/** Everything derived from the imóveis table is stale once a refresh finishes (list, filter options, amenity counts). */
export function useInvalidarImoveis() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["sw", "imoveis"] });
}

/** Kept under its historical name: the page's "Sincronizar" buttons are the same queued refresh. */
export const useSyncImoveis = useAtualizarVista;

// ─── Display helpers ────────────────────────────────────────────────────────

/**
 * Format a count where 0 is meaningful.
 *
 * `dormitorios: 0` on a Terreno is a fact; `null` is unknown. A naive
 * `value || "—"` collapses both to "—" and erases the distinction the
 * backend went out of its way to preserve.
 */
export function formatCount(value: number | null): string {
  return value === null || value === undefined ? "—" : String(value);
}

/** Format BRL, or "—" when the price genuinely does not apply. */
export function formatValor(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });
}

export function formatArea(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} m²`;
}

/**
 * Linear measurement in meters — `frente`/`fundos` are lot dimensions, not
 * an area, so they get their own unit rather than borrowing `formatArea`'s
 * "m²" (which would be wrong by a whole dimension).
 */
export function formatMetros(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} m`;
}

/**
 * "Sim"/"Não" for a nullable boolean — never the raw `true`/`false`.
 *
 * Returns `null` (not "—") when the value is null: per CONTRACT § 7, a null
 * boolean means the FIELD is hidden, not shown with a dash. Callers gate the
 * `Fact` render on this being non-null, same shape as the "não possui"
 * disclosure logic below.
 */
export function formatBool(value: boolean | null): string | null {
  return value === null || value === undefined ? null : value ? "Sim" : "Não";
}

/** Turn an amenity slug back into something readable. */
/**
 * Human labels for the imóvel characteristic slugs.
 *
 * 🔴 THE FULL LIVE SET, NOT A GUESS. Every key below is one of the 55 distinct
 * values actually present in `imoveis.caracteristicas` on 2026-08-25, read
 * from the database. A partial map would leave the same defect in the tail.
 *
 * They arrive from Vista as lowercase concatenations with no separator —
 * `salajantar`, `aguaquente`, `dormitoriocomarmario` — so there is nothing in
 * the string to split on. The previous implementation only broke camelCase,
 * which these have none of, so it capitalised the first letter and shipped
 * `Cozinhaplanejada` to the filter chips on the two most-used property
 * screens.
 */
const CARACTERISTICA_LABEL: Record<string, string> = {
  adega: "Adega",
  aguaquente: "Água quente",
  arcentral: "Ar central",
  arcondicionado: "Ar-condicionado",
  areaservico: "Área de serviço",
  armarioembutido: "Armário embutido",
  banheirosocial: "Banheiro social",
  bar: "Bar",
  canaletasnorodape: "Canaletas no rodapé",
  churrasqueira: "Churrasqueira",
  copa: "Copa",
  copacozinha: "Copa e cozinha",
  cozinha: "Cozinha",
  cozinhaamericana: "Cozinha americana",
  cozinhaplanejada: "Cozinha planejada",
  deck: "Deck",
  dependenciadeempregada: "Dependência de empregada",
  despensa: "Despensa",
  dormitoriocomarmario: "Dormitório com armário",
  edicula: "Edícula",
  escritorio: "Escritório",
  esperasplit: "Espera para split",
  forro: "Forro",
  gradeado: "Gradeado",
  hidromassagem: "Hidromassagem",
  hometheater: "Home theater",
  jardiminverno: "Jardim de inverno",
  lareira: "Lareira",
  lavabo: "Lavabo",
  livinghall: "Living hall",
  mezanino: "Mezanino",
  mobiliado: "Mobiliado",
  monitoramento: "Monitoramento",
  pisoelevado: "Piso elevado",
  piscina: "Piscina",
  quintal: "Quintal",
  reformado: "Reformado",
  sacada: "Sacada",
  sacadacomchurrasqueira: "Sacada com churrasqueira",
  salaarmarios: "Sala com armários",
  salajantar: "Sala de jantar",
  salatv: "Sala de TV",
  sauna: "Sauna",
  semimobiliado: "Semimobiliado",
  split: "Split",
  suitemaster: "Suíte master",
  terraco: "Terraço",
  tvcabo: "TV a cabo",
  vigiaexterno: "Vigia externo",
  vigiainterno: "Vigia interno",
  vistamar: "Vista para o mar",
  vistapanoramica: "Vista panorâmica",
  vitrine: "Vitrine",
  wcempregada: "WC de empregada",

  // CONTRACT § 3 — the ~20 keys missing from the 2026-08-25 census, added
  // 2026-09-04. Slugs derived the SAME way the backend derives them —
  // `caracteristica_slug()` in imovel.py: fold accents, lowercase, strip
  // all whitespace — from the raw Vista key text quoted in the contract.
  cercaeletrica: "Cerca elétrica",
  alarme: "Alarme",
  antenaparabolica: "Antena parabólica",
  aquecimentoeletrico: "Aquecimento elétrico",
  calefacao: "Calefação",
  porao: "Porão",
  sotao: "Sótão",
  patio: "Pátio",
  gabinete: "Gabinete",
  sala: "Sala",
  salaestar: "Sala de estar",
  estarintimo: "Estar íntimo",
  banheiroauxiliar: "Banheiro auxiliar",
  cozinhamontada: "Cozinha montada",
  cozinhacomtanque: "Cozinha com tanque",
  construcaoalvenaria: "Construção em alvenaria",
  living: "Living",
  // `dependenciadeempregada` (line above, in the original 55) already
  // covers this — the backend's CARACTERISTICA_COLLISIONS merges the
  // upstream-typo variant ("Dependenciade Empregada") and the correctly
  // spelled one ("Dependencia De Empregada") into that ONE slug with an OR,
  // so there is no second key to add here. See imovel.py's
  // `CARACTERISTICA_COLLISIONS` for the merge.
};

/**
 * The label for a characteristic slug.
 *
 * An unknown slug falls back to the old camelCase-and-capitalise behaviour
 * rather than rendering blank: Vista can add a value at any time, and a
 * slightly ugly label is a far better failure than an empty chip that looks
 * like a rendering bug.
 */
export function caracteristicaLabel(slug: string): string {
  const conhecido = CARACTERISTICA_LABEL[slug.toLowerCase()];
  if (conhecido) return conhecido;
  return slug.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (c) => c.toUpperCase());
}

/**
 * The amenity slugs this imóvel does NOT have, restricted to the known
 * label set.
 *
 * The backend only retains the `"Sim"` slugs per row (`parse_caracteristicas`
 * drops every `"Nao"` — see the normalizer), so there is no raw "has=false"
 * list to read on the wire. This is the complement of `presentes` within
 * `CARACTERISTICA_LABEL`'s keys instead: a slug this map doesn't recognize
 * can't appear on either side of the split until it's added above.
 */
export function caracteristicasAusentes(presentes: string[]): string[] {
  const presentesSet = new Set(presentes.map((s) => s.toLowerCase()));
  return Object.keys(CARACTERISTICA_LABEL).filter((slug) => !presentesSet.has(slug));
}
