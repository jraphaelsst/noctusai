/**
 * Julia channel conversations (admin only, server-enforced):
 *   GET /api/conversations/channel?agent_key=&channel=
 *   GET /api/conversations/{id}/messages
 *
 * The channel credential is no longer managed here: platform admins grant it in "Conexões da plataforma"
 * (`hooks/useGrants.ts`); nobody copies or pastes a token.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const channelKeys = {
  conversations: (agentKey: string, channel: string) => ["agents", "channel", agentKey, "conversations", channel] as const,
  messages: (conversationId: string) => ["agents", "channel", "messages", conversationId] as const,
};

export interface ChannelConversation {
  id: string;
  titulo: string | null;
  status: string;
  last_message_at: string | null;
  created_at: string;
  channel: string | null;
  contact: Record<string, unknown> | null;
}

export interface ChannelMessage {
  id: string;
  role: string;
  texto: string;
  created_at: string;
}

export function useChannelConversations(agentKey: string, channel: string) {
  const q = useQuery<{ items: ChannelConversation[]; total: number }>({
    queryKey: channelKeys.conversations(agentKey, channel),
    queryFn: () => {
      const params = new URLSearchParams({ agent_key: agentKey });
      if (channel) params.set("channel", channel);
      return api.get(`/api/conversations/channel?${params.toString()}`);
    },
    enabled: !!agentKey,
    placeholderData: (prev) => prev,
  });
  return {
    data: q.data?.items,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
    isError: q.isError,
    error: q.error,
    refetch: () => void q.refetch(),
  };
}

export function useChannelMessages(conversationId: string | null) {
  const q = useQuery<{ items: ChannelMessage[]; total: number }>({
    queryKey: channelKeys.messages(conversationId ?? ""),
    queryFn: () => api.get(`/api/conversations/${encodeURIComponent(conversationId as string)}/messages`),
    enabled: !!conversationId,
    placeholderData: (prev) => prev,
  });
  return {
    data: q.data?.items,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
    isError: q.isError,
    error: q.error,
    refetch: () => void q.refetch(),
  };
}
