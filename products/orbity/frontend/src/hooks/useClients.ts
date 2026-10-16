/**
 * Clients + leads lookup hooks — feed the shared ClientSelect / LeadSelect
 * pickers (and name lookups for tables). Backend: GET /api/clients,
 * GET /api/crm/leads (both `{ items, total, page, page_size }`).
 */
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface ClientOption {
  id: string;
  /** Nome fantasia (falls back to the legal name server-side). */
  name: string;
  /** Razão Social -- what contracts and the payment gateway use. */
  legal_name?: string;
  company: string | null;
  active: boolean;
}

export interface LeadOption {
  id: string;
  name: string;
  company: string | null;
}

interface Page<T> {
  items: T[];
  total: number;
}

export function useClientOptions() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['orbity-client-options'],
    queryFn: async () => {
      const res = await api.get<Page<ClientOption>>('/api/clients', {
        active_only: true,
        page: 1,
        page_size: 200,
      });
      return res.items;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useLeadOptions() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['orbity-lead-options'],
    queryFn: async () => {
      const res = await api.get<Page<LeadOption>>('/api/crm/leads', {
        page: 1,
        page_size: 200,
      });
      return res.items;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

/** id -> display name; falls back to the id only while the list is unresolved. */
export function nameLookup(
  options: { id: string; name: string }[] | undefined,
): (id: string | null | undefined) => string | null {
  const map = new Map((options ?? []).map((o) => [o.id, o.name]));
  return (id) => (id ? (map.get(id) ?? null) : null);
}
