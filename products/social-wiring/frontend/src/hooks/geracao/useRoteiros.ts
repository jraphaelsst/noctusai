/**
 * Roteiros (Meus roteiros + Roteiro Avançado) over `/api/media-creation/roteiros`
 * (contract §4.5 #32–#40). Responses arrive wrapped in `{success, data}`.
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * never `isLoading`. The real status drives the 3 s poll (contract §3.2): only
 * `criando` / `processando` are moving — `perguntas` waits for the user.
 * Every mutation invalidates the whole `["sw","geracao"]` family.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { emAndamento } from "@/components/geracao/labels";
import type { Roteiro, RoteiroResumo } from "@/types/geracao";
import { GERACAO_KEY } from "./useHeadlineMutations";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/roteiros";
export const ROTEIROS_POLL_MS = 3000;
export const ROTEIROS_PAGE_SIZE = 20;

const listaKey = (marcaId: string | null, q: string, offset: number) =>
  [...GERACAO_KEY, "roteiros", marcaId, "lista", q, offset] as const;
const detalheKey = (id: string | null) => [...GERACAO_KEY, "roteiros", "detalhe", id] as const;

function useInvalidateGeracao() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: GERACAO_KEY });
}

/** True while any visible roteiro is still being produced (drives the poll). */
export function algumRoteiroEmAndamento(items: Pick<RoteiroResumo, "status">[] | undefined): boolean {
  return !!items?.some((r) => emAndamento(r.status));
}

export function useRoteiros(marcaId: string | null, q = "", offset = 0) {
  const query = useQuery({
    queryKey: listaKey(marcaId, q, offset),
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        limit: String(ROTEIROS_PAGE_SIZE),
        offset: String(offset),
      });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<{ items: RoteiroResumo[]; total: number }>>(`${BASE}?${p}`));
    },
    refetchInterval: (s) => (algumRoteiroEmAndamento(s.state.data?.items) ? ROTEIROS_POLL_MS : false),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useRoteiro(id: string | null) {
  const query = useQuery({
    queryKey: detalheKey(id),
    enabled: !!id,
    queryFn: async () => unwrap(await api.get<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(id as string)}`)),
    refetchInterval: (s) => (s.state.data && emAndamento(s.state.data.status) ? ROTEIROS_POLL_MS : false),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export interface CriarRoteiroInput {
  marca_id: string;
  headline_id?: string | null;
  headline_texto: string;
  instrucoes?: string;
  fonte: "ia";
  duracao: Roteiro["duracao"];
  brain_id?: string | null;
  viral_id?: string | null;
  gerar_perguntas: boolean;
  /** Created from inside an Esteira post: the server binds the roteiro to it (esteira-contract §3.5). */
  post_id?: string;
}

export function useCriarRoteiro() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: CriarRoteiroInput) => unwrap(await api.post<Envelope<Roteiro>>(BASE, v)),
    onSuccess: invalidate,
  });
}

export function useResponderPerguntas() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; respostas: { id: string; resposta: string }[] }) =>
      unwrap(
        await api.put<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(v.id)}/perguntas`, {
          respostas: v.respostas,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useGerarRoteiro() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; pular_perguntas?: boolean }) =>
      unwrap(
        await api.post<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(v.id)}/gerar`, {
          pular_perguntas: !!v.pular_perguntas,
        }),
      ),
    onSuccess: invalidate,
  });
}

/** #37 — a stale `expected_versao` answers 409 (callers show "O roteiro mudou; recarregue"). */
export function useSalvarRoteiro() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; nome?: string; conteudo?: string; expected_versao: number }) => {
      const { id, ...corpo } = v;
      return unwrap(await api.put<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(id)}`, corpo));
    },
    onSuccess: invalidate,
  });
}

export function useFeedbackRoteiro() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; feedback: "gostei" | "nao_gostei"; motivo?: string }) =>
      unwrap(
        await api.post<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(v.id)}/feedback`, {
          feedback: v.feedback,
          ...(v.motivo ? { motivo: v.motivo } : {}),
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useReprocessarRoteiro() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; instrucoes_adicionais?: string }) =>
      unwrap(
        await api.post<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(v.id)}/reprocessar`, {
          ...(v.instrucoes_adicionais ? { instrucoes_adicionais: v.instrucoes_adicionais } : {}),
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useExcluirRoteiros() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (ids: string[]) =>
      unwrap(await api.post<Envelope<{ excluidos: number }>>(`${BASE}/excluir`, { ids })),
    onSuccess: invalidate,
  });
}
