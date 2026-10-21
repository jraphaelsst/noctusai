/**
 * Branding hooks — the richer brand-kit model (tokens, brand book,
 * components, assets), grouped by marca. TanStack Query wrappers.
 *
 *   GET    /api/media-creation/branding              → BrandingOverview
 *   GET    /api/media-creation/branding/{id}         → BrandingDetail
 *   POST   /api/media-creation/branding              (create, optionally from the template)
 *   POST   /api/media-creation/branding/import       (design-system folder)
 *   PATCH  /api/media-creation/branding/{id}
 *   DELETE /api/media-creation/branding/{id}
 *   PUT    /api/media-creation/branding/{id}/components
 *   DELETE /api/media-creation/branding/components/{cid}
 *   POST   /api/media-creation/branding/{id}/assets  (base64 JSON)
 *   POST   /api/media-creation/brand-kits/{id}/references  (link-only reference)
 *   DELETE /api/media-creation/references/{rid}
 *
 * Responses are wrapped in `{ok, data}` by the backend (`success_response`);
 * unwrapped here so components stay envelope-free. Loading follows the two
 * signal rule: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import type { BrandingTokens } from "@/lib/branding";
import type { ImportFilePayload } from "@/lib/branding";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface BrandingSummary {
  id: string;
  name: string;
  slug: string | null;
  marca_id: string | null;
  is_template: boolean;
  default_lang: string;
  created_at: string;
  updated_at: string;
}

export interface BrandingMarcaGroup {
  id: string;
  name: string;
  slug: string;
  kind: string | null;
  brandings: BrandingSummary[];
}

export interface BrandingOverview {
  template: BrandingSummary | null;
  marcas: BrandingMarcaGroup[];
  unassigned: BrandingSummary[];
}

export interface BrandingSection {
  title: string;
  markdown: string;
}

export interface BrandingComponent {
  id: string;
  brand_kit_id: string;
  name: string;
  guideline_md: string;
  preview_html: string;
  position: number;
}

export type AssetKind = "logo" | "model" | "font";
export type LinkReferenceKind = "model" | "prompt" | "palette" | "typography";

export interface BrandingAsset {
  id: string;
  brand_kit_id: string;
  kind: AssetKind | LinkReferenceKind;
  label: string;
  asset_url: string | null;
  notes: string | null;
  storage_path: string | null;
  content_type: string | null;
  size_bytes: number | null;
  /** Short-TTL URL minted on read; null for link-only references. */
  signed_url: string | null;
  signed_url_error: string | null;
}

export interface BrandingDetail extends BrandingSummary {
  persona: string;
  design_system: string;
  tokens: BrandingTokens | null;
  brand_book: string;
  sections: BrandingSection[];
  marca: { id: string; name: string; slug: string; kind: string | null } | null;
  components: BrandingComponent[];
  assets: BrandingAsset[];
}

export interface ImportResult {
  id: string;
  action: "created" | "updated";
  is_template: boolean;
  name: string;
  components: number;
  assets: number;
  sections: number;
  ignored: string[];
  warnings: string[];
}

interface Envelope<T> {
  ok: boolean;
  data: T;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

export const BRANDING_KEY = ["sw", "branding"] as const;
export const brandingDetailKey = (id: string) => ["sw", "branding", "detail", id] as const;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useBrandingOverview() {
  const query = useQuery({
    queryKey: BRANDING_KEY,
    queryFn: async () => (await api.get<Envelope<BrandingOverview>>("/api/media-creation/branding")).data,
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useBrandingDetail(id: string | null) {
  const query = useQuery({
    queryKey: brandingDetailKey(id ?? ""),
    queryFn: async () =>
      (await api.get<Envelope<BrandingDetail>>(`/api/media-creation/branding/${id}`)).data,
    enabled: !!id,
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** The overview regroups brands by marca/template, so every write refreshes it in the background. */
const OVERVIEW = [BRANDING_KEY];

export interface CreateBrandingInput {
  name: string;
  marca_id: string | null;
  persona?: string;
  from_template?: boolean;
}

export function useCreateBranding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateBrandingInput) =>
      (await api.post<Envelope<BrandingDetail>>("/api/media-creation/branding", input)).data,
    onSuccess: (d) => {
      // The new brand's detail is known now; the overview regroups server-side, so it refreshes.
      qc.setQueryData(brandingDetailKey(d.id), d);
      void qc.invalidateQueries({ queryKey: BRANDING_KEY });
    },
  });
}

export interface UpdateBrandingInput {
  name?: string;
  persona?: string;
  design_system?: string;
  default_lang?: string;
  marca_id?: string | null;
  brand_book?: string;
  sections?: BrandingSection[];
  tokens?: BrandingTokens;
}

export function useUpdateBranding(id: string) {
  return useCacheWriteMutation<BrandingDetail, UpdateBrandingInput>({
    mutationFn: async (patch) =>
      (await api.patch<Envelope<BrandingDetail>>(`/api/media-creation/branding/${id}`, patch)).data,
    targets: (patch) => [
      {
        queryKey: brandingDetailKey(id),
        optimistic: (old: BrandingDetail | undefined) => listOps.merge(old, patch as Partial<BrandingDetail>),
        commit: (_old: BrandingDetail | undefined, saved) => saved,
      },
    ],
    invalidate: OVERVIEW,
  });
}

export function useDeleteBranding() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/media-creation/branding/${id}`),
    targets: [
      {
        queryKey: BRANDING_KEY,
        optimistic: (old: BrandingOverview | undefined, id) =>
          old && {
            template: old.template?.id === id ? null : old.template,
            marcas: old.marcas.map((g) => ({ ...g, brandings: listOps.remove(g.brandings, id) ?? g.brandings })),
            unassigned: listOps.remove(old.unassigned, id) ?? old.unassigned,
          },
      },
    ],
    invalidate: OVERVIEW,
  });
}

export interface ImportInput {
  marca_id: string | null;
  is_template: boolean;
  name?: string;
  files: ImportFilePayload[];
}

export function useImportDesignSystem() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — an import creates or updates a brand with its components/assets server-side; the result is a summary, not the detail
    mutationFn: async (input: ImportInput) =>
      (await api.post<Envelope<ImportResult>>("/api/media-creation/branding/import", input)).data,
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: BRANDING_KEY });
      void qc.invalidateQueries({ queryKey: brandingDetailKey(r.id) });
    },
  });
}

export function useUpsertComponent(id: string) {
  return useCacheWriteMutation<BrandingComponent, { name: string; guideline_md: string; preview_html: string }>({
    mutationFn: async (input) =>
      (await api.put<Envelope<BrandingComponent>>(`/api/media-creation/branding/${id}/components`, input)).data,
    targets: [
      {
        queryKey: brandingDetailKey(id),
        commit: (old: BrandingDetail | undefined, saved) =>
          old && { ...old, components: listOps.replace(old.components, saved.id, saved) ?? old.components },
      },
    ],
  });
}

export function useDeleteComponent(id: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (componentId) => api.delete(`/api/media-creation/branding/components/${componentId}`),
    targets: [
      {
        queryKey: brandingDetailKey(id),
        optimistic: (old: BrandingDetail | undefined, componentId) =>
          old && { ...old, components: listOps.remove(old.components, componentId) ?? old.components },
      },
    ],
  });
}

export function useUploadAsset(id: string) {
  return useCacheWriteMutation<BrandingAsset, { kind: AssetKind; label: string; content_base64: string }>({
    mutationFn: async (input) =>
      (await api.post<Envelope<BrandingAsset>>(`/api/media-creation/branding/${id}/assets`, input)).data,
    targets: [
      {
        queryKey: brandingDetailKey(id),
        commit: (old: BrandingDetail | undefined, saved) =>
          old && { ...old, assets: listOps.replace(old.assets, saved.id, saved) ?? old.assets },
      },
    ],
  });
}

export function useAddLinkReference(id: string) {
  return useCacheWriteMutation<BrandingAsset, { kind: LinkReferenceKind; label: string; asset_url?: string; notes?: string }>({
    mutationFn: async (input) =>
      (await api.post<Envelope<BrandingAsset>>(`/api/media-creation/brand-kits/${id}/references`, input)).data,
    targets: [
      {
        queryKey: brandingDetailKey(id),
        commit: (old: BrandingDetail | undefined, saved) =>
          old && { ...old, assets: listOps.replace(old.assets, saved.id, saved) ?? old.assets },
      },
    ],
  });
}

export function useDeleteReference(id: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (referenceId) => api.delete(`/api/media-creation/references/${referenceId}`),
    targets: [
      {
        queryKey: brandingDetailKey(id),
        optimistic: (old: BrandingDetail | undefined, referenceId) =>
          old && { ...old, assets: listOps.remove(old.assets, referenceId) ?? old.assets },
      },
    ],
  });
}
