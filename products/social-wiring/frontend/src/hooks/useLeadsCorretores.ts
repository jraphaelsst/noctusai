/**
 * Lead corretores hooks — `/api/leads/corretores*` (the broker dimension +
 * its alias map, mirrors `useLeadsSources.ts` exactly per §5.2).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
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
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<LeadCorretor, unknown, LeadCorretorInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadCorretor>>(BASE, body);
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const update = useMutation<
    LeadCorretor,
    unknown,
    { id: string; body: Partial<LeadCorretorInput> }
  >({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<LeadCorretor>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  /** Same 409/`reassignTo` rule as sources — §5.2. */
  const remove = useMutation<unknown, unknown, { id: string; reassignTo?: string }>({
    mutationFn: ({ id, reassignTo }) => {
      const qs = reassignTo ? `?reassign_to=${encodeURIComponent(reassignTo)}` : "";
      return api.delete(`${BASE}/${encodeURIComponent(id)}${qs}`);
    },
    onSuccess: invalidateFamily,
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
  const qc = useQueryClient();
  const invalidateFamily = () => {
    qc.invalidateQueries({ queryKey: FAMILY_KEY });
    qc.invalidateQueries({ queryKey: ["leads", "list"] });
    qc.invalidateQueries({ queryKey: ["leads", "analytics"] });
  };

  const upsert = useMutation<
    LeadCorretorAlias,
    unknown,
    { alias: string; corretor_id: string }
  >({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadCorretorAlias>>(`${BASE}/aliases`, body);
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const remove = useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/aliases/${encodeURIComponent(id)}`),
    onSuccess: invalidateFamily,
  });

  return { upsert, remove };
}
