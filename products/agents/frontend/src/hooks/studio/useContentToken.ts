/**
 * Platform-admin management of the `noctus.agents.content` MCP token (scope `studio:content-write`).
 *
 *   GET    /api/studio/plataforma/content-tokens        list (never the secret)
 *   POST   /api/studio/plataforma/content-token         mint { label, expira_em_dias: 1..365 | null = never }
 *   DELETE /api/studio/plataforma/content-token/{id}    revoke (idempotent)
 *
 * The raw secret exists only in the mint mutation's result (`gcTime: 0`) and the dialog that shows it.
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import { editList } from "../cacheEnvelope";
import { seg, studioKeys, toView } from "./keys";

export type ContentTokenStatus = "ativo" | "expirado" | "revogado";

export interface ContentTokenRow {
  id: string;
  label: string;
  prefix: string;
  scopes: string[];
  created_at: string | null;
  created_by: string | null;
  /** `null` = never expires. */
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  status: ContentTokenStatus;
}

export interface ContentTokenMinted {
  id: string;
  token: string;
  prefix: string;
  expires_at: string | null;
  scopes: string[];
}

export interface ContentTokenMintInput {
  label: string;
  /** `null` = never expires. */
  expira_em_dias: number | null;
}

export function useContentTokens() {
  const q = useQuery<{ itens: ContentTokenRow[] }>({
    queryKey: studioKeys.contentTokens(),
    queryFn: () => api.get<{ itens: ContentTokenRow[] }>("/api/studio/plataforma/content-tokens"),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}

type TokenList = { itens: ContentTokenRow[] };

export function useMintContentToken() {
  // The raw secret (`result.token`) lives ONLY in this mutation's result (`gcTime: 0`) and the dialog —
  // the cached row is built from the server's non-secret fields + the input label, never the token.
  return useCacheWriteMutation<ContentTokenMinted, ContentTokenMintInput>({
    mutationFn: (payload) => api.post<ContentTokenMinted>("/api/studio/plataforma/content-token", payload),
    gcTime: 0,
    targets: [
      {
        queryKey: studioKeys.contentTokens(),
        commit: (old: TokenList | undefined, minted, vars) =>
          editList(old, "itens", (l) =>
            listOps.replace<ContentTokenRow>(
              l,
              minted.id,
              {
                id: minted.id,
                label: vars.label,
                prefix: minted.prefix,
                scopes: minted.scopes,
                created_at: new Date().toISOString(),
                created_by: null,
                expires_at: minted.expires_at,
                last_used_at: null,
                revoked_at: null,
                status: "ativo",
              },
              "prepend",
            ),
          ),
      },
    ],
  });
}

export function useRevokeContentToken() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/studio/plataforma/content-token/${seg(id)}`),
    // Revoking is idempotent and predictable: flip the row on the click; settle brings the server's timestamp.
    targets: (id) => [
      {
        queryKey: studioKeys.contentTokens(),
        optimistic: (old: TokenList | undefined) =>
          editList(old, "itens", (l: ContentTokenRow[]) =>
            l.map((r) =>
              r.id === id ? { ...r, status: "revogado" as const, revoked_at: r.revoked_at ?? new Date().toISOString() } : r,
            ),
          ),
      },
    ],
  });
}
