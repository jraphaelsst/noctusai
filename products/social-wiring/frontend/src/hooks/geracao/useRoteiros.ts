/**
 * Roteiros (Meus roteiros + Roteiro Avançado) over `/api/media-creation/roteiros`
 * (contract §4.5 #32–#40). Responses arrive wrapped in `{success, data}`.
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * never `isLoading`. The real status drives the 3 s poll (contract §3.2): only
 * `criando` / `processando` are moving — `perguntas` waits for the user. The poll
 * goes through `jobPolling`, so it keeps running in a background tab.
 * Every mutation invalidates the whole `["sw","geracao"]` family AND the Esteira
 * board/post family: a post card carries its roteiro's status chip and the
 * roteiro worker never touches the post row, so the board only learns about a
 * roteiro status change from here. `useRoteiro` does the same when its poll sees
 * a run reach a terminal status.
 */
import { useEffect, useRef } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";

import { emAndamento } from "@/components/geracao/labels";
import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
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
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: GERACAO_KEY }),
      qc.invalidateQueries({ queryKey: [ESTEIRA_PIPELINE_KEY] }),
      qc.invalidateQueries({ queryKey: ESTEIRA_KEY }),
    ]);
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
    ...jobPolling((d: { items: RoteiroResumo[]; total: number } | undefined) => algumRoteiroEmAndamento(d?.items), ROTEIROS_POLL_MS),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useRoteiro(id: string | null) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: detalheKey(id),
    enabled: !!id,
    queryFn: async () => unwrap(await api.get<Envelope<Roteiro>>(`${BASE}/${encodeURIComponent(id as string)}`)),
    ...jobPolling((d: Roteiro | undefined) => !!d && emAndamento(d.status), ROTEIROS_POLL_MS),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });

  // A run leaving criando/processando changes the Esteira card chip and the
  // roteiro lists — refresh them now instead of waiting on their own poll.
  const anterior = useRef<{ id: string; status: Roteiro["status"] } | null>(null);
  const dados = query.data;
  useEffect(() => {
    if (!dados) return;
    const prev = anterior.current;
    anterior.current = { id: dados.id, status: dados.status };
    if (prev && prev.id === dados.id && emAndamento(prev.status) && !emAndamento(dados.status)) {
      void qc.invalidateQueries({ queryKey: [ESTEIRA_PIPELINE_KEY] });
      void qc.invalidateQueries({ queryKey: ESTEIRA_KEY });
      void qc.invalidateQueries({
        queryKey: [...GERACAO_KEY, "roteiros"],
        predicate: (q) => q.queryKey[3] !== "detalhe",
      });
    }
  }, [dados?.id, dados?.status]); // eslint-disable-line react-hooks/exhaustive-deps

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
  /** Beat order; the server defaults to "cta_inicio" when omitted. */
  estrutura?: Roteiro["estrutura"];
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
