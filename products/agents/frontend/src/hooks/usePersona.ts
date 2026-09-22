/**
 * Julia persona hooks — contract §E.2
 * (`GET`/`PUT /api/agents/julia/persona`).
 *
 * `PUT` is admin-only server-side (`require_admin`); the page also gates
 * the form on `useIsAdmin()` so a non-admin never sees an editable form
 * that would 403 on submit.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";

const PERSONA_KEY = ["agents", "julia", "persona"] as const;

export const PERSONA_MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"] as const;
export const PERSONA_EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

export interface Persona {
  versao: number;
  nome: string;
  papel: string;
  tom: string | null;
  system_prompt_append: string | null;
  model: string;
  effort: string;
  idioma: string;
  org_display_name: string | null;
  project_display_name: string | null;
  ativa: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PersonaUpdateInput {
  nome: string;
  papel: string;
  model: string;
  effort: string;
  tom?: string | null;
  system_prompt_append?: string | null;
  idioma?: string;
  org_display_name?: string | null;
  project_display_name?: string | null;
}

export function usePersona() {
  const query = useQuery<Persona>({
    queryKey: PERSONA_KEY,
    queryFn: () => api.get<Persona>("/api/agents/julia/persona"),
    // A 404 here means "Julia has no persona yet" (contract §E.2,
    // `code: "not_found"`) — a definitive, stable answer, not a transient
    // failure. Retrying it 3x just stretches the skeleton before the page
    // can fall back to its create-mode form. Any other status (5xx,
    // network) still gets react-query's normal retry.
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404 ? false : failureCount < 3,
  });

  const isNotFound = query.error instanceof ApiError && query.error.status === 404;

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    // A definitive "no persona yet" is not an error state — the page
    // renders its create-mode form instead. Only a genuine failure (5xx,
    // network) surfaces the error card.
    isError: query.isError && !isNotFound,
    isNotFound,
  };
}

export function useUpdatePersona() {
  const qc = useQueryClient();

  return useMutation<Persona, unknown, PersonaUpdateInput>({
    mutationFn: (payload) => api.put<Persona>("/api/agents/julia/persona", payload),
    onSuccess: (persona) => {
      qc.setQueryData(PERSONA_KEY, persona);
    },
  });
}
