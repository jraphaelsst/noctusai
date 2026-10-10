/**
 * Segundo Cérebro — questionnaire hooks (contract §4 endpoints 4, 8–13).
 * Loading: two signals off `data`, never `isLoading`. The detail query polls
 * every 3 s while a review, a transcription or a synthesis is non-terminal.
 * Autosave writes the returned Answer straight into the cache (no refetch
 * storm per keystroke); the other mutations invalidate the cerebro family.
 */
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { CEREBRO_KEY, POLL_MS } from "@/hooks/useCerebro";
import { uploadMultipart } from "@/hooks/useCardHub";
import type { Answer, BrainDetail } from "@/types/cerebro";

const BASE = "/api/media-creation/cerebro";
const perguntasKey = (id: string | null) => [...CEREBRO_KEY, "perguntas", id] as const;
const enc = encodeURIComponent;

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

/** True while any answer is being reviewed/transcribed or the brain is synthesising. */
export function perguntasEmAndamento(b: BrainDetail | undefined): boolean {
  if (!b) return false;
  return (
    b.synthesis_status === "processing" ||
    b.answers.some(
      (a) =>
        a.review.status === "pending" ||
        a.transcricao?.status === "na_fila" ||
        a.transcricao?.status === "processando",
    )
  );
}

/** Transcription jobs still moving (na_fila / processando). */
export function transcricaoEmAndamento(b: BrainDetail | undefined): boolean {
  return !!b?.answers.some((a) => a.transcricao?.status === "na_fila" || a.transcricao?.status === "processando");
}

/** transcription-contract §4: 3 s for the first 30 s of a non-terminal run, then 10 s. */
export const POLL_RAPIDO_MS = POLL_MS;
export const POLL_LENTO_MS = 10_000;
export const POLL_JANELA_MS = 30_000;

export function useCerebroPerguntas(brainId: string | null) {
  const transcricaoDesde = useRef<number | null>(null);
  const query = useQuery({
    queryKey: perguntasKey(brainId),
    enabled: !!brainId,
    queryFn: async () => unwrap(await api.get<Envelope<BrainDetail>>(`${BASE}/brains/${enc(brainId as string)}`)),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!perguntasEmAndamento(d)) {
        transcricaoDesde.current = null;
        return false;
      }
      if (!transcricaoEmAndamento(d)) return POLL_MS;
      transcricaoDesde.current ??= Date.now();
      return Date.now() - transcricaoDesde.current < POLL_JANELA_MS ? POLL_RAPIDO_MS : POLL_LENTO_MS;
    },
    placeholderData: (prev) => (prev && prev.id === brainId ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!brainId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

function mesclarResposta(b: BrainDetail | undefined, a: Answer): BrainDetail | undefined {
  if (!b) return b;
  const existe = b.answers.some((x) => x.question_id === a.question_id);
  return { ...b, answers: existe ? b.answers.map((x) => (x.question_id === a.question_id ? a : x)) : [...b.answers, a] };
}

export function useSalvarResposta(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { questionId: string; text: string }) =>
      unwrap(
        await api.put<Envelope<Answer>>(`${BASE}/brains/${enc(brainId)}/answers/${enc(v.questionId)}`, {
          text: v.text,
        }),
      ),
    onSuccess: (a) => qc.setQueryData<BrainDetail>(perguntasKey(brainId), (b) => mesclarResposta(b, a)),
  });
}

export function useZerarRespostas(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.post<Envelope<{ deleted: number }>>(`${BASE}/brains/${enc(brainId)}/answers/reset`, { confirm: true })),
    onSuccess: () => qc.invalidateQueries({ queryKey: CEREBRO_KEY }),
  });
}

export function useRevisarRespostas(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (questionIds?: string[]) =>
      unwrap(
        await api.post<Envelope<{ queued: number }>>(
          `${BASE}/brains/${enc(brainId)}/review`,
          questionIds ? { question_ids: questionIds } : {},
        ),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: CEREBRO_KEY }),
  });
}

export function useDecidirSugestao(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { questionId: string; action: "accept" | "dismiss" }) =>
      unwrap(
        await api.post<Envelope<Answer>>(
          `${BASE}/brains/${enc(brainId)}/answers/${enc(v.questionId)}/suggestion`,
          { action: v.action },
        ),
      ),
    onSuccess: (a) => qc.setQueryData<BrainDetail>(perguntasKey(brainId), (b) => mesclarResposta(b, a)),
  });
}

export function useFinalizarRespostas(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { mode: "replace" | "append"; expected_version: number }) =>
      unwrap(await api.post<Envelope<{ brain: unknown }>>(`${BASE}/brains/${enc(brainId)}/synthesize`, v)),
    onSuccess: () => qc.invalidateQueries({ queryKey: CEREBRO_KEY }),
  });
}

/** Endpoint 13 — upload a recorded voice answer; the server transcribes async and
 *  appends the transcript to the answer text. Returns the updated Answer. */
export function useEnviarAudioResposta(brainId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { questionId: string; blob: Blob; mime: string }) => {
      const ext = v.mime.includes("ogg") ? "ogg" : v.mime.includes("mp4") ? "m4a" : v.mime.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.set("arquivo", v.blob, `resposta.${ext}`);
      return unwrap(
        await uploadMultipart<Envelope<Answer>>(`${BASE}/brains/${enc(brainId)}/answers/${enc(v.questionId)}/audio`, form),
      );
    },
    onSuccess: (a) => {
      qc.setQueryData<BrainDetail>(perguntasKey(brainId), (b) => mesclarResposta(b, a));
      void qc.invalidateQueries({ queryKey: perguntasKey(brainId) });
    },
  });
}
