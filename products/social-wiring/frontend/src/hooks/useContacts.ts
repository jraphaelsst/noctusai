/**
 * In-home platform contacts hooks.
 *
 * Wraps `/api/email-marketing/contacts` — the social_wiring.contacts table.
 * These are platform-owned contacts (manually created, WhatsApp-auto-saved,
 * imported) — NOT Mailchimp audience members (see useMailchimpContacts).
 *
 * Response envelope: paginated_response → { data: Contact[], pagination: {...} }
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export type ContactSource = "manual" | "import" | "whatsapp" | string;
export type ContactStatus = "active" | "archived" | string;

export interface Contact {
  id: string;
  org_id: string;
  nome: string;
  email: string | null;
  telefone: string | null;
  empresa: string | null;
  tags: string[];
  source: ContactSource;
  status: ContactStatus;
  whatsapp_phone: string | null;
  whatsapp_lids: string[];
  whatsapp_jid: string | null;
  created_at: string;
  updated_at: string | null;
  custom_fields: Record<string, unknown>;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ContactsPage {
  data: Contact[];
  pagination: PaginationMeta;
}

export interface ContactCreateInput {
  email: string;
  nome?: string;
  telefone?: string;
  empresa?: string;
  tags?: string[];
  source?: ContactSource;
  custom_fields?: Record<string, unknown>;
}

export interface ContactUpdateInput {
  email?: string;
  nome?: string;
  telefone?: string;
  empresa?: string;
  tags?: string[];
  custom_fields?: Record<string, unknown>;
}

export interface ListContactsParams {
  page?: number;
  pageSize?: number;
  status?: string;
  search?: string;
}

const BASE = "/api/email-marketing/contacts";
const FAMILY_KEY = ["contacts", "in-home"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useContacts(params?: ListContactsParams) {
  const searchParams = new URLSearchParams();
  if (params?.page != null) searchParams.set("page", String(params.page));
  if (params?.pageSize != null) searchParams.set("page_size", String(params.pageSize));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.search) searchParams.set("search", params.search);
  const qs = searchParams.toString();

  return useQuery<ContactsPage>({
    queryKey: [...FAMILY_KEY, params],
    queryFn: () => api.get<ContactsPage>(qs ? `${BASE}?${qs}` : BASE),
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

/**
 * Unwrap the seed success_response envelope: { data: T } → T.
 * The contacts router always returns `success_response(result)` which
 * wraps the object. `paginated_response` (list) is handled by typing
 * ContactsPage to match its shape directly.
 */
type SuccessEnvelope<T> = { data: T };

export function useContactMutations() {
  const qc = useQueryClient();
  const invalidateFamily = () =>
    qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<Contact, unknown, ContactCreateInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<Contact>>(BASE, body);
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const update = useMutation<
    Contact,
    unknown,
    { id: string; body: ContactUpdateInput }
  >({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<Contact>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const archive = useMutation<unknown, unknown, string>({
    mutationFn: (id) =>
      api.delete(`${BASE}/${encodeURIComponent(id)}`),
    onSuccess: invalidateFamily,
  });

  return { create, update, archive };
}
