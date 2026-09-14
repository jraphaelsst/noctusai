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

const PERSONA_KEY = ["agents", "julia", "persona"] as const;

export const PERSONA_MODELS = ["claude-opus-5", "claude-sonnet-5"] as const;
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
  });

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
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
