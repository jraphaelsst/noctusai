/**
 * Lead corretores hooks — `/api/leads/corretores*` (the broker dimension +
 * its alias map, mirrors `useLeadsSources.ts` exactly per §5.2).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import type { LeadCorretor, LeadCorretorAlias, LeadCorretorInput } from "@/pages/leads/types";

interface SuccessEnvelope<T> {
  data: T;
}

const BASE = "/api/leads/corretores";
const FAMILY_KEY = ["leads", "corretores"] as const;
const ALIASES_KEY = [...FAMILY_KEY, "aliases"] as const;

// ─── Corretores ──────────────────────────────────────────────────────────────

export function useLeadCorretores() {
  return useQuery<LeadCorretor[]>({
    queryKey: FAMILY_KEY,
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadCorretor[]>>(BASE);
      return res.data;
    },
  });
}

export function useLeadCorretorMutations() {
  const create = useCacheWriteMutation<LeadCorretor, LeadCorretorInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadCorretor>>(BASE, body);
      return res.data;
    },
    targets: [{ queryKey: FAMILY_KEY, commit: (old: LeadCorretor[] | undefined, saved) => listOps.append(old, saved) }],
  });

  const update = useCacheWriteMutation<LeadCorretor, { id: string; body: Partial<LeadCorretorInput> }>({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<LeadCorretor>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    // Patch (not replace): the list rows carry a server-computed `lead_count` the PATCH answer may omit.
    targets: ({ id, body }) => [
      {
        queryKey: FAMILY_KEY,
        optimistic: (old: LeadCorretor[] | undefined) => listOps.patch(old, id, body as Partial<LeadCorretor>),
        commit: (old: LeadCorretor[] | undefined, saved) => listOps.patch(old, saved.id, saved),
      },
    ],
  });

  /** Same 409/`reassignTo` rule as sources — §5.2. */
  const remove = useCacheWriteMutation<unknown, { id: string; reassignTo?: string }>({
    mutationFn: ({ id, reassignTo }) => {
      const qs = reassignTo ? `?reassign_to=${encodeURIComponent(reassignTo)}` : "";
      return api.delete(`${BASE}/${encodeURIComponent(id)}${qs}`);
    },
    // A reassign moves leads to another corretor: its `lead_count` converges on the settle.
    targets: ({ id }) => [
      { queryKey: FAMILY_KEY, optimistic: (old: LeadCorretor[] | undefined) => listOps.remove(old, id) },
    ],
  });

  return { create, update, remove };
}

// ─── Alias map ───────────────────────────────────────────────────────────────

export function useLeadCorretorAliases() {
  return useQuery<LeadCorretorAlias[]>({
    queryKey: ALIASES_KEY,
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadCorretorAlias[]>>(`${BASE}/aliases`);
      return res.data;
    },
  });
}

/** `?unmapped=true` — mirrors `useLeadSourceUnmapped` (§5.2: "mirrors the source-alias endpoints"). */
export interface UnmappedCorretorAlias {
  alias: string;
  count: number;
}

export function useLeadCorretorUnmapped() {
  return useQuery<UnmappedCorretorAlias[]>({
    queryKey: [...ALIASES_KEY, "unmapped"],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<UnmappedCorretorAlias[]>>(`${BASE}/aliases?unmapped=true`);
      return res.data;
    },
  });
}

export function useLeadCorretorAliasMutations() {
  // The lead lists and analytics group by corretor, so they refresh behind the alias write.
  const derived = [FAMILY_KEY, ["leads", "list"], ["leads", "analytics"]] as const;

  const upsert = useCacheWriteMutation<LeadCorretorAlias, { alias: string; corretor_id: string }>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadCorretorAlias>>(`${BASE}/aliases`, body);
      return res.data;
    },
    targets: [
      {
        queryKey: ALIASES_KEY,
        commit: (old: LeadCorretorAlias[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
    invalidate: [...derived],
  });

  const remove = useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/aliases/${encodeURIComponent(id)}`),
    targets: (id) => [
      { queryKey: ALIASES_KEY, optimistic: (old: LeadCorretorAlias[] | undefined) => listOps.remove(old, id) },
    ],
    invalidate: [...derived],
  });

  return { upsert, remove };
}
