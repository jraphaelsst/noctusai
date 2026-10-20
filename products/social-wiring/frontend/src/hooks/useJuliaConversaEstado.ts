/**
 * Julia's state in ONE conversation, as AGENTS reports it (julia-v2: agents decides; SW only displays).
 *
 *   GET /api/whatsapp/connections/{c}/chats/{chat}/agente  ->  {data: {thread_id, estado, pausado,
 *        reengajamento_suprimido, motivo, fonte}}
 *
 * `fonte` says where the value came from: `agents` (live), `espelho` (agents unreachable: the last mirrored value,
 * possibly stale) or `nenhuma` (agents has no thread for this chat: Julia never served it). The pause/resume toggle is
 * `PATCH` on the same path (see `useSetChatAgentePausado`); it invalidates this query.
 *
 * Not kept across chats (`placeholderData` deliberately absent): the state belongs to ONE conversation, so showing the
 * previous chat's value while the next loads would be a lie about the wrong lead.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type EstadoJulia = "ativo" | "pausado" | "concluido" | "encerrado" | "transferido";
export type FonteEstado = "agents" | "espelho" | "nenhuma";

export interface EstadoConversa {
  thread_id: string | null;
  estado: EstadoJulia | null;
  pausado: boolean;
  reengajamento_suprimido: boolean | null;
  motivo: string | null;
  fonte: FonteEstado;
}

export const juliaConversaEstadoKey = (connectionId: string | null, chatId: string | null) =>
  ["sw", "julia", "conversa-estado", connectionId, chatId] as const;

export function useJuliaConversaEstado(connectionId: string | null, chatId: string | null, enabled = true) {
  return useQuery({
    queryKey: juliaConversaEstadoKey(connectionId, chatId),
    enabled: enabled && !!connectionId && !!chatId,
    retry: false,
    queryFn: async () =>
      (
        await api.get<{ data: EstadoConversa }>(
          `/api/whatsapp/connections/${encodeURIComponent(connectionId as string)}/chats/${encodeURIComponent(chatId as string)}/agente`,
        )
      ).data,
  });
}

export const ROTULO_ESTADO: Record<EstadoJulia, string> = {
  ativo: "Julia atendendo",
  pausado: "Atendimento humano (Julia pausada)",
  concluido: "Julia concluiu",
  encerrado: "Conversa encerrada",
  transferido: "Transferido para uma pessoa",
};

/** Honest copy per source: what the chip may claim and what it must admit. */
export const AVISO_FONTE: Record<FonteEstado, string | null> = {
  agents: null,
  espelho: "Sem resposta do app de agentes agora: este é o último estado conhecido e pode estar desatualizado.",
  nenhuma: "A Julia ainda não atendeu esta conversa.",
};
