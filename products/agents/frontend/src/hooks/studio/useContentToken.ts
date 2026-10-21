/**
 * Platform-admin management of the `noctus.agents.content` MCP token (scope `studio:content-write`).
 *
 *   GET    /api/studio/plataforma/content-tokens        list (never the secret)
 *   POST   /api/studio/plataforma/content-token         mint { label, expira_em_dias: 1..365 | null = never }
 *   DELETE /api/studio/plataforma/content-token/{id}    revoke (idempotent)
 *
 * The raw secret exists only in the mint mutation's result (`gcTime: 0`) and the dialog that shows it.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
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

export function useMintContentToken() {
  const qc = useQueryClient();
  return useMutation<ContentTokenMinted, unknown, ContentTokenMintInput>({
    mutationFn: (payload) => api.post<ContentTokenMinted>("/api/studio/plataforma/content-token", payload),
    gcTime: 0,
    onSuccess: () => void qc.invalidateQueries({ queryKey: studioKeys.contentTokens() }),
  });
}

export function useRevokeContentToken() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`/api/studio/plataforma/content-token/${seg(id)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: studioKeys.contentTokens() }),
  });
}
