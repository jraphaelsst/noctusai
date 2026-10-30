/**
 * "Identidade visual" data hooks (core `/api/brand/*`, CONTRACT org-brand-identity §3/§6).
 *
 * Every key carries the EFFECTIVE org id (org picker, no reload): no entry of org A survives
 * under org B. These reads are authorization-scoped per org, so they carry NO `placeholderData`
 * — the page shows a skeleton for a fresh org (`isPending && !data`), never the previous org's data.
 *
 * Writes follow noc-cache-writes: PATCH/activate draw what they know (optimistic) and commit the
 * server's answer; ingest is a job-starting write → it seeds the job's cache entry as `queued`
 * and hands off to `jobPolling` (`handOffToPolling`), so the progress UI never waits for a reload.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { handOffToPolling, jobPolling } from '@noctusai/lib';
import { brandCurrentQueryKey, useEffectiveSSOContext } from '@noctusai/lib/design-system';
import { listOps, useCacheWriteMutation } from '@noctusai/lib/cache-writes';

import { api } from '../lib/api';
import {
  jobEmAndamento,
  type AssetSlot, type BrandCurrent, type BrandIdentity, type BrandIdentitySummary, type BrandJob,
  type BrandTokens, type BrandVoice,
} from '../lib/brand-contract';

export const JOB_POLL_MS = 2_000;

/** The /api/brand detail + write routes answer `{ data }` (core router envelope). */
const unwrap = <T,>(r: { data: T }): T => r.data;

export const brandKeys = {
  // Seed-owned key: BrandProvider reads the same entry, so an activation here reskins live.
  current: (orgId: string) => brandCurrentQueryKey(orgId),
  identities: (orgId: string) => ['core', 'brand', orgId, 'identities'] as const,
  identity: (orgId: string, id: string) => ['core', 'brand', orgId, 'identity', id] as const,
  job: (orgId: string, jobId: string) => ['core', 'brand', orgId, 'job', jobId] as const,
};

/** The effective org of this visit; `''` until it resolves (queries stay disabled). */
export function useBrandOrgId(): string {
  return useEffectiveSSOContext().orgId ?? '';
}

export function useBrandCurrent() {
  const orgId = useBrandOrgId();
  return useQuery<BrandCurrent>({
    queryKey: brandKeys.current(orgId),
    queryFn: () => api.get<BrandCurrent>('/api/brand/current'),
    enabled: !!orgId,
    retry: false,
  });
}

export function useBrandIdentities() {
  const orgId = useBrandOrgId();
  return useQuery<BrandIdentitySummary[]>({
    queryKey: brandKeys.identities(orgId),
    queryFn: async () => {
      const r = await api.get<BrandIdentitySummary[] | { data: BrandIdentitySummary[] }>('/api/brand/identities');
      return Array.isArray(r) ? r : r.data ?? [];
    },
    enabled: !!orgId,
    retry: false,
  });
}

export function useBrandIdentity(id: string | null) {
  const orgId = useBrandOrgId();
  return useQuery<BrandIdentity>({
    queryKey: brandKeys.identity(orgId, id ?? ''),
    queryFn: () => api.get<{ data: BrandIdentity }>(`/api/brand/identities/${id}`).then(unwrap),
    enabled: !!orgId && !!id,
    retry: false,
  });
}

/** Polls while queued/running — also in a background tab, and a fresh hand-off keeps it polling. */
export function useBrandJob(jobId: string | null) {
  const orgId = useBrandOrgId();
  return useQuery<BrandJob>({
    queryKey: brandKeys.job(orgId, jobId ?? ''),
    queryFn: () => api.get<BrandJob>(`/api/brand/jobs/${jobId}`),
    enabled: !!orgId && !!jobId,
    retry: false,
    ...jobPolling((d: BrandJob | undefined) => !!d && jobEmAndamento(d.status), JOB_POLL_MS),
  });
}

export interface IngestInput { files: File[]; descriptions: Record<string, string> }

export function useIngestBrand() {
  const orgId = useBrandOrgId();
  const qc = useQueryClient();
  return useCacheWriteMutation<{ job_id: string }, IngestInput>({
    mutationFn: ({ files, descriptions }) => {
      const form = new FormData();
      for (const f of files) form.append('files', f);
      const filled = Object.fromEntries(Object.entries(descriptions).filter(([, v]) => v.trim()));
      form.append('descriptions', JSON.stringify(filled));
      return api.upload<{ job_id: string }>('/api/brand/identities/ingest', form);
    },
    // The 202 answer is the job id: write the queued job into ITS cache entry now.
    targets: [],
    onSuccess: (res) => {
      const key = brandKeys.job(orgId, res.job_id);
      qc.setQueryData<BrandJob>(key, { status: 'queued' });
      return handOffToPolling(qc, key);
    },
  });
}

export interface PatchInput {
  id: string;
  tokens?: BrandTokens;
  brand_book?: string;
  voice?: BrandVoice;
}

export function usePatchBrandIdentity() {
  const orgId = useBrandOrgId();
  return useCacheWriteMutation<Partial<BrandIdentity>, PatchInput>({
    mutationFn: ({ id, ...body }) => api.patch<{ data: Partial<BrandIdentity> }>(`/api/brand/identities/${id}`, body).then(unwrap),
    targets: (vars) => [
      {
        queryKey: brandKeys.identity(orgId, vars.id),
        optimistic: (old: BrandIdentity | undefined) =>
          old ? { ...old, ...(vars.tokens && { tokens: vars.tokens }), ...(vars.brand_book !== undefined && { brand_book: vars.brand_book }), ...(vars.voice && { voice: vars.voice }) } : old,
        // The answer is the re-validated row (validation warnings / filled keys); merge what it carries.
        commit: (old: BrandIdentity | undefined, saved) => (old ? { ...old, ...saved } : old),
      },
    ],
  });
}

export function useActivateBrandIdentity() {
  const orgId = useBrandOrgId();
  const qc = useQueryClient();
  return useCacheWriteMutation<Partial<BrandIdentity> | undefined, string>({
    mutationFn: (id) => api.post<{ data: Partial<BrandIdentity> }>(`/api/brand/identities/${id}/activate`).then(unwrap),
    targets: (id) => [
      {
        // The target becomes active, the previous active one is archived (rollback = activating an archived).
        queryKey: brandKeys.identities(orgId),
        optimistic: (old: BrandIdentitySummary[] | undefined) =>
          old?.map((r) =>
            r.id === id ? { ...r, status: 'active' as const, activated_at: new Date().toISOString() }
              : r.status === 'active' ? { ...r, status: 'archived' as const } : r),
      },
      {
        queryKey: brandKeys.identity(orgId, id),
        optimistic: (old: BrandIdentity | undefined) => (old ? { ...old, status: 'active' as const } : old),
      },
      {
        // The theme the org wears is the activated one's tokens; signed asset URLs converge on settle.
        queryKey: brandKeys.current(orgId),
        commit: (old: BrandCurrent | undefined) => {
          const d = qc.getQueryData<BrandIdentity>(brandKeys.identity(orgId, id));
          return d
            ? { source: 'org' as const, identity_id: d.id, version: d.version, tokens: d.tokens, assets: old?.assets ?? {}, updated_at: new Date().toISOString() }
            : old;
        },
      },
    ],
  });
}

export function useUploadBrandAsset() {
  const orgId = useBrandOrgId();
  return useCacheWriteMutation<Partial<BrandIdentity> | undefined, { id: string; slot: AssetSlot; file: File }>({
    mutationFn: ({ id, slot, file }) => {
      const form = new FormData();
      form.append('slot', slot);
      form.append('file', file);
      return api.upload<{ data: Partial<BrandIdentity> }>(`/api/brand/identities/${id}/assets`, form).then(unwrap);
    },
    targets: (vars) => [
      {
        queryKey: brandKeys.identity(orgId, vars.id),
        commit: (old: BrandIdentity | undefined, saved) =>
          old && saved?.assets ? { ...old, assets: saved.assets } : old,
      },
    ],
    // Without an answer body the stored path is the server's: settle refetches the draft.
    invalidate: (vars) => [brandKeys.identity(orgId, vars.id)],
  });
}

/** A finished job: the new draft joins the version list now (its row is read from the job's identity). */
export function addDraftToList(old: BrandIdentitySummary[] | undefined, row: BrandIdentitySummary) {
  return listOps.replace(old, row.id, row, 'prepend');
}
