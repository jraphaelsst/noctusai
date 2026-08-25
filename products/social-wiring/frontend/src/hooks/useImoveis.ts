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
