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
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
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

/**
 * Pins are written to the DRAFT: the server answers with the draft's full pin list (it assigns
 * `nova_versao`), so this is commit-only — never optimistic. The answer carries its `version_id`, so
 * it lands in exactly the refs entry of that version; the compiled/payload views settle behind.
 */
function pinTargets(key: string) {
  return [
    {
      queryKey: ["studio", key, "biblioteca-refs"],
      match: "prefix" as const,
      commit: (old: BibliotecaRefs | undefined, result: BibliotecaRefs) =>
        old && old.version_id === result.version_id ? result : old,
    },
  ];
}

const pinInvalidate = (key: string) => [
  studioKeys.detail(key),
  studioKeys.compiledAll(key),
  ["studio", key, "payload"],
];

export function useFixarSkill(key: string) {
  return useCacheWriteMutation<BibliotecaRefs, { skill: string; ref: BibliotecaRefInput }>({
    mutationFn: ({ skill, ref }) => api.put<BibliotecaRefs>(`${base(key)}/draft/skills-biblioteca/${seg(skill)}`, ref),
    targets: pinTargets(key),
    invalidate: pinInvalidate(key),
  });
}

export function useRemoverSkillFixada(key: string) {
  return useCacheWriteMutation<BibliotecaRefs, { skill: string }>({
    mutationFn: ({ skill }) => api.delete<BibliotecaRefs>(`${base(key)}/draft/skills-biblioteca/${seg(skill)}`),
    targets: pinTargets(key),
    invalidate: pinInvalidate(key),
  });
}
