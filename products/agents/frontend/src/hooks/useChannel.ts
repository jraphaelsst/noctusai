/**
 * Julia channel surfaces (admin only, server-enforced):
 *   POST   /api/agents/{key}/channel-token            mint (raw `pk_*` ONCE)
 *   DELETE /api/agents/{key}/channel-token/{id}       revoke
 *   GET    /api/settings/api-tokens                   the org's tokens (seed; non-secret rows)
 *   GET    /api/conversations/channel?agent_key=&channel=
 *   GET    /api/conversations/{id}/messages
 *
 * The minted secret is returned by the mutation and is NEVER written to the
 * query cache (`gcTime: 0`; the cached row is built from the non-secret fields) — the dialog is its only holder.
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export const channelKeys = {
  tokens: () => ["agents", "channel", "tokens"] as const,
  conversations: (agentKey: string, channel: string) => ["agents", "channel", agentKey, "conversations", channel] as const,
  messages: (conversationId: string) => ["agents", "channel", "messages", conversationId] as const,
};

export interface ChannelTokenMinted {
  id: string;
  token: string;
  prefix: string;
  expires_at: string;
  scopes: string[];
}

export interface ApiTokenRow {
  id: string;
  label: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

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

/** `canal <product> · <agent>: <label>` — the label `channel_token_router` writes. */
export function channelTokenLabelPrefix(agentKey: string): string {
  return `canal social-wiring · ${agentKey}:`;
}

export function useChannelTokens(agentKey: string) {
  const q = useQuery<ApiTokenRow[]>({
    queryKey: channelKeys.tokens(),
    queryFn: () => api.get<ApiTokenRow[]>("/api/settings/api-tokens"),
    select: (rows) => rows.filter((r) => r.label.startsWith(channelTokenLabelPrefix(agentKey))),
    placeholderData: (prev) => prev,
  });
  return {
    data: q.data,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
    isError: q.isError,
    error: q.error,
    refetch: () => void q.refetch(),
  };
}

export function useMintChannelToken(agentKey: string) {
  return useCacheWriteMutation<ChannelTokenMinted, { label: string }>({
    mutationFn: ({ label }) =>
      api.post<ChannelTokenMinted>(`/api/agents/${encodeURIComponent(agentKey)}/channel-token`, {
        product: "social-wiring",
        label,
      }),
    gcTime: 0,
    // The new token's row is in the list after one round trip — without `token` (the secret).
    targets: [
      {
        queryKey: channelKeys.tokens(),
        commit: (old: ApiTokenRow[] | undefined, minted, { label }) =>
          listOps.replace<ApiTokenRow>(
            old,
            minted.id,
            {
              id: minted.id,
              // The server prefixes the stored label (`channelTokenLabelPrefix`); settle brings the exact text.
              label: `${channelTokenLabelPrefix(agentKey)} ${label}`,
              prefix: minted.prefix,
              scopes: minted.scopes,
              created_at: new Date().toISOString(),
              last_used_at: null,
              revoked_at: null,
            },
            "prepend",
          ),
      },
    ],
  });
}

export function useRevokeChannelToken(agentKey: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (tokenId) =>
      api.delete(`/api/agents/${encodeURIComponent(agentKey)}/channel-token/${encodeURIComponent(tokenId)}`),
    // Revoking is idempotent and predictable: the row flips on the click.
    targets: (tokenId) => [
      {
        queryKey: channelKeys.tokens(),
        optimistic: (old: ApiTokenRow[] | undefined) =>
          listOps.patch(old, tokenId, { revoked_at: new Date().toISOString() }),
      },
    ],
  });
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
