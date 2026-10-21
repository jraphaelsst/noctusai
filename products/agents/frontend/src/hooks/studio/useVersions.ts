/**
 * Agent Studio — versions, the draft, skills, skill files, diff, publish
 * (CONTRACT §D1).
 *
 * Invalidation map (what each write can change):
 *   - any draft write      → the draft's `VersionDetail` (set from the
 *                            response when the route returns one), the agent
 *                            detail (`versoes[]` carries `compiled_hash`, which
 *                            the backend refreshes on every draft save), and
 *                            every compiled view of this agent.
 *   - create / discard     → + the agent list (`tem_rascunho`).
 *   - publish              → + the agent list (`versao_ativa`) and every
 *                            version (the previous `ativa` became `substituida`).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation, type CacheWriteTarget } from "@noctusai/lib/cache-writes";
import { skillFilesBatchPath } from "@/api/studio/batchPaths";
import { api } from "@/lib/api";
import type {
  DraftCreateInput,
  DraftPatchInput,
  PublishInput,
  SectionsReplaceInput,
  Skill,
  SkillCreateInput,
  SkillFile,
  SkillFileBatchItem,
  SkillFilesBatchResponse,
  SkillFileSummary,
  SkillFileUpsertInput,
  SkillPatchInput,
  VersionDetail,
  VersionDiff,
} from "@/api/studio/types";
import { editList } from "../cacheEnvelope";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";
import { useStudioAgent } from "./useStudioAgents";

const base = (key: string) => `/api/studio/agents/${seg(key)}`;

/**
 * Every draft write is COMMIT-ONLY, never optimistic: the server owns the version's identity,
 * `compiled_hash` and ordering (versioned / CAS-protected prompt content). What the route returns is
 * written into the cache the moment it arrives; the derived views settle behind.
 */
const draftDerived = (key: string) => [
  studioKeys.detail(key),
  studioKeys.compiledAll(key),
  ["studio", key, "diff"],
];

/** Write a whole `VersionDetail` the route returned (seeds the entry even if it was never read). */
function useSeedVersion(key: string) {
  const qc = useQueryClient();
  return (version: VersionDetail) => qc.setQueryData(studioKeys.version(key, version.id), version);
}

/** The draft's cached `VersionDetail`: edit its `skills` with what the skill route answered. */
const draftSkills = <TData, TVars>(
  key: string,
  draftId: string | null,
  commit: (skills: Skill[], result: TData, vars: TVars, tempId: string) => Skill[] | undefined,
) =>
  (draftId
    ? [
        {
          queryKey: studioKeys.version(key, draftId),
          commit: (old: VersionDetail | undefined, result: TData, vars: TVars, ctx: { tempId: string }) =>
            editList(old, "skills", (l) => commit(l, result, vars, ctx.tempId)),
        },
      ]
    : []) as CacheWriteTarget<TData, TVars, any>[];

// ── Reads ─────────────────────────────────────────────────────────────────────

/**
 * The agent detail plus its two distinguished versions (§A3: at most one
 * `rascunho`, at most one `ativa`). Shares the detail query's cache entry.
 */
export function useAgentVersionRefs(key: string) {
  const view = useStudioAgent(key);
  const versoes = view.data?.versoes ?? [];
  return {
    ...view,
    draft: versoes.find((v) => v.status === "rascunho") ?? null,
    ativa: versoes.find((v) => v.status === "ativa") ?? null,
  };
}

export function useVersion(key: string, vid: string | null | undefined) {
  const q = useQuery<VersionDetail>({
    queryKey: studioKeys.version(key, vid ?? ""),
    queryFn: () => api.get<VersionDetail>(`${base(key)}/versions/${seg(vid as string)}`),
    enabled: !!key && !!vid,
    placeholderData: keepWithinAgent<VersionDetail>(key),
  });
  return toView(q);
}

export function useSkillFile(key: string, skillId: string | null, fileId: string | null) {
  const q = useQuery<SkillFile>({
    queryKey: studioKeys.skillFile(key, skillId ?? "", fileId ?? ""),
    queryFn: () =>
      api.get<SkillFile>(`${base(key)}/skills/${seg(skillId as string)}/files/${seg(fileId as string)}`),
    enabled: !!key && !!skillId && !!fileId,
    // Kept for continuity while switching files; the editor seeds its form
    // only when `isPlaceholderData` is false, so file A's text never lands
    // in file B's form.
    placeholderData: keepWithinAgent<SkillFile>(key),
  });
  return toView(q);
}

export function useVersionDiff(key: string, a: string | null, b: string | null) {
  const q = useQuery<VersionDiff>({
    queryKey: studioKeys.diff(key, a ?? "", b ?? ""),
    queryFn: () => api.get<VersionDiff>(`${base(key)}/versions/${seg(a as string)}/diff/${seg(b as string)}`),
    enabled: !!key && !!a && !!b && a !== b,
    placeholderData: keepWithinAgent<VersionDiff>(key),
  });
  return toView(q);
}

// ── Draft lifecycle ───────────────────────────────────────────────────────────

export function useCreateDraft(key: string) {
  const seed = useSeedVersion(key);
  return useCacheWriteMutation<VersionDetail, DraftCreateInput | void>({
    mutationFn: (payload) => api.post<VersionDetail>(`${base(key)}/draft`, payload ?? {}),
    targets: [],
    invalidate: [...draftDerived(key), studioKeys.list()],
    onSuccess: seed,
  });
}

export function useDiscardDraft(key: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<null, { draftId: string }>({
    mutationFn: () => api.delete<null>(`${base(key)}/draft`),
    targets: [],
    invalidate: [...draftDerived(key), studioKeys.list()],
    onSuccess: (_r, { draftId }) => {
      qc.removeQueries({ queryKey: studioKeys.version(key, draftId) });
    },
  });
}

export function useUpdateDraft(key: string) {
  const seed = useSeedVersion(key);
  return useCacheWriteMutation<VersionDetail, DraftPatchInput>({
    mutationFn: (payload) => api.patch<VersionDetail>(`${base(key)}/draft`, payload),
    targets: [],
    invalidate: draftDerived(key),
    onSuccess: seed,
  });
}

export function useSaveSections(key: string) {
  const seed = useSeedVersion(key);
  return useCacheWriteMutation<VersionDetail, SectionsReplaceInput>({
    mutationFn: (payload) => api.put<VersionDetail>(`${base(key)}/draft/sections`, payload),
    targets: [],
    invalidate: draftDerived(key),
    onSuccess: seed,
  });
}

export function usePublishDraft(key: string) {
  const seed = useSeedVersion(key);
  return useCacheWriteMutation<VersionDetail, PublishInput>({
    mutationFn: (payload) => api.post<VersionDetail>(`${base(key)}/draft/publish`, payload),
    // The previous `ativa` became `substituida`, so every other cached version is refreshed too.
    targets: [],
    invalidate: [studioKeys.versions(key), ...draftDerived(key), studioKeys.list()],
    onSuccess: seed,
  });
}

// ── Draft skills + files ──────────────────────────────────────────────────────
// Skill routes return the `Skill` (not the whole version), so the answer is committed into the
// draft's `VersionDetail.skills` (commit-only — the server assigns ids/ordem and refreshes the hash).

export function useCreateSkill(key: string, draftId: string | null) {
  return useCacheWriteMutation<Skill, SkillCreateInput>({
    mutationFn: (payload) => api.post<Skill>(`${base(key)}/draft/skills`, payload),
    targets: draftSkills<Skill, SkillCreateInput>(key, draftId, (l, saved, _v, tempId) =>
      listOps.replace(l, tempId, saved),
    ),
    invalidate: draftDerived(key),
  });
}

export function useUpdateSkill(key: string, draftId: string | null) {
  return useCacheWriteMutation<Skill, { skillId: string; patch: SkillPatchInput }>({
    mutationFn: ({ skillId, patch }) => api.patch<Skill>(`${base(key)}/draft/skills/${seg(skillId)}`, patch),
    targets: draftSkills<Skill, { skillId: string; patch: SkillPatchInput }>(key, draftId, (l, saved, { skillId }) =>
      listOps.replace(l, skillId, saved),
    ),
    invalidate: draftDerived(key),
  });
}

export function useDeleteSkill(key: string, draftId: string | null) {
  return useCacheWriteMutation<null, { skillId: string }>({
    mutationFn: ({ skillId }) => api.delete<null>(`${base(key)}/draft/skills/${seg(skillId)}`),
    targets: draftSkills<null, { skillId: string }>(key, draftId, (l, _r, { skillId }) => listOps.remove(l, skillId)),
    invalidate: draftDerived(key),
  });
}

/** Insert / replace one file summary (matched by `caminho`, the upsert key) inside its skill. */
function withFile(skills: Skill[], skillId: string, file: SkillFileSummary): Skill[] {
  return skills.map((s) =>
    s.id !== skillId
      ? s
      : {
          ...s,
          arquivos: s.arquivos.some((f) => f.id === file.id || f.caminho === file.caminho)
            ? s.arquivos.map((f) => (f.id === file.id || f.caminho === file.caminho ? file : f))
            : [...s.arquivos, file],
        },
  );
}

export function useUpsertSkillFile(key: string, draftId: string | null) {
  type Vars = { skillId: string; file: SkillFileUpsertInput };
  return useCacheWriteMutation<SkillFileSummary, Vars>({
    mutationFn: ({ skillId, file }) =>
      api.put<SkillFileSummary>(`${base(key)}/draft/skills/${seg(skillId)}/files`, file),
    targets: draftSkills<SkillFileSummary, Vars>(key, draftId, (l, saved, { skillId }) => withFile(l, skillId, saved)),
    // The open file's text changed: its own read refreshes in the background.
    invalidate: ({ skillId }) => [...draftDerived(key), ["studio", key, "skill-file", skillId]],
  });
}

/**
 * ONE call to `skillFilesBatchPath` (max `SKILL_FILES_BATCH_MAX` files —
 * `@/api/studio/batchPaths.ts`). Like `useBatchCreateDocuments`
 * (`useKnowledge.ts`), chunking belongs to the caller (`sendInChunks`,
 * `@/lib/batchUpload.ts`), not this hook.
 */
export function useBatchUpsertSkillFiles(key: string, draftId: string | null) {
  type Vars = { skillId: string; arquivos: SkillFileBatchItem[] };
  return useCacheWriteMutation<SkillFilesBatchResponse, Vars>({
    mutationFn: ({ skillId, arquivos }) =>
      api.put<SkillFilesBatchResponse>(skillFilesBatchPath(key, skillId), { arquivos }),
    // Each stored file the batch answered for lands in its skill; failed entries (no id) wait for the refetch.
    targets: draftSkills<SkillFilesBatchResponse, Vars>(key, draftId, (l, res, { skillId }) =>
      res.resultados.reduce(
        (skills, r) =>
          r.id && !r.erro
            ? withFile(skills, skillId, { id: r.id, caminho: r.caminho, titulo: r.titulo ?? null, chars: r.chars ?? 0 })
            : skills,
        l,
      ),
    ),
    invalidate: ({ skillId }) => [...draftDerived(key), ["studio", key, "skill-file", skillId]],
  });
}

export function useDeleteSkillFile(key: string, draftId: string | null) {
  const qc = useQueryClient();
  type Vars = { skillId: string; fileId: string };
  return useCacheWriteMutation<null, Vars>({
    mutationFn: ({ skillId, fileId }) =>
      api.delete<null>(`${base(key)}/draft/skills/${seg(skillId)}/files/${seg(fileId)}`),
    targets: draftSkills<null, Vars>(key, draftId, (l, _r, { skillId, fileId }) =>
      l.map((s) => (s.id === skillId ? { ...s, arquivos: s.arquivos.filter((f) => f.id !== fileId) } : s)),
    ),
    invalidate: draftDerived(key),
    onSuccess: (_r, { skillId, fileId }) => {
      qc.removeQueries({ queryKey: studioKeys.skillFile(key, skillId, fileId) });
    },
  });
}
