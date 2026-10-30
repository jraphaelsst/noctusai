/**
 * Admin > Templates data hooks (core `/api/admin/templates`). Every write follows noc-cache-writes: it puts the
 * server's answer into the detail entry and into the (filtered) lists it belongs to; derived views (counts in the
 * nav tree, the version history) are refreshed in the background.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '@noctusai/lib/cache-writes';

import { api } from '../lib/api';
import {
  PLATFORM_SCOPE, type Template, type TemplateFilters, type TemplateFormat, type TemplateKind, type TemplateSource,
  type TemplateSummary, type TemplatesMeta,
} from '../lib/templates-contract';

const unwrap = <T,>(r: { data: T }): T => r.data;
const ROOT = ['core', 'admin-templates'] as const;

export const templateKeys = {
  meta: [...ROOT, 'meta'] as const,
  lists: [...ROOT, 'list'] as const,
  list: (f: TemplateFilters) => [...ROOT, 'list', f] as const,
  detail: (id: string) => [...ROOT, 'detail', id] as const,
  histories: [...ROOT, 'history'] as const,
  history: (id: string) => [...ROOT, 'history', id] as const,
  sources: (f: TemplateFilters) => [...ROOT, 'sources', f] as const,
};

const qs = (f: TemplateFilters) => {
  const p = new URLSearchParams();
  if (f.product) p.set('product', f.product);
  if (f.kind) p.set('kind', f.kind);
  if (f.q) p.set('q', f.q);
  const s = p.toString();
  return s ? `?${s}` : '';
};

export function useTemplatesMeta() {
  return useQuery<TemplatesMeta>({
    queryKey: templateKeys.meta,
    queryFn: () => api.get<{ data: TemplatesMeta }>('/api/admin/templates/meta').then(unwrap),
    retry: false,
  });
}

export function useTemplates(filters: TemplateFilters) {
  return useQuery<TemplateSummary[]>({
    queryKey: templateKeys.list(filters),
    queryFn: () => api.get<{ data: TemplateSummary[] }>(`/api/admin/templates${qs(filters)}`).then(unwrap),
    retry: false,
  });
}

export function useTemplate(id: string | null) {
  return useQuery<Template>({
    queryKey: templateKeys.detail(id ?? ''),
    queryFn: () => api.get<{ data: Template }>(`/api/admin/templates/${id}`).then(unwrap),
    enabled: !!id,
    retry: false,
  });
}

export function useTemplateHistory(id: string | null) {
  return useQuery<TemplateSummary[]>({
    queryKey: templateKeys.history(id ?? ''),
    queryFn: () => api.get<{ data: TemplateSummary[] }>(`/api/admin/templates/${id}/history`).then(unwrap),
    enabled: !!id,
    retry: false,
  });
}

export function useTemplateSources(filters: TemplateFilters) {
  return useQuery<TemplateSource[]>({
    queryKey: templateKeys.sources(filters),
    queryFn: () => api.get<{ data: TemplateSource[] }>(`/api/admin/templates/sources${qs(filters)}`).then(unwrap),
    retry: false,
  });
}

/** The scope id the lists group by — product + kind + key (a template across its versions). */
const scopeId = (r: { product: string | null; kind: string; key: string }) => `${r.product ?? ''}|${r.kind}|${r.key}`;

/** Does the (filtered) list at `queryKey` show rows of this template's scope? */
function listCovers(queryKey: readonly unknown[], row: { product: string | null; kind: string }): boolean {
  const f = (queryKey[3] ?? {}) as TemplateFilters;
  if (f.kind && f.kind !== row.kind) return false;
  if (f.product === PLATFORM_SCOPE) return row.product === null;
  if (f.product && f.product !== row.product) return false;
  return !f.q; // a text-filtered list converges on settle
}

const headOf = (row: Template, extra: Partial<TemplateSummary> = {}): TemplateSummary => {
  const { body: _body, ...summary } = row;
  return { ...summary, versions: 1, latest_version: row.version, has_draft: row.status === 'draft', ...extra };
};

export interface CreateInput { product: string | null; kind: TemplateKind; key: string; title: string; description: string; format: TemplateFormat; body: string }

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useCacheWriteMutation<Template, CreateInput>({
    mutationFn: (body) => api.post<{ data: Template }>('/api/admin/templates', body).then(unwrap),
    targets: [
      // A brand-new key joins every list that shows its scope; a new version of a known key bumps its head row.
      { queryKey: templateKeys.lists, match: 'prefix',
        commit: (old: TemplateSummary[] | undefined, saved: Template, _v, _c, key) => {
          if (!Array.isArray(old) || (key && !listCovers(key, saved))) return old;
          return old.some((r) => scopeId(r) === scopeId(saved))
            ? listOps.update(old, scopeId(saved), (r) => ({ ...r, versions: (r.versions ?? 1) + 1, latest_version: saved.version, has_draft: true }), scopeId)
            : listOps.prepend(old, headOf(saved));
        } },
    ],
    // The editor opens the new draft by id: seed its detail so it does not wait for a read.
    onSuccess: (saved) => { qc.setQueryData(templateKeys.detail(saved.id), saved); },
    invalidate: [templateKeys.meta, templateKeys.histories],
  });
}

export interface UpdateInput { id: string; title?: string; description?: string; format?: TemplateFormat; body?: string }

export function useUpdateTemplate() {
  return useCacheWriteMutation<Template, UpdateInput>({
    mutationFn: ({ id, ...body }) => api.patch<{ data: Template }>(`/api/admin/templates/${id}`, body).then(unwrap),
    targets: (vars) => [
      // A draft is edited in place (same id); an active/archived version answers with a NEW draft id.
      { queryKey: templateKeys.detail(vars.id), commit: (old: Template | undefined, saved: Template) => (saved.id === vars.id ? saved : old) },
      { queryKey: templateKeys.lists, match: 'prefix',
        commit: (old: TemplateSummary[] | undefined, saved: Template) =>
          listOps.update(old, scopeId(saved), (r) => (saved.id === r.id
            ? { ...r, ...headOf(saved, { versions: r.versions, latest_version: r.latest_version, has_draft: r.has_draft }) }
            : { ...r, versions: (r.versions ?? 1) + (r.latest_version === saved.version ? 0 : 1), latest_version: saved.version, has_draft: true }), scopeId) },
    ],
    invalidate: [templateKeys.histories],
  });
}

export function useActivateTemplate() {
  return useCacheWriteMutation<Template, string>({
    mutationFn: (id) => api.post<{ data: Template }>(`/api/admin/templates/${id}/activate`).then(unwrap),
    targets: (id) => [
      { queryKey: templateKeys.detail(id), commit: (old: Template | undefined, saved: Template) => (old ? { ...old, ...saved } : saved) },
      { queryKey: templateKeys.lists, match: 'prefix',
        commit: (old: TemplateSummary[] | undefined, saved: Template) =>
          listOps.update(old, scopeId(saved), (r) => ({ ...r, ...headOf(saved, { versions: r.versions, latest_version: r.latest_version, has_draft: r.has_draft && r.latest_version !== saved.version }) }), scopeId) },
    ],
    // The previous active version is archived server-side: its detail + the history are derived views.
    invalidate: [templateKeys.histories, [...ROOT, 'detail']],
  });
}

export function useArchiveTemplate() {
  return useCacheWriteMutation<Template, string>({
    mutationFn: (id) => api.post<{ data: Template }>(`/api/admin/templates/${id}/archive`).then(unwrap),
    targets: (id) => [
      { queryKey: templateKeys.detail(id), commit: (old: Template | undefined, saved: Template) => (old ? { ...old, ...saved } : saved) },
      { queryKey: templateKeys.lists, match: 'prefix',
        commit: (old: TemplateSummary[] | undefined, saved: Template) =>
          listOps.update(old, scopeId(saved), (r) => (r.id === saved.id ? { ...r, status: saved.status } : r), scopeId) },
    ],
    invalidate: [templateKeys.lists, templateKeys.histories, templateKeys.meta],
  });
}
