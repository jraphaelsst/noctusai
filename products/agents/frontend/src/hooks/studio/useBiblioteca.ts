/**
 * Agent Studio — the shared skills LIBRARY and an agent version's pins (CONTRACT D7/D8, §4.2).
 * Routes live on branch `feat/julia-v2-a-skills` (`skills_biblioteca_router.py`); platform admin
 * only (a skill body is platform IP).
 *
 *   GET /api/skills-biblioteca · /{chave}/versoes
 *   GET /api/studio/agents/{key}/versions/{vid}/skills-biblioteca   (pins, with `nova_versao`)
 *   GET /api/studio/agents/{key}/draft/skills-biblioteca
 *   PUT|DELETE /api/studio/agents/{key}/draft/skills-biblioteca/{skill}
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BibliotecaRefInput, BibliotecaRefs, BibliotecaSkill } from "@/api/studio/types-julia";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

const base = (key: string) => `/api/studio/agents/${seg(key)}`;

export function useBibliotecaSkills() {
  const q = useQuery<{ items: BibliotecaSkill[] }>({
    queryKey: studioKeys.biblioteca(),
    queryFn: () => api.get<{ items: BibliotecaSkill[] }>("/api/skills-biblioteca"),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return { ...toView(q), data: q.data?.items };
}

export function useBibliotecaRefs(key: string, versionId: string | null | undefined) {
  const q = useQuery<BibliotecaRefs>({
    queryKey: studioKeys.bibliotecaRefs(key, versionId ?? ""),
    queryFn: () => api.get<BibliotecaRefs>(`${base(key)}/versions/${seg(versionId as string)}/skills-biblioteca`),
    enabled: !!key && !!versionId,
    retry: false,
    placeholderData: keepWithinAgent<BibliotecaRefs>(key),
  });
  return { ...toView(q), data: q.data?.items };
}

function useAfterPin(key: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["studio", key, "biblioteca-refs"] });
    void qc.invalidateQueries({ queryKey: studioKeys.detail(key) });
    void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
    void qc.invalidateQueries({ queryKey: ["studio", key, "payload"] });
  };
}

export function useFixarSkill(key: string) {
  const after = useAfterPin(key);
  return useMutation<BibliotecaRefs, unknown, { skill: string; ref: BibliotecaRefInput }>({
    mutationFn: ({ skill, ref }) => api.put<BibliotecaRefs>(`${base(key)}/draft/skills-biblioteca/${seg(skill)}`, ref),
    onSuccess: after,
  });
}

export function useRemoverSkillFixada(key: string) {
  const after = useAfterPin(key);
  return useMutation<BibliotecaRefs, unknown, { skill: string }>({
    mutationFn: ({ skill }) => api.delete<BibliotecaRefs>(`${base(key)}/draft/skills-biblioteca/${seg(skill)}`),
    onSuccess: after,
  });
}
