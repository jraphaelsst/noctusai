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
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
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
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";
import { useStudioAgent } from "./useStudioAgents";

const base = (key: string) => `/api/studio/agents/${seg(key)}`;

function afterDraftWrite(qc: QueryClient, key: string, version?: VersionDetail) {
  if (version) qc.setQueryData(studioKeys.version(key, version.id), version);
  void qc.invalidateQueries({ queryKey: studioKeys.detail(key) });
  void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
  void qc.invalidateQueries({ queryKey: ["studio", key, "diff"] });
}

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
  const qc = useQueryClient();
  return useMutation<VersionDetail, unknown, DraftCreateInput | void>({
    mutationFn: (payload) => api.post<VersionDetail>(`${base(key)}/draft`, payload ?? {}),
    onSuccess: (draft) => {
      afterDraftWrite(qc, key, draft);
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
    },
  });
}

export function useDiscardDraft(key: string) {
  const qc = useQueryClient();
  return useMutation<null, unknown, { draftId: string }>({
    mutationFn: () => api.delete<null>(`${base(key)}/draft`),
    onSuccess: (_r, { draftId }) => {
      qc.removeQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
    },
  });
}

export function useUpdateDraft(key: string) {
  const qc = useQueryClient();
  return useMutation<VersionDetail, unknown, DraftPatchInput>({
    mutationFn: (payload) => api.patch<VersionDetail>(`${base(key)}/draft`, payload),
    onSuccess: (draft) => afterDraftWrite(qc, key, draft),
  });
}

export function useSaveSections(key: string) {
  const qc = useQueryClient();
  return useMutation<VersionDetail, unknown, SectionsReplaceInput>({
    mutationFn: (payload) => api.put<VersionDetail>(`${base(key)}/draft/sections`, payload),
    onSuccess: (draft) => afterDraftWrite(qc, key, draft),
  });
}

export function usePublishDraft(key: string) {
  const qc = useQueryClient();
  return useMutation<VersionDetail, unknown, PublishInput>({
    mutationFn: (payload) => api.post<VersionDetail>(`${base(key)}/draft/publish`, payload),
    onSuccess: (published) => {
      void qc.invalidateQueries({ queryKey: studioKeys.versions(key) });
      afterDraftWrite(qc, key, published);
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
    },
  });
}

// ── Draft skills + files ──────────────────────────────────────────────────────
// Skill routes return the `Skill` (not the whole version), so the draft's
// `VersionDetail` is invalidated rather than patched by hand.

export function useCreateSkill(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<Skill, unknown, SkillCreateInput>({
    mutationFn: (payload) => api.post<Skill>(`${base(key)}/draft/skills`, payload),
    onSuccess: () => {
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
    },
  });
}

export function useUpdateSkill(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<Skill, unknown, { skillId: string; patch: SkillPatchInput }>({
    mutationFn: ({ skillId, patch }) => api.patch<Skill>(`${base(key)}/draft/skills/${seg(skillId)}`, patch),
    onSuccess: () => {
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
    },
  });
}

export function useDeleteSkill(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<null, unknown, { skillId: string }>({
    mutationFn: ({ skillId }) => api.delete<null>(`${base(key)}/draft/skills/${seg(skillId)}`),
    onSuccess: () => {
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
    },
  });
}

export function useUpsertSkillFile(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<SkillFileSummary, unknown, { skillId: string; file: SkillFileUpsertInput }>({
    mutationFn: ({ skillId, file }) =>
      api.put<SkillFileSummary>(`${base(key)}/draft/skills/${seg(skillId)}/files`, file),
    onSuccess: (saved, { skillId }) => {
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      void qc.invalidateQueries({ queryKey: studioKeys.skillFile(key, skillId, saved.id) });
      afterDraftWrite(qc, key);
    },
  });
}

/**
 * ONE call to `skillFilesBatchPath` (max `SKILL_FILES_BATCH_MAX` files —
 * `@/api/studio/batchPaths.ts`). Like `useBatchCreateDocuments`
 * (`useKnowledge.ts`), chunking belongs to the caller (`sendInChunks`,
 * `@/lib/batchUpload.ts`), not this hook.
 */
export function useBatchUpsertSkillFiles(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<SkillFilesBatchResponse, unknown, { skillId: string; arquivos: SkillFileBatchItem[] }>({
    mutationFn: ({ skillId, arquivos }) =>
      api.put<SkillFilesBatchResponse>(skillFilesBatchPath(key, skillId), { arquivos }),
    onSuccess: () => {
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
    },
  });
}

export function useDeleteSkillFile(key: string, draftId: string | null) {
  const qc = useQueryClient();
  return useMutation<null, unknown, { skillId: string; fileId: string }>({
    mutationFn: ({ skillId, fileId }) =>
      api.delete<null>(`${base(key)}/draft/skills/${seg(skillId)}/files/${seg(fileId)}`),
    onSuccess: (_r, { skillId, fileId }) => {
      qc.removeQueries({ queryKey: studioKeys.skillFile(key, skillId, fileId) });
      if (draftId) void qc.invalidateQueries({ queryKey: studioKeys.version(key, draftId) });
      afterDraftWrite(qc, key);
    },
  });
}
