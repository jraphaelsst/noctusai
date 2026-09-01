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
  created_at: string;
  updated_at: string;
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
}

export interface EmDomain {
  id: string;
  org_id: string;
  domain: string;
  resend_domain_id: string | null;
  status: DomainStatus;
  dns_records: unknown;
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

export function useEmCampaignMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [...FAMILY, "campaigns"] });
    qc.invalidateQueries({ queryKey: emKeys.dashboard() });
  };

  return {
    create: useMutation({
      mutationFn: (body: EmCampaignInput) =>
        api.post<Envelope<EmCampaign>>(`${BASE}/campaigns`, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<EmCampaignInput> }) =>
        api.patch<Envelope<EmCampaign>>(
          `${BASE}/campaigns/${encodeURIComponent(id)}`,
          body,
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/campaigns/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
    schedule: useMutation({
      mutationFn: ({ id, scheduledAt }: { id: string; scheduledAt: string }) =>
        api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/schedule`, {
          scheduled_at: scheduledAt,
        }),
      onSuccess: invalidate,
    }),
    send: useMutation({
      mutationFn: (id: string) =>
        api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/send`, {}),
      onSuccess: invalidate,
    }),
    pause: useMutation({
      mutationFn: (id: string) =>
        api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/pause`, {}),
      onSuccess: invalidate,
    }),
    cancel: useMutation({
      mutationFn: (id: string) =>
        api.post(`${BASE}/campaigns/${encodeURIComponent(id)}/cancel`, {}),
      onSuccess: invalidate,
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

export function useEmContactMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [...FAMILY, "contacts"] });
    qc.invalidateQueries({ queryKey: emKeys.dashboard() });
  };
  return {
    create: useMutation({
      mutationFn: (body: EmContactInput) =>
        api.post<Envelope<EmContact>>(`${BASE}/contacts`, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<EmContactInput> }) =>
        api.patch<Envelope<EmContact>>(
          `${BASE}/contacts/${encodeURIComponent(id)}`,
          body,
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/contacts/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
    importMany: useMutation({
      mutationFn: (contacts: EmContactInput[]) =>
        api.post<Envelope<unknown>>(`${BASE}/contacts/import`, { contacts }),
      onSuccess: invalidate,
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
    create: useMutation({
      mutationFn: (body: EmListInput) =>
        api.post<Envelope<EmList>>(`${BASE}/lists`, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<EmListInput> }) =>
        api.patch<Envelope<EmList>>(`${BASE}/lists/${encodeURIComponent(id)}`, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/lists/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
    addMembers: useMutation({
      mutationFn: ({ id, contactIds }: { id: string; contactIds: string[] }) =>
        api.post(`${BASE}/lists/${encodeURIComponent(id)}/members`, {
          contact_ids: contactIds,
        }),
      onSuccess: invalidate,
    }),
    removeMembers: useMutation({
      // DELETE with a body — the route declares `ListMembersRemove`.
      mutationFn: ({ id, contactIds }: { id: string; contactIds: string[] }) =>
        api.delete(`${BASE}/lists/${encodeURIComponent(id)}/members`, {
          contact_ids: contactIds,
        }),
      onSuccess: invalidate,
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
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: [...FAMILY, "templates"] });
  return {
    create: useMutation({
      mutationFn: (body: EmTemplateInput) =>
        api.post<Envelope<EmTemplate>>(`${BASE}/templates`, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<EmTemplateInput> }) =>
        api.patch<Envelope<EmTemplate>>(
          `${BASE}/templates/${encodeURIComponent(id)}`,
          body,
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/templates/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
    preview: useMutation({
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

export function useEmAutomationMutations() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: [...FAMILY, "automations"] });
  return {
    create: useMutation({
      mutationFn: (body: EmAutomationInput) =>
        api.post<Envelope<EmAutomation>>(`${BASE}/automations`, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({
        id,
        body,
      }: {
        id: string;
        body: Partial<EmAutomationInput>;
      }) =>
        api.patch<Envelope<EmAutomation>>(
          `${BASE}/automations/${encodeURIComponent(id)}`,
          body,
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/automations/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
    activate: useMutation({
      mutationFn: (id: string) =>
        api.post(`${BASE}/automations/${encodeURIComponent(id)}/activate`, {}),
      onSuccess: invalidate,
    }),
    pause: useMutation({
      mutationFn: (id: string) =>
        api.post(`${BASE}/automations/${encodeURIComponent(id)}/pause`, {}),
      onSuccess: invalidate,
    }),
    addStep: useMutation({
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
    updateStep: useMutation({
      mutationFn: ({
        id,
        stepId,
        body,
      }: {
        id: string;
        stepId: string;
        body: { tipo?: string; config?: Record<string, unknown> };
      }) =>
        api.patch(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/${encodeURIComponent(stepId)}`,
          body,
        ),
      onSuccess: invalidate,
    }),
    removeStep: useMutation({
      mutationFn: ({ id, stepId }: { id: string; stepId: string }) =>
        api.delete(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/${encodeURIComponent(stepId)}`,
        ),
      onSuccess: invalidate,
    }),
    reorderSteps: useMutation({
      mutationFn: ({ id, stepIds }: { id: string; stepIds: string[] }) =>
        api.post(
          `${BASE}/automations/${encodeURIComponent(id)}/steps/reorder`,
          { step_ids: stepIds },
        ),
      onSuccess: invalidate,
    }),
    enroll: useMutation({
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
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: emKeys.domains() });
  return {
    add: useMutation({
      mutationFn: (domain: string) =>
        api.post<Envelope<EmDomain>>(`${BASE}/settings/domains`, { domain }),
      onSuccess: invalidate,
    }),
    verify: useMutation({
      mutationFn: (id: string) =>
        api.get<Envelope<EmDomain>>(
          `${BASE}/settings/domains/${encodeURIComponent(id)}/verify`,
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api.delete(`${BASE}/settings/domains/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    }),
  };
}

// ─── AI assists ──────────────────────────────────────────────────────────────

export function useEmAi() {
  return {
    subjects: useMutation({
      mutationFn: (campaignSummary: string) =>
        api.post<Envelope<{ subjects?: string[] }>>(`${BASE}/ai/subjects`, {
          campaign_summary: campaignSummary,
        }),
    }),
    templateDraft: useMutation({
      mutationFn: (prompt: string) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/template-draft`, {
          prompt,
        }),
    }),
    reengagement: useMutation({
      mutationFn: (context: string) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/reengagement`, {
          context,
        }),
    }),
    deliverability: useMutation({
      mutationFn: ({ html, subject }: { html: string; subject?: string }) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/deliverability`, {
          html,
          subject: subject ?? null,
        }),
    }),
    translate: useMutation({
      mutationFn: ({ html, targetLang }: { html: string; targetLang: string }) =>
        api.post<Envelope<Record<string, unknown>>>(`${BASE}/ai/translate`, {
          html,
          target_lang: targetLang,
        }),
    }),
    segmentContacts: useMutation({
      mutationFn: (body: Record<string, unknown>) =>
        api.post<Envelope<Record<string, unknown>>>(
          `${BASE}/ai/segment-contacts`,
          body,
        ),
    }),
    sendDebrief: useMutation({
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
