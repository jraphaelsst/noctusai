/**
 * Estruturas (platform library of script structures) — hooks over `/api/media-creation/estruturas*`
 * and the admin "add video by link" route (contract §6.1–§6.3, §4.2, §11.4).
 *
 * Reads are tier `org` (any member; the server strips admin-only fields), writes are platform-admin.
 *
 * Server-state rules (KB § PATTERNS/common/server-state-family-index.md):
 *  - loading is two signals off `data` — `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`;
 *    `placeholderData` only on filter-keyed lists, never on a by-id detail;
 *  - every write returns the fresh `EstruturaDetalhe` (admin view) and writes it into every cache entry it
 *    touches (the detail + every cached list row) before settling by invalidating the family;
 *  - a refusal is never silent: callers render `mensagemEstruturas(error)` (rotulos/erros.ts).
 */
import { jobPolling } from "@noctusai/lib";
import { pageOps, useCacheWriteMutation, listOps } from "@noctusai/lib/cache-writes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { camposPendentes } from "@/components/geracao/biblioteca/estruturas/rotulos";
import { GERACAO_KEY } from "@/lib/geracaoKeys";
import type {
  EstruturaDetalhe,
  EstruturaFormato,
  EstruturaObjetivo,
  EstruturaResumo,
  EstruturaStatus,
  ImportacaoRelatorio,
  TipoBloco,
  VideoPorLinkResultado,
} from "@/types/estruturas";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/estruturas";
const BIB_BASE = "/api/media-creation/biblioteca";
export const ESTRUTURAS_KEY = [...GERACAO_KEY, "estruturas"] as const;
const LISTA_KEY = [...ESTRUTURAS_KEY, "lista"] as const;
const TIPOS_KEY = [...ESTRUTURAS_KEY, "tipos-bloco"] as const;
const IMPORTACOES_KEY = [...ESTRUTURAS_KEY, "importacoes"] as const;
const PERFIS_KEY = [...GERACAO_KEY, "biblioteca", "perfis"] as const;
const PERFIL_KEY = [...GERACAO_KEY, "biblioteca", "perfil"] as const;

export const estruturaKey = (id: string) => [...ESTRUTURAS_KEY, "detalhe", id] as const;
export const ESTRUTURAS_POR_PAGINA = 20;
export const IMPORTACAO_POLL_MS = 3000;

/* ----------------------------- reads ----------------------------- */

/** Whether the caller is a platform admin (admin controls render only when true; the server enforces). */
export function useEstruturasAdmin() {
  return useQuery({
    queryKey: [...ESTRUTURAS_KEY, "admin"] as const,
    queryFn: async () => unwrap(await api.get<Envelope<{ is_admin: boolean }>>(`${BASE}/admin`)).is_admin,
    staleTime: 5 * 60_000,
  });
}

export interface EstruturasFiltros {
  marcaId?: string | null;
  perfilId?: string | null;
  q?: string;
  formatos?: EstruturaFormato[];
  objetivos?: EstruturaObjetivo[];
  /** Admin only: `ativa | rascunho | arquivada | todas` (ignored by the server for members). */
  status?: EstruturaStatus | "todas";
  /** Admin only. */
  somentePendentesRevisao?: boolean;
  /** Admin only: the 24-months-unused review queue (`revisao=pendente`). */
  revisaoPorDesuso?: boolean;
  limit?: number;
  offset?: number;
}

export interface EstruturasPage {
  items: EstruturaResumo[];
  total: number;
}

export function estruturasQuery(f: EstruturasFiltros): string {
  const p = new URLSearchParams();
  if (f.marcaId) p.set("marca_id", f.marcaId);
  if (f.perfilId) p.set("perfil_id", f.perfilId);
  if (f.q?.trim()) p.set("q", f.q.trim().slice(0, 200));
  f.formatos?.forEach((x) => p.append("formato", x));
  f.objetivos?.forEach((x) => p.append("objetivo", x));
  if (f.status) p.set("status", f.status);
  if (f.somentePendentesRevisao) p.set("somente_pendentes_revisao", "true");
  if (f.revisaoPorDesuso) p.set("revisao", "pendente");
  p.set("limit", String(f.limit ?? ESTRUTURAS_POR_PAGINA));
  p.set("offset", String(f.offset ?? 0));
  return p.toString();
}

/** `GET /estruturas` — filtered, paged (≤ 50). */
export function useEstruturas(filtros: EstruturasFiltros, enabled = true) {
  const query = useQuery({
    queryKey: [...LISTA_KEY, filtros],
    enabled,
    queryFn: async () => unwrap(await api.get<Envelope<EstruturasPage>>(`${BASE}?${estruturasQuery(filtros)}`)),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: enabled && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** `GET /estruturas/{id}` — 404 for a non-admin on a rascunho/arquivada. */
export function useEstruturaDetalhe(id: string | null) {
  const query = useQuery({
    queryKey: estruturaKey(id ?? ""),
    enabled: !!id,
    queryFn: async () => unwrap(await api.get<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id as string)}`)),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** Catalog of block types (the editor's type select, the detail view, the AI prompts). */
export function useTiposBloco() {
  const query = useQuery({
    queryKey: TIPOS_KEY,
    queryFn: async () => unwrap(await api.get<Envelope<TipoBloco[]>>(`${BASE}/tipos-bloco`)),
    staleTime: 60_000,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export interface ImportacoesPage {
  items: ImportacaoRelatorio[];
  total: number;
}

const importacaoEmAndamento = (d: ImportacoesPage | undefined) => !!d?.items.some((i) => i.status === "em_andamento");

/** Import runs (read-only report; the load itself is the MCP tool). Polls while one is `em_andamento`. */
export function useImportacoes(limit = 20, offset = 0, enabled = true) {
  const query = useQuery({
    queryKey: [...IMPORTACOES_KEY, limit, offset],
    enabled,
    queryFn: async () =>
      unwrap(await api.get<Envelope<ImportacoesPage>>(`${BASE}/importacoes?limit=${limit}&offset=${offset}`)),
    placeholderData: (prev) => prev,
    ...jobPolling<ImportacoesPage>(importacaoEmAndamento, IMPORTACAO_POLL_MS),
  });
  return {
    ...query,
    showSkeleton: enabled && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/* ----------------------------- writes ----------------------------- */

/** The list-row shape of a detail (drops `blocos`/`versao` and the admin-only provenance extras). */
export function resumoDe(d: EstruturaDetalhe): EstruturaResumo {
  const { blocos: _b, versao: _v, origem: _o, ref_externa: _r, referencia_rotulo: _rr, formula_herdada_de: _h, proveniencia: _p, ...resumo } = d;
  return d.proveniencia ? { ...resumo, pendente_revisao: camposPendentes(d).length > 0 } : resumo;
}

/** Targets every write of an existing Estrutura fills: its detail + its row in every cached list. */
function alvosDaEstrutura(id: string) {
  return [
    { queryKey: estruturaKey(id), commit: (_old: EstruturaDetalhe | undefined, saved: EstruturaDetalhe) => saved },
    {
      queryKey: LISTA_KEY,
      match: "prefix" as const,
      commit: (old: EstruturasPage | undefined, saved: EstruturaDetalhe) => pageOps.replace(old, id, resumoDe(saved)),
    },
  ];
}

/** A change moves counts on the profile page; filtered lists (status/pendentes) converge on the settle. */
const FAMILIAS_AFETADAS = [ESTRUTURAS_KEY, PERFIS_KEY, PERFIL_KEY];

export type NovoBloco = { nome: string; tipo_id: string; tempo?: string; instrucao?: string; nota?: string; repeticoes?: number };
export type BlocoCorpo = NovoBloco & { id?: string };

export type CriarEstruturaVars = {
  perfil_id: string;
  viral_id?: string;
  formula_headline: string;
  formato: EstruturaFormato;
  objetivos: EstruturaObjetivo[];
  blocos: NovoBloco[];
  status?: "rascunho" | "ativa";
};

export function useCriarEstrutura() {
  const qc = useQueryClient();
  return useCacheWriteMutation<EstruturaDetalhe, CriarEstruturaVars>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<EstruturaDetalhe>>(BASE, v)),
    // A new row's place in a filtered/sorted list is the server's call: the lists settle; the detail is ready now.
    targets: [
      {
        queryKey: LISTA_KEY,
        match: "prefix",
        commit: (old: EstruturasPage | undefined, saved) => pageOps.replace(old, saved.id, resumoDe(saved)),
      },
    ],
    onSuccess: (saved) => {
      qc.setQueryData(estruturaKey(saved.id), saved);
    },
    invalidate: FAMILIAS_AFETADAS,
  });
}

export type AtualizarEstruturaVars = {
  id: string;
  expected_versao: number;
  formula_headline?: string;
  formato?: EstruturaFormato;
  objetivos?: EstruturaObjetivo[];
  viral_id?: string | null;
};

export function useAtualizarEstrutura() {
  return useCacheWriteMutation<EstruturaDetalhe, AtualizarEstruturaVars>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(await api.patch<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id)}`, corpo)),
    targets: (v) => alvosDaEstrutura(v.id),
    invalidate: FAMILIAS_AFETADAS,
  });
}

export type SubstituirBlocosVars = { id: string; expected_versao: number; blocos: BlocoCorpo[] };

export function useSubstituirBlocos() {
  return useCacheWriteMutation<EstruturaDetalhe, SubstituirBlocosVars>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(await api.put<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id)}/blocos`, corpo)),
    targets: (v) => alvosDaEstrutura(v.id),
    invalidate: FAMILIAS_AFETADAS,
  });
}

/** Exactly one of `campos` | `todos` (contract §6.2). */
export type ConfirmarEstruturaVars =
  | { id: string; expected_versao: number; campos: string[] }
  | { id: string; expected_versao: number; todos: true };

export function useConfirmarEstrutura() {
  return useCacheWriteMutation<EstruturaDetalhe, ConfirmarEstruturaVars>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(await api.post<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id)}/confirmar`, corpo)),
    targets: (v) => alvosDaEstrutura(v.id),
    invalidate: [ESTRUTURAS_KEY],
  });
}

export function usePublicarEstrutura() {
  return useCacheWriteMutation<EstruturaDetalhe, { id: string; expected_versao: number }>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(await api.post<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id)}/publicar`, corpo)),
    targets: (v) => alvosDaEstrutura(v.id),
    invalidate: FAMILIAS_AFETADAS,
  });
}

/** `arquivar` ↔ `restaurar` (`ativa ↔ arquivada`). */
export function useArquivarEstrutura() {
  return useCacheWriteMutation<EstruturaDetalhe, { id: string; acao: "arquivar" | "restaurar" }>({
    mutationFn: async ({ id, acao }) =>
      unwrap(await api.post<Envelope<EstruturaDetalhe>>(`${BASE}/${encodeURIComponent(id)}/${acao}`)),
    targets: (v) => alvosDaEstrutura(v.id),
    invalidate: FAMILIAS_AFETADAS,
  });
}

/** Hard delete — only while nothing used it (else 409 `estrutura_em_uso`: archive instead). */
export function useExcluirEstrutura() {
  const qc = useQueryClient();
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: LISTA_KEY,
        match: "prefix",
        optimistic: (old: EstruturasPage | undefined) => pageOps.remove(old, id),
      },
    ],
    onSuccess: (_r, id) => {
      qc.removeQueries({ queryKey: estruturaKey(id) });
    },
    invalidate: FAMILIAS_AFETADAS,
  });
}

/* ------------------------ block-type catalog (admin) ------------------------ */

/** The read type plus the optimistic-concurrency/system fields the admin writes need (contract §6.2). */
export type TipoBlocoAdmin = TipoBloco & { versao?: number; sistema?: boolean };

export type SalvarTipoBlocoVars = {
  /** Present ⇒ `PUT` (edit); absent ⇒ `POST` (create). */
  id?: string;
  nome: string;
  tempo_tipico?: string | null;
  instrucao_referencia: string;
  ativo?: boolean;
  ordem?: number;
  expected_versao?: number;
};

export function useSalvarTipoBloco() {
  return useCacheWriteMutation<TipoBlocoAdmin, SalvarTipoBlocoVars>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(
        id
          ? await api.put<Envelope<TipoBlocoAdmin>>(`${BASE}/tipos-bloco/${encodeURIComponent(id)}`, corpo)
          : await api.post<Envelope<TipoBlocoAdmin>>(`${BASE}/tipos-bloco`, corpo),
      ),
    targets: [
      {
        queryKey: TIPOS_KEY,
        // Replace in place when it is there, else add; keep the catalog in its display order.
        commit: (old: TipoBlocoAdmin[] | undefined, saved) =>
          old &&
          (old.some((t) => t.id === saved.id) ? listOps.replace(old, saved.id, saved) : [...old, saved]).sort(
            (a, b) => a.ordem - b.ordem,
          ),
      },
    ],
    // A rename reaches the denormalised `tipo.nome` of every block that uses it.
    invalidate: [ESTRUTURAS_KEY],
  });
}

export function useExcluirTipoBloco() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.delete(`${BASE}/tipos-bloco/${encodeURIComponent(id)}`),
    targets: (id) => [
      { queryKey: TIPOS_KEY, optimistic: (old: TipoBlocoAdmin[] | undefined) => listOps.remove(old, id) },
    ],
  });
}

/* ------------------------ "Adicionar por link" (admin) ------------------------ */

/**
 * Paste ONE Instagram post link → `POST /biblioteca/virais/por-link` (201, or 200 `ja_existia`).
 * Deduped server-side; a new video is analysed regardless of the viral threshold.
 */
export function useAdicionarVideoPorLink() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the answer is one ViralCard whose place in the sorted/filtered grid (and the profile's totals when perfil_criado) is the server's call
    mutationFn: async (url: string) =>
      unwrap(await api.post<Envelope<VideoPorLinkResultado>>(`${BIB_BASE}/virais/por-link`, { url })),
    onSuccess: () => qc.invalidateQueries({ queryKey: GERACAO_KEY }),
  });
}
