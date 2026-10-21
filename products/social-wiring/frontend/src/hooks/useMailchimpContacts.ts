/**
 * Mailchimp contacts hooks.
 *
 * Wraps `/api/mailchimp/contacts` (members of the default audience).
 * Email is the FE-visible identifier; the backend computes subscriber_hash.
 *
 * Built on @tanstack/react-query v5. queryFns never return undefined.
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface MemberOut {
  email: string;
  status: string;
  first_name: string | null;
  last_name: string | null;
  tags: string[];
  vip: boolean;
  last_changed: string;
}

export interface ContactsOut {
  items: MemberOut[];
  total: number;
}

export interface UpsertContactBody {
  status?: string;
  first_name?: string;
  last_name?: string;
  tags?: string[];
}

export interface ListContactsParams {
  status?: string;
  count?: number;
  offset?: number;
}

const BASE = "/api/mailchimp/contacts";
const FAMILY_KEY = ["mailchimp"] as const;
const CONTACTS_KEY = [...FAMILY_KEY, "contacts"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useMailchimpContacts(params?: ListContactsParams) {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.count != null) searchParams.set("count", String(params.count));
  if (params?.offset != null) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();

  return useQuery<ContactsOut>({
    queryKey: [...CONTACTS_KEY, params],
    queryFn: () => api.get<ContactsOut>(qs ? `${BASE}?${qs}` : BASE),
  });
}

export function useMailchimpContact(email: string | null) {
  return useQuery<MemberOut>({
    queryKey: [...CONTACTS_KEY, email],
    queryFn: () => api.get<MemberOut>(`${BASE}/${encodeURIComponent(email!)}`),
    enabled: !!email,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useMailchimpContactMutations() {
  // Members are keyed by `email`. Audience counts and campaign reach hang off the family, so it refreshes on settle.
  const invalidate = [FAMILY_KEY];

  const upsert = useCacheWriteMutation<MemberOut, { email: string; body: UpsertContactBody }>({
    mutationFn: ({ email, body }) =>
      api.put<MemberOut>(`${BASE}/${encodeURIComponent(email)}`, body),
    targets: ({ email }) => [
      {
        queryKey: CONTACTS_KEY,
        match: "prefix",
        commit: (old: ContactsOut | undefined, saved) => pageOps.prependNewest(old, saved, "email"),
      },
      {
        queryKey: [...CONTACTS_KEY, email],
        commit: (old: MemberOut | undefined, saved) => listOps.merge(old, saved),
      },
    ],
    invalidate,
  });

  const archive = useCacheWriteMutation<unknown, string>({
    mutationFn: (email) => api.delete(`${BASE}/${encodeURIComponent(email)}`),
    targets: (email) => [
      {
        queryKey: CONTACTS_KEY,
        match: "prefix",
        optimistic: (old: ContactsOut | undefined) => pageOps.remove(old, email, "email"),
      },
    ],
    invalidate,
  });

  return { upsert, archive };
}
