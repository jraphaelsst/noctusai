/**
 * Mailchimp templates hooks.
 *
 * Wraps `/api/mailchimp/templates` (user-created templates, type=user).
 * `edit_url` is computed server-side and deep-links to Mailchimp's editor.
 *
 * Built on @tanstack/react-query v5. queryFns never return undefined.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
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

export function useMailchimpTemplateMutations() {
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<TemplateOut, unknown, CreateTemplateBody>({
    mutationFn: (body) => api.post<TemplateOut>(BASE, body),
    onSuccess: invalidateFamily,
  });

  const update = useMutation<
    TemplateOut,
    unknown,
    { id: number; body: UpdateTemplateBody }
  >({
    mutationFn: ({ id, body }) => api.patch<TemplateOut>(`${BASE}/${id}`, body),
    onSuccess: invalidateFamily,
  });

  const remove = useMutation<unknown, unknown, number>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    onSuccess: invalidateFamily,
  });

  return { create, update, remove };
}
