/**
 * Lead sources hooks — `/api/leads/sources*` (the canonical origem dimension
 * + its editable alias map, "Configuração" subtab). List is NOT paginated
 * (success_response, per §5.2) — the dimension is small (~15-20 rows).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
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
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<LeadSource, unknown, LeadSourceInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadSource>>(BASE, body);
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const update = useMutation<LeadSource, unknown, { id: string; body: Partial<LeadSourceInput> }>({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<LeadSource>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  /** 409 (with a decoded message) if leads still reference it and no `reassignTo` given — §5.2. */
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
  const qc = useQueryClient();
  const invalidateFamily = () => {
    qc.invalidateQueries({ queryKey: FAMILY_KEY });
    qc.invalidateQueries({ queryKey: ["leads", "list"] });
    qc.invalidateQueries({ queryKey: ["leads", "analytics"] });
  };

  /** Creates/repoints an alias, then re-links matching leads server-side (§5.2). */
  const upsert = useMutation<
    LeadSourceAlias,
    unknown,
    { alias: string; source_id: string }
  >({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<LeadSourceAlias>>(`${BASE}/aliases`, body);
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
