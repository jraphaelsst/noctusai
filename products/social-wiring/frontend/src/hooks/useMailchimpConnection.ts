/**
 * Mailchimp connection hooks.
 *
 * Wraps `/api/mailchimp/connection` and `/api/mailchimp/audiences`.
 * GET /connection always returns 200 — `connected: false` means no key
 * stored, not an error. The FE uses this as a gate probe.
 *
 * Built on @tanstack/react-query v5. queryFns never return undefined.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

// ─── Types (mirror app/modules/mailchimp/schemas.py) ────────────────────────

export interface MailchimpConnectionOut {
  connected: boolean;
  server_prefix: string | null;
  audience_id: string | null;
  audience_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AudienceItem {
  id: string;
  name: string;
  member_count: number;
}

export interface AudiencesOut {
  items: AudienceItem[];
  total: number;
}

export interface PutConnectionBody {
  api_key: string;
  audience_id?: string;
}

export interface PatchConnectionBody {
  audience_id: string;
}

const BASE = "/api/mailchimp/connection";
const AUDIENCES_BASE = "/api/mailchimp/audiences";
const FAMILY_KEY = ["mailchimp"] as const;
const CONNECTION_KEY = [...FAMILY_KEY, "connection"] as const;
const AUDIENCES_KEY = [...FAMILY_KEY, "audiences"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

/** Always-200 probe. connected=false → show NotConnected state. */
export function useMailchimpConnection() {
  return useQuery<MailchimpConnectionOut>({
    queryKey: CONNECTION_KEY,
    queryFn: () => api.get<MailchimpConnectionOut>(BASE),
    staleTime: 30_000,
  });
}

/** Audience picker — only meaningful when connected=true. */
export function useMailchimpAudiences(enabled = true) {
  return useQuery<AudiencesOut>({
    queryKey: AUDIENCES_KEY,
    queryFn: () => api.get<AudiencesOut>(AUDIENCES_BASE),
    enabled,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useMailchimpConnectionMutations() {
  // Audiences, campaigns, segments and contacts all depend on the connection, so the family refreshes on settle.
  const invalidate = [FAMILY_KEY];
  const commitConnection = {
    queryKey: CONNECTION_KEY,
    commit: (_old: MailchimpConnectionOut | undefined, saved: MailchimpConnectionOut) => saved,
  };

  const put = useCacheWriteMutation<MailchimpConnectionOut, PutConnectionBody>({
    mutationFn: (body) => api.put<MailchimpConnectionOut>(BASE, body),
    targets: [commitConnection],
    invalidate,
  });

  const patch = useCacheWriteMutation<MailchimpConnectionOut, PatchConnectionBody>({
    mutationFn: (body) => api.patch<MailchimpConnectionOut>(BASE, body),
    targets: [commitConnection],
    invalidate,
  });

  const remove = useCacheWriteMutation<unknown, void>({
    mutationFn: () => api.delete(BASE),
    targets: [
      {
        queryKey: CONNECTION_KEY,
        optimistic: (old: MailchimpConnectionOut | undefined) =>
          old
            ? { ...old, connected: false, server_prefix: null, audience_id: null, audience_name: null }
            : old,
      },
    ],
    invalidate,
  });

  return { put, patch, remove };
}
