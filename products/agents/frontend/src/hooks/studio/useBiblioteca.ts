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
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { BibliotecaRefInput, BibliotecaRefs, BibliotecaSkill, SkillVersao, SkillVersaoMeta } from "@/api/studio/types-julia";
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

// ── library management (platform admin): skills, their versions, the draft editor ─────────────

type SkillList = { items: BibliotecaSkill[] };
type VersaoList = { items: SkillVersaoMeta[] };

const L = "/api/skills-biblioteca";
const metaOf = (v: SkillVersao): SkillVersaoMeta => ({
  id: v.id,
  versao: v.versao,
  status: v.status,
  notas: v.notas,
  publicada_em: v.publicada_em,
});

export function useSkillVersoes(chave: string | null | undefined) {
  const q = useQuery<VersaoList>({
    queryKey: studioKeys.bibliotecaVersoes(chave ?? ""),
    queryFn: () => api.get<VersaoList>(`${L}/${seg(chave as string)}/versoes`),
    enabled: !!chave,
    retry: false,
    placeholderData: undefined, // never paint another skill's versions under this one
  });
  return { ...toView(q), data: q.data?.items };
}

export function useSkillVersao(versaoId: string | null | undefined) {
  const q = useQuery<SkillVersao>({
    queryKey: studioKeys.bibliotecaVersao(versaoId ?? ""),
    queryFn: () => api.get<SkillVersao>(`${L}/versoes/${seg(versaoId as string)}`),
    enabled: !!versaoId,
    retry: false,
    placeholderData: undefined,
  });
  return toView(q);
}

/** Create/patch answer with a bare SkillOut (no pin state): keep the cached row's `versao_publicada`/`tem_rascunho`. */
const mergeRow = (old: SkillList | undefined, row: BibliotecaSkill, keepState: boolean): SkillList | undefined => {
  if (!old) return old;
  const prev = old.items.find((s) => s.chave === row.chave);
  const merged = prev && keepState ? { ...row, versao_publicada: prev.versao_publicada, tem_rascunho: prev.tem_rascunho } : row;
  return { ...old, items: prev ? old.items.map((s) => (s.chave === row.chave ? merged : s)) : [merged, ...old.items] };
};

export function useCriarSkill() {
  return useCacheWriteMutation<BibliotecaSkill, { chave: string; nome: string; descricao?: string | null }>({
    mutationFn: (body) => api.post<BibliotecaSkill>(L, body),
    targets: [{ queryKey: studioKeys.biblioteca(), commit: (old: SkillList | undefined, row) => mergeRow(old, row, false) }],
  });
}

export function useEditarSkill(chave: string) {
  return useCacheWriteMutation<BibliotecaSkill, { nome?: string; descricao?: string | null }>({
    mutationFn: (body) => api.patch<BibliotecaSkill>(`${L}/${seg(chave)}`, body),
    targets: [{ queryKey: studioKeys.biblioteca(), commit: (old: SkillList | undefined, row) => mergeRow(old, row, true) }],
  });
}

const setRascunhoFlag = (chave: string, value: boolean) => ({
  queryKey: studioKeys.biblioteca(),
  commit: (old: SkillList | undefined) =>
    old && { ...old, items: old.items.map((s) => (s.chave === chave ? { ...s, tem_rascunho: value } : s)) },
});

export function useCriarRascunhoSkill(chave: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<SkillVersao, { copiar_de?: string; notas?: string }>({
    mutationFn: (body) => api.post<SkillVersao>(`${L}/${seg(chave)}/versoes`, body),
    targets: [
      setRascunhoFlag(chave, true),
      {
        queryKey: studioKeys.bibliotecaVersoes(chave),
        commit: (old: VersaoList | undefined, v: SkillVersao) => old && { ...old, items: [metaOf(v), ...old.items] },
      },
    ],
    onSuccess: (v) => qc.setQueryData(studioKeys.bibliotecaVersao(v.id), v),
  });
}

export function useDescartarRascunhoSkill(chave: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<null, { versaoId: string }>({
    mutationFn: ({ versaoId }) => api.delete<null>(`${L}/versoes/${seg(versaoId)}`),
    targets: ({ versaoId }) => [
      {
        queryKey: studioKeys.bibliotecaVersoes(chave),
        optimistic: (old: VersaoList | undefined) => listOps.within(old, "items", (l) => listOps.remove(l, versaoId)),
      },
      setRascunhoFlag(chave, false),
    ],
    onSuccess: (_r, { versaoId }) => qc.removeQueries({ queryKey: studioKeys.bibliotecaVersao(versaoId) }),
  });
}

/** Every draft write answers the FULL version: commit it into its entry; the version list settles behind (notas). */
function useRascunhoWrite<TVars>(chave: string, versaoId: string, mutationFn: (vars: TVars) => Promise<SkillVersao>) {
  return useCacheWriteMutation<SkillVersao, TVars>({
    mutationFn,
    targets: [{ queryKey: studioKeys.bibliotecaVersao(versaoId), commit: (_old, v) => v }],
    invalidate: [studioKeys.bibliotecaVersoes(chave)],
  });
}

export function useSalvarRascunhoSkill(chave: string, versaoId: string) {
  return useRascunhoWrite<{ descricao_modelo?: string; corpo?: string; notas?: string }>(chave, versaoId, (body) =>
    api.patch<SkillVersao>(`${L}/versoes/${seg(versaoId)}`, body),
  );
}

export function useSalvarArquivoSkill(chave: string, versaoId: string) {
  return useRascunhoWrite<{ caminho: string; titulo?: string | null; conteudo: string }>(chave, versaoId, ({ caminho, ...body }) =>
    api.put<SkillVersao>(`${L}/versoes/${seg(versaoId)}/arquivos/${encodeURI(caminho)}`, body),
  );
}

export function useRemoverArquivoSkill(versaoId: string) {
  return useCacheWriteMutation<null, { caminho: string }>({
    mutationFn: ({ caminho }) => api.delete<null>(`${L}/versoes/${seg(versaoId)}/arquivos/${encodeURI(caminho)}`),
    targets: ({ caminho }) => [
      {
        queryKey: studioKeys.bibliotecaVersao(versaoId),
        optimistic: (old: SkillVersao | undefined) => old && { ...old, arquivos: old.arquivos.filter((a) => a.caminho !== caminho) },
      },
    ],
  });
}

export function usePublicarSkill(chave: string, versaoId: string) {
  return useCacheWriteMutation<SkillVersao, void>({
    mutationFn: () => api.post<SkillVersao>(`${L}/versoes/${seg(versaoId)}/publicar`, {}),
    targets: [
      { queryKey: studioKeys.bibliotecaVersao(versaoId), commit: (_old, v: SkillVersao) => v },
      {
        queryKey: studioKeys.biblioteca(),
        commit: (old: SkillList | undefined, v: SkillVersao) =>
          old && { ...old, items: old.items.map((s) => (s.chave === chave ? { ...s, versao_publicada: v.versao, tem_rascunho: false } : s)) },
      },
    ],
    // The previous published version turns "arquivada" server-side, and pins now report "nova versão".
    invalidate: [studioKeys.bibliotecaVersoes(chave), ["studio"]],
  });
}
