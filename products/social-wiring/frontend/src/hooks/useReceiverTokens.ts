/**
 * Per-advertiser receiver URLs — TanStack Query over
 * `/api/portals/receiver-tokens`.
 *
 * These are the URLs an operator pastes into a client's Canal Pro
 * ("Receber leads no CRM"). Grupo OLX issues one SECRET_KEY per CRM, not
 * per advertiser, so the path token is the only thing that says whose
 * lead a delivery is.
 *
 * 🔴 The plaintext URL exists exactly once, in the mint response. It is
 * never stored and never returned again — `useReceiverTokens` lists only
 * digests and prefixes. That is why `mint` returns the URL to the caller
 * instead of relying on a refetch to reveal it: a refetch cannot.
 *
 * 🔴 Loading is gated on `isPending || isFetching`, never `isLoading`.
 * Under TanStack v5 `isLoading` is false during a background refetch, so
 * an `isEmpty` branch renders "no URLs yet" over URLs that exist — which
 * here would invite an operator to mint a duplicate for a client who
 * already has one. Keeper: `check_lying_loading_state`.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

const BASE = "/api/portals/receiver-tokens";

export const RECEIVER_TOKENS_KEY = ["portals", "receiver-tokens"] as const;

/** Mirrors the `provider` CHECK in migration 053. */
export type ReceiverProvider = "olx" | "imovelweb";

export interface ReceiverToken {
  id: string;
  provider: ReceiverProvider;
  label: string;
  token_prefix: string;
  created_at: string | null;
  /** Null means this URL has never received a delivery. */
  last_seen_at: string | null;
  revoked_at: string | null;
}

export interface MintedReceiverToken {
  id: string;
  provider: ReceiverProvider;
  label: string;
  token_prefix: string;
  /** Contains the plaintext token. Shown once; never retrievable again. */
  url: string;
}

export function useReceiverTokens(provider?: ReceiverProvider) {
  const query = useQuery({
    queryKey: [...RECEIVER_TOKENS_KEY, provider ?? "all"],
    queryFn: () =>
      api.get<ReceiverToken[]>(
        provider ? `${BASE}?provider=${encodeURIComponent(provider)}` : BASE,
      ),
  });

  const tokens = query.data ?? [];

  // Split here rather than in the component so every consumer agrees on
  // what "active" means — a revoked URL still resolves to nothing, and
  // showing it alongside live ones has already confused one reader of
  // the equivalent OLX card.
  const active = tokens.filter((token) => !token.revoked_at);
  const revoked = tokens.filter((token) => token.revoked_at);

  // The signal an operator actually needs: a URL that was minted but has
  // never received anything is the signature of a wrong paste into Canal
  // Pro, which otherwise looks identical to "a quiet week".
  const neverUsed = active.filter((token) => !token.last_seen_at);

  return {
    ...query,
    tokens,
    active,
    revoked,
    neverUsed,
    /** See the module header — NOT `isLoading`. */
    loading: query.isPending || query.isFetching,
    isEmpty:
      !query.isPending && !query.isFetching && tokens.length === 0,
  };
}

export function useMintReceiverToken() {
  return useCacheWriteMutation<MintedReceiverToken, { provider: ReceiverProvider; label: string }>({
    mutationFn: (body) => api.post<MintedReceiverToken>(BASE, body),
    // The minted answer (minus the one-time URL) is the new list row: it lands in the "all" list and
    // in its own provider's list, never in the other provider's.
    targets: ({ provider }) =>
      [...new Set([provider, "all"])].map((slot) => ({
        queryKey: [...RECEIVER_TOKENS_KEY, slot] as const,
        commit: (old: ReceiverToken[] | undefined, saved: MintedReceiverToken) =>
          listOps.replace(old, saved.id, {
            id: saved.id,
            provider: saved.provider,
            label: saved.label,
            token_prefix: saved.token_prefix,
            created_at: new Date().toISOString(),
            last_seen_at: null,
            revoked_at: null,
          }),
      })),
  });
}

export function useRevokeReceiverToken() {
  return useCacheWriteMutation<{ status: string; id: string }, string>({
    mutationFn: (tokenId) =>
      api.delete<{ status: string; id: string }>(
        `${BASE}/${encodeURIComponent(tokenId)}`,
      ),
    // A revoked URL resolves to nothing at once; the row stays (revoked) in every list.
    targets: (tokenId) => [
      {
        queryKey: RECEIVER_TOKENS_KEY,
        match: "prefix",
        optimistic: (old: ReceiverToken[] | undefined) =>
          listOps.patch(old, tokenId, { revoked_at: new Date().toISOString() }),
      },
    ],
  });
}
