/**
 * Mailchimp templates hooks.
 *
 * Wraps `/api/mailchimp/templates` (user-created templates, type=user).
 * `edit_url` is computed server-side and deep-links to Mailchimp's editor.
 *
 * Built on @tanstack/react-query v5. queryFns never return undefined.
 */
import {
  useQuery,
} from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TemplateOut {
  id: number;
  name: string;
  category: string | null;
  type: string;
  drag_and_drop: boolean;
  preview_image: string | null;
  date_created: string;
  date_edited: string;
  edit_url: string | null;
}

export interface TemplatesOut {
  items: TemplateOut[];
  total: number;
}

export interface CreateTemplateBody {
  name: string;
  html: string;
}

export interface UpdateTemplateBody {
  name?: string;
  html?: string;
}

export interface ListTemplatesParams {
  count?: number;
  offset?: number;
}

const BASE = "/api/mailchimp/templates";
const FAMILY_KEY = ["mailchimp"] as const;
const TEMPLATES_KEY = [...FAMILY_KEY, "templates"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useMailchimpTemplates(params?: ListTemplatesParams) {
  const searchParams = new URLSearchParams();
  if (params?.count != null) searchParams.set("count", String(params.count));
  if (params?.offset != null) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();

  return useQuery<TemplatesOut>({
    queryKey: [...TEMPLATES_KEY, params],
    queryFn: () => api.get<TemplatesOut>(qs ? `${BASE}?${qs}` : BASE),
  });
}

export function useMailchimpTemplate(templateId: number | null) {
  return useQuery<TemplateOut>({
    queryKey: [...TEMPLATES_KEY, templateId],
    queryFn: () => api.get<TemplateOut>(`${BASE}/${templateId}`),
    enabled: templateId != null,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

/** Mailchimp ids are numbers, so the list edits go through `listOps.within` (untyped rows). */
export function useMailchimpTemplateMutations() {
  const create = useCacheWriteMutation<TemplateOut, CreateTemplateBody>({
    mutationFn: (body) => api.post<TemplateOut>(BASE, body),
    // The default (param-less) list; paged / offset lists settle.
    targets: [
      {
        queryKey: [...TEMPLATES_KEY, undefined],
        commit: (old: TemplatesOut | undefined, saved) => {
          if (!old?.items || old.items.some((t) => t.id === saved.id)) return old;
          const next = listOps.within(old, "items", (l) => [...l, saved]);
          return next ? { ...next, total: next.total + 1 } : old;
        },
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  const update = useCacheWriteMutation<TemplateOut, { id: number; body: UpdateTemplateBody }>({
    mutationFn: ({ id, body }) => api.patch<TemplateOut>(`${BASE}/${id}`, body),
    // One prefix reaches every cached list page AND this template's detail.
    targets: ({ id }) => [
      {
        queryKey: TEMPLATES_KEY,
        match: "prefix",
        commit: (old: TemplatesOut | TemplateOut | undefined, saved) => {
          if (old && "items" in old) {
            return listOps.within(old, "items", (l) => l.map((t) => (t.id === id ? { ...t, ...saved } : t)));
          }
          return old && (old as TemplateOut).id === id ? { ...(old as TemplateOut), ...saved } : old;
        },
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  const remove = useCacheWriteMutation<unknown, number>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    targets: (id) => [
      {
        queryKey: TEMPLATES_KEY,
        match: "prefix",
        optimistic: (old: TemplatesOut | TemplateOut | undefined) => {
          if (!old || !("items" in old) || !old.items.some((t) => t.id === id)) return old;
          const next = listOps.within(old, "items", (l) => l.filter((t) => t.id !== id));
          return next ? { ...next, total: Math.max(0, next.total - 1) } : old;
        },
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  return { create, update, remove };
}
