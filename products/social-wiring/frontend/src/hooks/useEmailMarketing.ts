/**
 * Email Marketing hooks — `/api/email-marketing/*`, the product's OWN mailing
 * engine (Resend-backed, tables in `social_wiring`).
 *
 * NOT to be confused with `useMailchimp*`, which proxies a connected Mailchimp
 * account. Both surfaces ship; they are different products in the same app and
 * the nav names them apart ("Email Marketing" vs "Mailchimp").
 *
 * Wire shape: every route returns the seed envelope `{ data: … }` via
 * `success_response()`. Lists come back as a bare array inside `data`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

const BASE = "/api/email-marketing";
const FAMILY = ["sw", "email-marketing"] as const;

interface Envelope<T> {
  data: T;
}

/** Unwrap `success_response()`; tolerate a bare payload for robustness. */
function unwrap<T>(res: Envelope<T> | T, fallback: T): T {
  if (res && typeof res === "object" && "data" in (res as Envelope<T>)) {
    return ((res as Envelope<T>).data ?? fallback) as T;
  }
  return ((res as T) ?? fallback) as T;
}

// ─── Types (mirror migration 001 DDL + the module schemas) ───────────────────

export type CampaignStatus =
  | "rascunho"
  | "agendada"
  | "enviando"
  | "enviada"
  | "pausada"
  | "cancelada";

export type ContactStatus = "active" | "unsubscribed" | "bounced" | "complained";
/** Double opt-in (migration 244). `pending` receives no marketing e-mail. */
export type EmailOptin = "not_required" | "pending" | "confirmed";
export type TemplateCategoria =
  | "marketing"
  | "transactional"
  | "follow_up"
  | "newsletter";
export type AutomationStatus = "rascunho" | "ativa" | "pausada";
export type DomainStatus = "pending" | "verified" | "failed";

export interface EmContact {
  id: string;
  org_id: string;
  email: string;
  nome: string | null;
  telefone: string | null;
  empresa: string | null;
  tags: string[];
  custom_fields: Record<string, unknown>;
  source: string;
  status: ContactStatus;
  unsubscribed_at: string | null;
  email_optin: EmailOptin;
  email_confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Outcome of one double opt-in confirmation e-mail — never faked: when it
 * could not be sent, `reason` says why (no Resend key, no FRONTEND_BASE_URL…). */
export interface EmConfirmationOutcome {
  sent: boolean;
  reason: string | null;
}

export interface EmImportResult {
  imported: number;
  total: number;
  confirmation?: { requested: number; sent: number; failed: number; reason: string | null };
}

export interface EmList {
  id: string;
  org_id: string;
  nome: string;
  descricao: string | null;
  tipo: "static" | "dynamic";
  filtros: Record<string, unknown>;
  contact_count: number;
  created_at: string;
  updated_at: string;
}

export interface EmTemplate {
  id: string;
  org_id: string;
  nome: string;
  assunto: string;
  corpo_html: string;
  corpo_text: string | null;
  variaveis: string[];
  categoria: TemplateCategoria;
  ativo: boolean;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmCampaignStats {
  total_sent?: number;
  total_opened?: number;
  total_clicked?: number;
  total_bounced?: number;
  open_rate?: number;
  click_rate?: number;
}

export interface EmCampaign {
  id: string;
  org_id: string;
  nome: string;
  template_id: string | null;
  list_id: string | null;
  assunto_override: string | null;
  remetente_nome: string | null;
  remetente_email: string | null;
  status: CampaignStatus;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_recipients: number;
  total_sent: number;
  total_failed: number;
  created_at: string;
  updated_at: string;
  stats?: EmCampaignStats;
}

export interface EmAutomation {
  id: string;
  org_id: string;
  nome: string;
  descricao: string | null;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  status: AutomationStatus;
  created_at: string;
  updated_at: string;
}

export interface EmAutomationStep {
  id: string;
  automation_id: string;
  posicao: number;
  tipo: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface EmEnrollment {
  id: string;
  automation_id: string;
  contact_id: string;
  current_step_id: string | null;
  status: string;
  next_action_at: string | null;
  enrolled_at: string;
  completed_at: string | null;
  /** Why the step executor paused it (migration 243); null unless paused. */
  pause_reason?: string | null;
  paused_at?: string | null;
}

/** One DNS record Resend asks the owner to publish (SPF / DKIM / DMARC / MX). */
export interface EmDnsRecord {
  record?: string;
  type: string;
  name: string;
  value: string;
  ttl?: string | number;
  priority?: number;
  status?: string;
}

export interface EmDomain {
  id: string;
  org_id: string;
  domain: string;
  resend_domain_id: string | null;
  status: DomainStatus;
  dns_records: EmDnsRecord[] | null;
  verified_at: string | null;
  created_at: string;
}

export interface EmDashboard {
  total_contacts: number;
  active_contacts: number;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  total_campaigns: number;
}

// ─── Query keys ──────────────────────────────────────────────────────────────

export const emKeys = {
  dashboard: () => [...FAMILY, "analytics", "dashboard"] as const,
  campaignAnalytics: (id: string) =>
    [...FAMILY, "analytics", "campaign", id] as const,
  campaigns: (status?: string) =>
    [...FAMILY, "campaigns", status ?? "all"] as const,
  campaign: (id: string) => [...FAMILY, "campaigns", "detail", id] as const,
  contacts: (status?: string, search?: string) =>
    [...FAMILY, "contacts", status ?? "all", search ?? ""] as const,
  lists: () => [...FAMILY, "lists"] as const,
  listContacts: (id: string) => [...FAMILY, "lists", id, "contacts"] as const,
  templates: (categoria?: string) =>
    [...FAMILY, "templates", categoria ?? "all"] as const,
  automations: (status?: string) =>
    [...FAMILY, "automations", status ?? "all"] as const,
  steps: (id: string) => [...FAMILY, "automations", id, "steps"] as const,
  enrollments: (id: string) =>
    [...FAMILY, "automations", id, "enrollments"] as const,
  domains: () => [...FAMILY, "domains"] as const,
  debrief: (id: string) => [...FAMILY, "debrief", id] as const,
};

function qs(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) usp.set(k, v);
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export function useEmDashboard() {
  return useQuery({
    queryKey: emKeys.dashboard(),
    queryFn: async () =>
      unwrap<EmDashboard | null>(
        await api.get<Envelope<EmDashboard>>(`${BASE}/analytics/dashboard`),
        null,
      ),
  });
}

export function useEmCampaignAnalytics(campaignId: string | null) {
  return useQuery({
    queryKey: emKeys.campaignAnalytics(campaignId ?? "_none"),
    enabled: !!campaignId,
    queryFn: async () =>
      unwrap<Record<string, unknown> | null>(
        await api.get<Envelope<Record<string, unknown>>>(
          `${BASE}/analytics/campaigns/${encodeURIComponent(campaignId!)}`,
        ),
        null,
      ),
  });
}

// ─── Campaigns ───────────────────────────────────────────────────────────────

export function useEmCampaigns(status?: string) {
  return useQuery({
    queryKey: emKeys.campaigns(status),
    queryFn: async () =>
      unwrap<EmCampaign[]>(
        await api.get<Envelope<EmCampaign[]>>(
          `${BASE}/campaigns${qs({ status })}`,
        ),
        [],
      ),
  });
}

export function useEmCampaign(campaignId: string | null) {
  return useQuery({
    queryKey: emKeys.campaign(campaignId ?? "_none"),
    enabled: !!campaignId,
    queryFn: async () =>
      unwrap<EmCampaign | null>(
        await api.get<Envelope<EmCampaign>>(
          `${BASE}/campaigns/${encodeURIComponent(campaignId!)}`,
        ),
        null,
      ),
  });
}

export interface EmCampaignInput {
  nome: string;
  template_id: string;
  list_id: string;
  assunto_override?: string | null;
  remetente_nome?: string | null;
  remetente_email?: string | null;
}

const CAMPAIGNS_KEY = [...FAMILY, "campaigns"] as const;
/** A campaign row's targets: every cached status list is patched, and the detail is merged. */
const campaignTargets = (id: string) => [
  {
    queryKey: CAMPAIGNS_KEY,
    match: "prefix" as const,
    commit: (old: EmCampaign[] | undefined, res: Envelope<EmCampaign>) => {
      const row = unwrap<EmCampaign | null>(res, null);
      return row ? listOps.patch(old, id, row) : old;
    },
  },
  {
    queryKey: emKeys.campaign(id),
    commit: (old: EmCampaign | null | undefined, res: Envelope<EmCampaign>) => {
      const row = unwrap<EmCampaign | null>(res, null);
      return row && old ? listOps.merge(old, row) : old;
    },
  },
];
/** Status-only transitions the route accepts without returning the row: drawn at once, settled by the refetch. */
const campaignStatusTarget = (id: string, status: CampaignStatus, extra: Partial<EmCampaign> = {}) => [
  {
    queryKey: CAMPAIGNS_KEY,
    match: "prefix" as const,
    optimistic: (old: EmCampaign[] | undefined) => listOps.patch(old, id, { status, ...extra }),
  },
  {
    queryKey: emKeys.campaign(id),
    optimistic: (old: EmCampaign | null | undefined) => (old ? listOps.merge(old, { status, ...extra }) : old),
  },
];

export function useEmCampaignMutations() {
  const dash = [emKeys.dashboard()];

  return {
    create: useCacheWriteMutation<Envelope<EmCampaign>, EmCampaignInput>({
      mutationFn: (body) => api.post<Envelope<EmCampaign>>(`${BASE}/campaigns`, body),
      // Newest campaign first in the unfiltered list; status-filtered lists converge on the settle.
      targets: [
        {
          queryKey: emKeys.campaigns(),
          commit: (old: EmCampaign[] | undefined, res) => {
            const row = unwrap<EmCampaign | null>(res, null);
            return row ? listOps.replace(old, row.id, row, "prepend") : old;
          },
        },
      ],
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    update: useCacheWriteMutation<Envelope<EmCampaign>, { id: string; body: Partial<EmCampaignInput> }>({
      mutationFn: ({ id, body }) =>
        api.patch<Envelope<EmCampaign>>(
          `${BASE}/campaigns/${encodeURIComponent(id)}`,
          body,
        ),
      targets: ({ id }) => campaignTargets(id),
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/campaigns/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: CAMPAIGNS_KEY,
          match: "prefix",
          optimistic: (old: EmCampaign[] | undefined) => listOps.remove(old, id),
        },
      ],
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    schedule: useCacheWriteMutation<unknown, { id: string; scheduledAt: string }>({
      mutationFn: ({ id, scheduledAt }) =>
        api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/schedule`, {
          scheduled_at: scheduledAt,
        }),
      targets: ({ id, scheduledAt }) => campaignStatusTarget(id, "agendada", { scheduled_at: scheduledAt }),
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    send: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/send`, {}),
      targets: (id) => campaignStatusTarget(id, "enviando"),
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    pause: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/pause`, {}),
      targets: (id) => campaignStatusTarget(id, "pausada"),
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
    cancel: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/cancel`, {}),
      targets: (id) => campaignStatusTarget(id, "cancelada"),
      invalidate: [CAMPAIGNS_KEY, ...dash],
    }),
  };
}

// ─── Contacts ────────────────────────────────────────────────────────────────

export function useEmContacts(params?: { status?: string; search?: string }) {
  return useQuery({
    queryKey: emKeys.contacts(params?.status, params?.search),
    queryFn: async () =>
      unwrap<EmContact[]>(
        await api.get<Envelope<EmContact[]>>(
          `${BASE}/contacts${qs({ status: params?.status, search: params?.search })}`,
        ),
        [],
      ),
  });
}

export interface EmContactInput {
  email: string;
  nome?: string | null;
  telefone?: string | null;
  empresa?: string | null;
  tags?: string[];
}

const CONTACTS_KEY = [...FAMILY, "contacts"] as const;

export function useEmContactMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: CONTACTS_KEY });
    qc.invalidateQueries({ queryKey: emKeys.dashboard() });
  };
  return {
    create: useCacheWriteMutation<Envelope<EmContact>, EmContactInput>({
      mutationFn: (body) => api.post<Envelope<EmContact>>(`${BASE}/contacts`, body),
      // Unfiltered list only (search / status lists would need the server's filter); the rest settle.
      targets: [
        {
          queryKey: emKeys.contacts(),
          commit: (old: EmContact[] | undefined, res) => {
            const row = unwrap<EmContact | null>(res, null);
            return row ? listOps.replace(old, row.id, row, "prepend") : old;
          },
        },
      ],
      invalidate: [CONTACTS_KEY, emKeys.dashboard()],
    }),
    update: useCacheWriteMutation<Envelope<EmContact>, { id: string; body: Partial<EmContactInput> }>({
      mutationFn: ({ id, body }) =>
        api.patch<Envelope<EmContact>>(
          `${BASE}/contacts/${encodeURIComponent(id)}`,
          body,
        ),
      targets: ({ id }) => [
        {
          queryKey: CONTACTS_KEY,
          match: "prefix",
          commit: (old: EmContact[] | undefined, res) => {
            const row = unwrap<EmContact | null>(res, null);
            return row ? listOps.patch(old, id, row) : old;
          },
        },
      ],
      invalidate: [CONTACTS_KEY, emKeys.dashboard()],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/contacts/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: CONTACTS_KEY,
          match: "prefix",
          optimistic: (old: EmContact[] | undefined) => listOps.remove(old, id),
        },
      ],
      invalidate: [CONTACTS_KEY, emKeys.dashboard()],
    }),
    importMany: useMutation({ // noc-allow: invalidate-only — bulk import: the answer is {imported,total} counts, the new contacts only exist server-side
      mutationFn: ({ contacts, doubleOptIn }: { contacts: EmContactInput[]; doubleOptIn: boolean }) =>
        api.post<Envelope<EmImportResult>>(`${BASE}/contacts/import`, {
          contacts,
          double_opt_in: doubleOptIn,
        }),
      onSuccess: invalidate,
    }),
    resendConfirmation: useMutation({ // noc-allow: invalidate-only — fire-and-forget email send: no cached read changes
      mutationFn: (id: string) =>
        api.post<Envelope<{ confirmation: EmConfirmationOutcome }>>(
          `${BASE}/contacts/${encodeURIComponent(id)}/resend-confirmation`,
        ),
    }),
  };
}

// ─── Lists ───────────────────────────────────────────────────────────────────

export function useEmLists() {
  return useQuery({
    queryKey: emKeys.lists(),
    queryFn: async () =>
      unwrap<EmList[]>(await api.get<Envelope<EmList[]>>(`${BASE}/lists`), []),
  });
}

export function useEmListContacts(listId: string | null) {
  return useQuery({
    queryKey: emKeys.listContacts(listId ?? "_none"),
    enabled: !!listId,
    queryFn: async () =>
      unwrap<EmContact[]>(
        await api.get<Envelope<EmContact[]>>(
          `${BASE}/lists/${encodeURIComponent(listId!)}/contacts`,
        ),
        [],
      ),
  });
}

export interface EmListInput {
  nome: string;
  descricao?: string | null;
  tipo?: "static" | "dynamic";
}

export function useEmListMutations() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: [...FAMILY, "lists"] });
  return {
    create: useCacheWriteMutation<Envelope<EmList>, EmListInput>({
      mutationFn: (body) => api.post<Envelope<EmList>>(`${BASE}/lists`, body),
      targets: [
        {
          queryKey: emKeys.lists(),
          commit: (old: EmList[] | undefined, res) => {
            const row = unwrap<EmList | null>(res, null);
            return row ? listOps.replace(old, row.id, row, "prepend") : old;
          },
        },
      ],
    }),
    update: useCacheWriteMutation<Envelope<EmList>, { id: string; body: Partial<EmListInput> }>({
      mutationFn: ({ id, body }) =>
        api.patch<Envelope<EmList>>(`${BASE}/lists/${encodeURIComponent(id)}`, body),
      targets: ({ id }) => [
        {
          queryKey: emKeys.lists(),
          commit: (old: EmList[] | undefined, res) => {
            const row = unwrap<EmList | null>(res, null);
            return row ? listOps.patch(old, id, row) : old;
          },
        },
      ],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/lists/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: emKeys.lists(),
          optimistic: (old: EmList[] | undefined) => listOps.remove(old, id),
        },
      ],
    }),
    addMembers: useMutation({ // noc-allow: invalidate-only — the answer carries no rows: the member contacts and the list's contact_count come from a refetch
      mutationFn: ({ id, contactIds }: { id: string; contactIds: string[] }) =>
        api.post(`${BASE}/lists/${encodeURIComponent(id)}/members`, {
          contact_ids: contactIds,
        }),
      onSuccess: invalidate,
    }),
    removeMembers: useCacheWriteMutation<unknown, { id: string; contactIds: string[] }>({
      // DELETE with a body — the route declares `ListMembersRemove`.
      mutationFn: ({ id, contactIds }) =>
        api.delete(`${BASE}/lists/${encodeURIComponent(id)}/members`, {
          contact_ids: contactIds,
        }),
      targets: ({ id, contactIds }) => [
        {
          queryKey: emKeys.listContacts(id),
          optimistic: (old: EmContact[] | undefined) =>
            contactIds.reduce((acc: EmContact[] | undefined, cid) => listOps.remove(acc, cid), old),
        },
        {
          queryKey: emKeys.lists(),
          optimistic: (old: EmList[] | undefined, vars) =>
            old?.map((l) =>
              l.id === id ? { ...l, contact_count: Math.max(0, l.contact_count - vars.contactIds.length) } : l,
            ),
        },
      ],
      invalidate: [[...FAMILY, "lists"]],
    }),
  };
}

// ─── Templates ───────────────────────────────────────────────────────────────

export function useEmTemplates(categoria?: string) {
  return useQuery({
    queryKey: emKeys.templates(categoria),
    queryFn: async () =>
      unwrap<EmTemplate[]>(
        await api.get<Envelope<EmTemplate[]>>(
          `${BASE}/templates${qs({ categoria })}`,
        ),
        [],
      ),
  });
}

export interface TemplatePreview {
  assunto: string;
  corpo_html: string;
  variaveis_usadas?: string[];
}

export interface EmTemplateInput {
  nome: string;
  assunto: string;
  corpo_html: string;
  corpo_text?: string | null;
  variaveis?: string[];
  categoria?: TemplateCategoria;
  ativo?: boolean;
}

export function useEmTemplateMutations() {
  return {
    create: useCacheWriteMutation<Envelope<EmTemplate>, EmTemplateInput>({
      mutationFn: (body) => api.post<Envelope<EmTemplate>>(`${BASE}/templates`, body),
      targets: [
        {
          queryKey: emKeys.templates(),
          commit: (old: EmTemplate[] | undefined, res) => {
            const row = unwrap<EmTemplate | null>(res, null);
            return row ? listOps.replace(old, row.id, row, "prepend") : old;
          },
        },
      ],
      invalidate: [[...FAMILY, "templates"]],
    }),
    update: useCacheWriteMutation<Envelope<EmTemplate>, { id: string; body: Partial<EmTemplateInput> }>({
      mutationFn: ({ id, body }) =>
        api.patch<Envelope<EmTemplate>>(
          `${BASE}/templates/${encodeURIComponent(id)}`,
          body,
        ),
      targets: ({ id }) => [
        {
          queryKey: [...FAMILY, "templates"],
          match: "prefix",
          commit: (old: EmTemplate[] | undefined, res) => {
            const row = unwrap<EmTemplate | null>(res, null);
            return row ? listOps.patch(old, id, row) : old;
          },
        },
      ],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/templates/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: [...FAMILY, "templates"],
          match: "prefix",
          optimistic: (old: EmTemplate[] | undefined) => listOps.remove(old, id),
        },
      ],
    }),
    preview: useMutation({ // noc-allow: invalidate-only — a render-only call: nothing is written, no cached read
      mutationFn: ({
        id,
        variaveis,
      }: {
        id: string;
        variaveis: Record<string, string>;
      }) =>
        // Field names mirror the route's own response, verified live:
        // `{assunto, corpo_html, variaveis_usadas}` — NOT `html`.
        api.post<Envelope<TemplatePreview>>(
          `${BASE}/templates/${encodeURIComponent(id)}/preview`,
          { variaveis },
        ),
    }),
  };
}

// ─── Automations ─────────────────────────────────────────────────────────────

export function useEmAutomations(status?: string) {
  return useQuery({
    queryKey: emKeys.automations(status),
    queryFn: async () =>
      unwrap<EmAutomation[]>(
        await api.get<Envelope<EmAutomation[]>>(
          `${BASE}/automations${qs({ status })}`,
        ),
        [],
      ),
  });
}

export function useEmAutomationSteps(automationId: string | null) {
  return useQuery({
    queryKey: emKeys.steps(automationId ?? "_none"),
    enabled: !!automationId,
    queryFn: async () =>
      unwrap<EmAutomationStep[]>(
        await api.get<Envelope<EmAutomationStep[]>>(
          `${BASE}/automations/${encodeURIComponent(automationId!)}/steps`,
        ),
        [],
      ),
  });
}

export function useEmAutomationEnrollments(automationId: string | null) {
  return useQuery({
    queryKey: emKeys.enrollments(automationId ?? "_none"),
    enabled: !!automationId,
    queryFn: async () =>
      unwrap<EmEnrollment[]>(
        await api.get<Envelope<EmEnrollment[]>>(
          `${BASE}/automations/${encodeURIComponent(automationId!)}/enrollments`,
        ),
        [],
      ),
  });
}

export interface EmAutomationInput {
  nome: string;
  descricao?: string | null;
  trigger_type: string;
  trigger_config?: Record<string, unknown>;
}

const AUTOMATIONS_KEY = [...FAMILY, "automations"] as const;
const automationStatus = (id: string, status: AutomationStatus) => [
  {
    queryKey: AUTOMATIONS_KEY,
    match: "prefix" as const,
    optimistic: (old: EmAutomation[] | undefined) => listOps.patch(old, id, { status }),
  },
];

export function useEmAutomationMutations() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY });
  return {
    create: useCacheWriteMutation<Envelope<EmAutomation>, EmAutomationInput>({
      mutationFn: (body) => api.post<Envelope<EmAutomation>>(`${BASE}/automations`, body),
      targets: [
        {
          queryKey: emKeys.automations(),
          commit: (old: EmAutomation[] | undefined, res) => {
            const row = unwrap<EmAutomation | null>(res, null);
            return row ? listOps.replace(old, row.id, row, "prepend") : old;
          },
        },
      ],
      invalidate: [AUTOMATIONS_KEY],
    }),
    update: useCacheWriteMutation<Envelope<EmAutomation>, { id: string; body: Partial<EmAutomationInput> }>({
      mutationFn: ({ id, body }) =>
        api.patch<Envelope<EmAutomation>>(
          `${BASE}/automations/${encodeURIComponent(id)}`,
          body,
        ),
      targets: ({ id }) => [
        {
          queryKey: AUTOMATIONS_KEY,
          match: "prefix",
          commit: (old: EmAutomation[] | undefined, res) => {
            const row = unwrap<EmAutomation | null>(res, null);
            return row ? listOps.patch(old, id, row) : old;
          },
        },
      ],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/automations/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: AUTOMATIONS_KEY,
          match: "prefix",
          optimistic: (old: EmAutomation[] | undefined) => listOps.remove(old, id),
        },
      ],
    }),
    activate: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.post(`${BASE}/automations/${encodeURIComponent(id)}/activate`, {}),
      targets: (id) => automationStatus(id, "ativa"),
      invalidate: [AUTOMATIONS_KEY],
    }),
    pause: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.post(`${BASE}/automations/${encodeURIComponent(id)}/pause`, {}),
      targets: (id) => automationStatus(id, "pausada"),
      invalidate: [AUTOMATIONS_KEY],
    }),
    addStep: useMutation({ // noc-allow: invalidate-only — the answer is untyped and the step's id/posicao are server-assigned: the steps list comes from a refetch
      mutationFn: ({
        id,
        tipo,
        config,
      }: {
        id: string;
        tipo: string;
        config: Record<string, unknown>;
      }) =>
        api.post(`${BASE}/automations/${encodeURIComponent(id)}/steps`, {
          tipo,
          config,
        }),
      onSuccess: invalidate,
    }),
    updateStep: useCacheWriteMutation<
      unknown,
      { id: string; stepId: string; body: { tipo?: string; config?: Record<string, unknown> } }
    >({
      mutationFn: ({ id, stepId, body }) =>
        api.patch(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/${encodeURIComponent(stepId)}`,
          body,
        ),
      targets: ({ id, stepId }) => [
        {
          queryKey: emKeys.steps(id),
          optimistic: (old: EmAutomationStep[] | undefined, vars) => listOps.patch(old, stepId, vars.body),
        },
      ],
      invalidate: [AUTOMATIONS_KEY],
    }),
    removeStep: useCacheWriteMutation<unknown, { id: string; stepId: string }>({
      mutationFn: ({ id, stepId }) =>
        api.delete(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/${encodeURIComponent(stepId)}`,
        ),
      targets: ({ id, stepId }) => [
        {
          queryKey: emKeys.steps(id),
          optimistic: (old: EmAutomationStep[] | undefined) => listOps.remove(old, stepId),
        },
      ],
      invalidate: [AUTOMATIONS_KEY],
    }),
    reorderSteps: useCacheWriteMutation<unknown, { id: string; stepIds: string[] }>({
      mutationFn: ({ id, stepIds }) =>
        api.post(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/reorder`,
          { step_ids: stepIds },
        ),
      targets: ({ id, stepIds }) => [
        {
          queryKey: emKeys.steps(id),
          optimistic: (old: EmAutomationStep[] | undefined) =>
            old
              ? [...old].sort((a, b) => stepIds.indexOf(a.id) - stepIds.indexOf(b.id))
              : old,
        },
      ],
      invalidate: [AUTOMATIONS_KEY],
    }),
    enroll: useMutation({ // noc-allow: invalidate-only — enrollments are rows the server creates per contact; the answer carries none
      mutationFn: ({ id, contactIds }: { id: string; contactIds: string[] }) =>
        api.post(`${BASE}/automations/${encodeURIComponent(id)}/enroll`, {
          contact_ids: contactIds,
        }),
      onSuccess: invalidate,
    }),
  };
}

// ─── Sending domains ─────────────────────────────────────────────────────────

export function useEmDomains() {
  return useQuery({
    queryKey: emKeys.domains(),
    queryFn: async () =>
      unwrap<EmDomain[]>(
        await api.get<Envelope<EmDomain[]>>(`${BASE}/settings/domains`),
        [],
      ),
  });
}

export function useEmDomainMutations() {
  return {
    add: useCacheWriteMutation<Envelope<EmDomain>, string>({
      mutationFn: (domain) => api.post<Envelope<EmDomain>>(`${BASE}/settings/domains`, { domain }),
      targets: [
        {
          queryKey: emKeys.domains(),
          commit: (old: EmDomain[] | undefined, res) => {
            const row = unwrap<EmDomain | null>(res, null);
            return row ? listOps.replace(old, row.id, row) : old;
          },
        },
      ],
    }),
    verify: useCacheWriteMutation<Envelope<EmDomain>, string>({
      mutationFn: (id) =>
        api.get<Envelope<EmDomain>>(
          `${BASE}/settings/domains/${encodeURIComponent(id)}/verify`,
        ),
      targets: (id) => [
        {
          queryKey: emKeys.domains(),
          commit: (old: EmDomain[] | undefined, res) => {
            const row = unwrap<EmDomain | null>(res, null);
            return row ? listOps.patch(old, id, row) : old;
          },
        },
      ],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/settings/domains/${encodeURIComponent(id)}`),
      targets: (id) => [
        {
          queryKey: emKeys.domains(),
          optimistic: (old: EmDomain[] | undefined) => listOps.remove(old, id),
        },
      ],
    }),
  };
}

// ─── AI assists ──────────────────────────────────────────────────────────────

export function useEmAi() {
  return {
    subjects: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: (campaignSummary: string) =>
        api.post<Envelope<{ subjects?: string[] }>>(`${BASE}/ai/subjects`, {
          campaign_summary: campaignSummary,
        }),
    }),
    templateDraft: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: (prompt: string) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/template-draft`, {
          prompt,
        }),
    }),
    reengagement: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: (context: string) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/reengagement`, {
          context,
        }),
    }),
    deliverability: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: ({ html, subject }: { html: string; subject?: string }) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/deliverability`, {
          html,
          subject: subject ?? null,
        }),
    }),
    translate: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: ({ html, targetLang }: { html: string; targetLang: string }) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/translate`, {
          html,
          target_lang: targetLang,
        }),
    }),
    segmentContacts: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: (body: Record<string, unknown>) =>
        api.post<Envelope<Record<string, unknown>>>(
          `${BASE}/ai/segment-contacts`,
          body,
        ),
    }),
    sendDebrief: useMutation({ // noc-allow: invalidate-only — AI call: computes a result for the caller, writes nothing cached
      mutationFn: (campaignId: string) =>
        api.post<Envelope<unknown>>(
          `${BASE}/ai/campaigns/${encodeURIComponent(campaignId)}/debrief/send`,
          {},
        ),
    }),
  };
}

export function useEmDebrief(campaignId: string | null) {
  return useQuery({
    queryKey: emKeys.debrief(campaignId ?? "_none"),
    enabled: !!campaignId,
    queryFn: async () =>
      unwrap<Record<string, unknown> | null>(
        await api.get<Envelope<Record<string, unknown>>>(
          `${BASE}/ai/campaigns/${encodeURIComponent(campaignId!)}/debrief`,
        ),
        null,
      ),
  });
}

// ── Public unsubscribe (/descadastro/:token) ──────────────────────────
// Token-authenticated, no session: the recipient is NOT logged in. Lives here
// (not inline in the page) per the module's hooks-file pattern.

const EM_UNSUBSCRIBE = "/api/email-marketing/unsubscribe";

export interface EmUnsubscribeInfo {
  email: string;
  valid: boolean;
}

export function useEmUnsubscribeInfo(token: string | undefined) {
  return useQuery({
    queryKey: ["sw", "email-marketing", "unsubscribe", token ?? "_none"],
    enabled: !!token,
    retry: false,
    // An invalid/expired link is a stable state the page renders itself —
    // the global "Erro ao carregar dados" toast would only duplicate it.
    meta: { suppressErrorToastStatuses: [400] },
    queryFn: () =>
      api.get<EmUnsubscribeInfo>(`${EM_UNSUBSCRIBE}/${encodeURIComponent(token!)}`),
  });
}

export function useEmConfirmUnsubscribe(token: string | undefined) {
  return useMutation({ // noc-allow: invalidate-only — public token page (no session, no cached read)
    mutationFn: () =>
      api.post<{ ok: boolean; already?: boolean; message?: string }>(
        `${EM_UNSUBSCRIBE}/${encodeURIComponent(token!)}`,
      ),
  });
}


// ── Public double opt-in confirmation (/confirmar-email/:token) ───────
// Token-authenticated, no session: the recipient is NOT logged in.

const EM_CONFIRM = "/api/email-marketing/confirm";

export interface EmConfirmInfo {
  email: string;
  valid: boolean;
}

export function useEmConfirmEmailInfo(token: string | undefined) {
  return useQuery({
    queryKey: ["sw", "email-marketing", "confirm-email", token ?? "_none"],
    enabled: !!token,
    retry: false,
    // 400 invalid/expired link · 404 contact gone — both rendered by the page
    // as "Link inválido ou expirado"; a global toast on top only alarms.
    meta: { suppressErrorToastStatuses: [400, 404] },
    queryFn: () => api.get<EmConfirmInfo>(`${EM_CONFIRM}/${encodeURIComponent(token!)}`),
  });
}

export function useEmConfirmEmail(token: string | undefined) {
  return useMutation({ // noc-allow: invalidate-only — public token page (no session, no cached read)
    mutationFn: () =>
      api.post<{ ok: boolean; already?: boolean; email?: string; message?: string }>(
        `${EM_CONFIRM}/${encodeURIComponent(token!)}`,
      ),
  });
}
