/**
 * Agent Studio — lead conversations of a channel agent (CONTRACT §6; org ADMIN only, LGPD).
 *
 *   GET   /api/conversations/channel?agent_key=            list (stripped: no prompt internals)
 *   GET   /api/studio/threads/{id}/mensagens?limite=        lead / agent / human / event lines, author labelled
 *   PATCH /api/studio/threads/{id}/participantes/{key}      per-thread pause / resume (actor = the admin)
 *
 * GAP: no studio route returns a thread's participants/state (only the channel-token `GET
 * /api/channels/threads/{id}` does), so the pause/resume state shown is the server's answer to the
 * last PATCH — never a client guess. NOC-REMEDIATE[studio-thread-state-read]: add `participantes`
 * to the channel list or a studio thread GET. — 2026-10-20
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CanalConversas,
  MensagemThread,
  Participante,
  ParticipanteEstadoInput,
} from "@/api/studio/types-julia";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export function useCanalConversas(key: string, enabled = true) {
  const q = useQuery<CanalConversas>({
    queryKey: studioKeys.canal(key),
    queryFn: () => api.get<CanalConversas>("/api/conversations/channel", { agent_key: key }),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<CanalConversas>(key),
  });
  return { ...toView(q), data: q.data?.items };
}

export function useThreadMensagens(key: string, threadId: string | null) {
  const q = useQuery<MensagemThread[]>({
    queryKey: studioKeys.threadMensagens(key, threadId ?? ""),
    queryFn: () => api.get<MensagemThread[]>(`/api/studio/threads/${seg(threadId as string)}/mensagens`, { limite: 100 }),
    enabled: !!key && !!threadId,
    retry: false,
    // A different thread must never show under the previous one.
    placeholderData: undefined,
  });
  return toView(q);
}

export function useAlterarParticipante(key: string) {
  const qc = useQueryClient();
  return useMutation<Participante, unknown, { threadId: string; input: ParticipanteEstadoInput }>({ // noc-allow: invalidate-only — the answer (a Participante) is not part of any cached read (see GAP above); the lines/controls it changes are server-generated events
    mutationFn: ({ threadId, input }) =>
      api.patch<Participante>(`/api/studio/threads/${seg(threadId)}/participantes/${seg(key)}`, input),
    onSuccess: (_p, { threadId }) => {
      void qc.invalidateQueries({ queryKey: studioKeys.canal(key) });
      void qc.invalidateQueries({ queryKey: studioKeys.threadMensagens(key, threadId) });
      void qc.invalidateQueries({ queryKey: studioKeys.controle(key) });
    },
  });
}
