/**
 * Lead sources hooks — `/api/leads/sources*` (the canonical origem dimension
 * + its editable alias map, "Configuração" subtab). List is NOT paginated
 * (success_response, per §5.2) — the dimension is small (~15-20 rows).
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { LeadSource, LeadSourceAlias, LeadSourceInput } from "@/pages/leads/types";

interface SuccessEnvelope<T> {
  data: T;
}

const BASE = "/api/leads/sources";
const FAMILY_KEY = ["leads", "sources"] as const;
const ALIASES_KEY = [...FAMILY_KEY, "aliases"] as const;

// ─── Sources ─────────────────────────────────────────────────────────────────

export function useLeadSources() {
  return useQuery<LeadSource[]>({
    queryKey: FAMILY_KEY,
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadSource[]>>(BASE);
      return res.data;
    },
  });
}

export function useLeadSourceMutations() {
  // Alias rows and the leads' source labels hang off a source, so the whole family refreshes on settle.
  const invalidate = [FAMILY_KEY];

  const create = useCacheWriteMutation<LeadSource, LeadSourceInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadSource>>(BASE, body);
      return res.data;
    },
    targets: [{ queryKey: FAMILY_KEY, commit: (old: LeadSource[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
    invalidate,
  });

  const update = useCacheWriteMutation<LeadSource, { id: string; body: Partial<LeadSourceInput> }>({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<LeadSource>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    targets: ({ id }) => [
      { queryKey: FAMILY_KEY, commit: (old: LeadSource[] | undefined, saved) => listOps.patch(old, id, saved) },
    ],
    invalidate,
  });

  const remove = useCacheWriteMutation<unknown, { id: string; reassignTo?: string }>({
    mutationFn: ({ id, reassignTo }) => {
      const qs = reassignTo ? `?reassign_to=${encodeURIComponent(reassignTo)}` : "";
      return api.delete(`${BASE}/${encodeURIComponent(id)}${qs}`);
    },
    targets: ({ id }) => [
      { queryKey: FAMILY_KEY, optimistic: (old: LeadSource[] | undefined) => listOps.remove(old, id) },
    ],
    invalidate,
  });

  return { create, update, remove };
}

// ─── Alias map ───────────────────────────────────────────────────────────────

export function useLeadSourceAliases() {
  return useQuery<LeadSourceAlias[]>({
    queryKey: ALIASES_KEY,
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadSourceAlias[]>>(`${BASE}/aliases`);
      return res.data;
    },
  });
}

/**
 * `?unmapped=true` — raw origens seen in the data with no alias yet (the
 * "map these first" queue). Distinct SHAPE from the mapped list per §5.2 —
 * `{alias, count}` like `ImportPreview.unmapped_origens`, not a full
 * `LeadSourceAlias` row (an unmapped origem has no `source_id` to attach).
 */
export interface UnmappedAlias {
  alias: string;
  count: number;
}

export function useLeadSourceUnmapped() {
  return useQuery<UnmappedAlias[]>({
    queryKey: [...ALIASES_KEY, "unmapped"],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<UnmappedAlias[]>>(`${BASE}/aliases?unmapped=true`);
      return res.data;
    },
  });
}

export function useLeadSourceAliasMutations() {
  // The leads lists/analytics carry the resolved source label, so they refresh once the alias map changes.
  const invalidate = [FAMILY_KEY, ["leads", "list"], ["leads", "analytics"]];

  const upsert = useCacheWriteMutation<LeadSourceAlias, { alias: string; source_id: string }>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadSourceAlias>>(`${BASE}/aliases`, body);
      return res.data;
    },
    targets: [
      { queryKey: ALIASES_KEY, commit: (old: LeadSourceAlias[] | undefined, saved) => listOps.replace(old, saved.id, saved) },
      {
        // The alias is mapped now: it leaves the "unmapped" queue.
        queryKey: [...ALIASES_KEY, "unmapped"],
        commit: (old: UnmappedAlias[] | undefined, saved) =>
          Array.isArray(old) ? old.filter((u) => u.alias !== saved.alias) : old,
      },
    ],
    invalidate,
  });

  const remove = useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/aliases/${encodeURIComponent(id)}`),
    targets: (id) => [
      { queryKey: ALIASES_KEY, optimistic: (old: LeadSourceAlias[] | undefined) => listOps.remove(old, id) },
    ],
    invalidate,
  });

  return { upsert, remove };
}
