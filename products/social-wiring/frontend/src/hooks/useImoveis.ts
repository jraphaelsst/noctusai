/**
 * Imóveis hooks — TanStack Query wrappers over /api/imoveis.
 *
 * These read the LOCAL mirror (`social_wiring.imoveis`), never Vista. Only
 * `useSyncImoveis` reaches the CRM, and it is a deliberate user action —
 * the full pull takes ~4-6 minutes for the 1919-imóvel catalog.
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Corretor {
  codigo: string | null;
  nome: string | null;
  email: string | null;
  fone: string | null;
}

export interface Imovel {
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
}

export interface FiltroOptions {
  status: string[];
  categoria: string[];
  cidade: string[];
  bairro: string[];
}

export interface SyncResult {
  total_reported: number;
  pages_fetched: number;
  upserted: number;
  detalhes_fetched: number;
  detalhes_failed: string[];
  detalhes_failed_count: number;
  page_failures: string[];
  complete: boolean;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const IMOVEIS_KEY = (f: ImovelFilters) => ["sw", "imoveis", f] as const;
const IMOVEL_KEY = (codigo: string) => ["sw", "imoveis", "detail", codigo] as const;
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
  // Repeated key, not comma-joined — FastAPI's `Query(None)` on a list
  // parses `?caracteristicas=a&caracteristicas=b`, and a comma-joined
  // string would arrive as one slug named "a,b" that matches nothing.
  (f.caracteristicas ?? []).forEach((c) => params.append("caracteristicas", c));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function useImoveis(filters: ImovelFilters = {}) {
  return useQuery({
    queryKey: IMOVEIS_KEY(filters),
    queryFn: async () => {
      const res = await api.get<ImovelPage>(`/api/imoveis${buildQuery(filters)}`);
      return res ?? { items: [], total: 0, page: 1, pages: 1 };
    },
    // Keeps the previous page on screen while the next one loads, so
    // paginating doesn't flash an empty grid.
    placeholderData: (prev) => prev,
  });
}

export function useImovel(codigo: string | null) {
  return useQuery({
    queryKey: IMOVEL_KEY(codigo ?? ""),
    queryFn: async () => api.get<Imovel>(`/api/imoveis/${codigo}`),
    enabled: Boolean(codigo),
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

export function useSyncImoveis() {
  const qc = useQueryClient();
  // Variables typed explicitly: a defaulted `mutationFn` parameter makes
  // TanStack infer the variable type as `void`, so `mutateAsync(true)` then
  // fails to compile.
  return useMutation<SyncResult, Error, boolean>({
    mutationFn: async (withDetalhes) =>
      api.post<SyncResult>(
        `/api/imoveis/sync?with_detalhes=${withDetalhes}`,
        {},
      ),
    onSuccess: () => {
      // Everything derived from the table is now stale — including the
      // filter options and amenity counts, which are computed FROM the rows.
      qc.invalidateQueries({ queryKey: ["sw", "imoveis"] });
    },
  });
}

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
