/**
 * Core website admin — typed client + react-query hooks for the
 * Configurações + Leads surfaces (contract `src/website/docs/15-api-contract.md`
 * §2 `WebsiteSettings`, §3 admin API).
 *
 * Same DI-seam shape as `./billing.ts`: the HTTP client arrives through
 * `WebsiteApiContext` (default: the app's `api`), so tests render pages with
 * a fake client instead of mocking modules. Loading flags follow the
 * two-signal rule everywhere: `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data` (`KB § PATTERNS/frontend/lying-loading-state.md`).
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@noctusai/lib';
import { api } from './api';

// ── Types (contract §1 / §2 / §3) ──────────────────────────────────────────

export type L10n = { pt: string; en: string };

export type ProductState = 'disponivel' | 'lista_de_espera' | 'em_breve';

export interface WebsiteProductEntry {
  slug: string;
  visible: boolean;
  order: number;
  state: ProductState;
  tagline?: L10n;
}

export interface TrustItem {
  key: string;
  icon: string;
  text: L10n;
  verified_by: string | null;
  verified_at: string | null;
}

export type SocialProofKind = 'logo' | 'testimonial' | 'metric';

export interface SocialProofItem {
  kind: SocialProofKind;
  name: string;
  text?: L10n;
  image_url?: string;
  consent_ref: string;
}

export interface FaqItem {
  q: L10n;
  a: L10n;
}

export interface WebsiteSettings {
  site_enabled: boolean;
  signup_enabled: boolean;
  whatsapp: { number_e164: string | null; default_message: L10n; float_enabled: boolean };
  sections: {
    audiences: boolean;
    products: boolean;
    custom_builds: boolean;
    trust: boolean;
    social_proof: boolean;
    pricing: boolean;
    news: boolean;
    faq: boolean;
    hero_update_card: boolean;
  };
  products: WebsiteProductEntry[];
  trust_items: TrustItem[];
  social_proof_items: SocialProofItem[];
  faq: FaqItem[];
  tracking: { plausible_domain: string | null; ga4_id: string | null; meta_pixel_id: string | null };
}

export type SectionKey = keyof WebsiteSettings['sections'];

export interface WebsiteSettingsVersion {
  version: number;
  settings: WebsiteSettings;
  created_at: string;
  created_by: string | null;
}

export interface WebsiteSettingsHistoryEntry {
  version: number;
  created_at: string;
  created_by: string | null;
}

export type LeadSource = 'waitlist' | 'brief' | 'contact' | 'signup_intent';
export type LeadStage = 'novo' | 'contatado' | 'qualificado' | 'proposta' | 'ganho' | 'perdido' | 'descartado';
export type LeadProfile = 'smb' | 'enterprise' | 'developer' | 'solo';

export interface Lead {
  id: string;
  created_at: string;
  updated_at: string;
  source: LeadSource;
  name: string;
  email: string | null;
  phone_e164: string | null;
  company: string | null;
  profile: LeadProfile | null;
  product_interest: string[];
  message: string | null;
  locale: 'pt-BR' | 'en';
  utm: Record<string, unknown>;
  landing_path: string | null;
  referrer: string | null;
  consent: { marketing: boolean; text_version: string; at: string; ip_hash: string };
  stage: LeadStage;
  owner_user_id: string | null;
  owner_agent: string | null;
  score: number | null;
  next_action: string | null;
  next_action_at: string | null;
  lost_reason: string | null;
  dedupe_key: string;
}

export type ActivityKind =
  | 'created' | 'form_submit' | 'note' | 'stage_change' | 'whatsapp_out' | 'whatsapp_in'
  | 'email_out' | 'call' | 'agent_action' | 'handoff' | 'fanout_failed';

export interface LeadActivity {
  id: string;
  lead_id: string;
  at: string;
  kind: ActivityKind;
  actor: string;
  payload: Record<string, unknown>;
}

export interface LeadWithActivities extends Lead {
  activities: LeadActivity[];
}

export interface LeadStats {
  new_today: number;
  new_7d: number;
  by_source: Record<string, number>;
  by_stage: Record<string, number>;
  events_7d: Record<string, number>;
}

export interface LeadListFilters {
  stage?: LeadStage | '';
  source?: LeadSource | '';
  q?: string;
  limit?: number;
  offset?: number;
}

export type LeadPatchBody = Partial<
  Pick<Lead, 'stage' | 'owner_user_id' | 'next_action' | 'next_action_at' | 'lost_reason' | 'score'>
>;

export type ActivityKindWritable = 'note' | 'call' | 'whatsapp_out' | 'email_out';

// ── HTTP client seam (DI for tests, mirrors ./billing.ts) ─────────────────

export interface HttpClient {
  get<T = any>(path: string, params?: Record<string, any>): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  put<T = any>(path: string, body?: unknown): Promise<T>;
  patch<T = any>(path: string, body?: unknown): Promise<T>;
  download(path: string): Promise<Blob>;
}

export function createWebsiteApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  return {
    settings: () => unwrap<WebsiteSettingsVersion>(http.get('/api/admin/website/settings')),
    updateSettings: (settings: WebsiteSettings, expectedVersion: number) =>
      unwrap<WebsiteSettingsVersion>(
        http.put('/api/admin/website/settings', { settings, expected_version: expectedVersion }),
      ),
    history: () => unwrap<WebsiteSettingsHistoryEntry[]>(http.get('/api/admin/website/settings/history')),
    rollback: (version: number) =>
      unwrap<WebsiteSettingsVersion>(http.post('/api/admin/website/settings/rollback', { version })),
    leads: (filters: LeadListFilters) =>
      http.get<{ data: Lead[]; total: number }>('/api/admin/website/leads', {
        stage: filters.stage || undefined,
        source: filters.source || undefined,
        q: filters.q || undefined,
        limit: filters.limit ?? 50,
        offset: filters.offset ?? 0,
      }),
    lead: (id: string) => unwrap<LeadWithActivities>(http.get(`/api/admin/website/leads/${id}`)),
    patchLead: (id: string, body: LeadPatchBody) => unwrap<Lead>(http.patch(`/api/admin/website/leads/${id}`, body)),
    addActivity: (id: string, body: { kind: ActivityKindWritable; body: string }) =>
      unwrap<LeadActivity>(http.post(`/api/admin/website/leads/${id}/activities`, body)),
    stats: () => unwrap<LeadStats>(http.get('/api/admin/website/stats')),
    exportCsv: (filters: LeadListFilters) => {
      const params = new URLSearchParams();
      if (filters.stage) params.set('stage', filters.stage);
      if (filters.source) params.set('source', filters.source);
      if (filters.q) params.set('q', filters.q);
      const qs = params.toString();
      return http.download(`/api/admin/website/leads/export.csv${qs ? `?${qs}` : ''}`);
    },
  };
}

export type WebsiteApi = ReturnType<typeof createWebsiteApi>;

const WebsiteApiContext = createContext<WebsiteApi>(createWebsiteApi(api));

export function WebsiteApiProvider({ value, children }: { value: WebsiteApi; children: ReactNode }) {
  return createElement(WebsiteApiContext.Provider, { value }, children);
}

export function useWebsiteApi(): WebsiteApi {
  return useContext(WebsiteApiContext);
}

// ── queries ─────────────────────────────────────────────────────────────

const KEY = ['core-website'] as const;

export function useWebsiteSettings() {
  const w = useWebsiteApi();
  return useQuery({ queryKey: [...KEY, 'settings'], queryFn: w.settings });
}

export function useWebsiteSettingsHistory() {
  const w = useWebsiteApi();
  return useQuery({ queryKey: [...KEY, 'history'], queryFn: w.history });
}

/** True for a mutation error that is (or presents as) an HTTP 409 — the
 * settings version-conflict shape (contract §3: `409 {"detail":"version_conflict"}`). */
export function isConflictError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

export function useUpdateWebsiteSettings() {
  const w = useWebsiteApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { settings: WebsiteSettings; expectedVersion: number }) =>
      w.updateSettings(vars.settings, vars.expectedVersion),
    onSuccess: (result) => {
      qc.setQueryData([...KEY, 'settings'], result);
      qc.invalidateQueries({ queryKey: [...KEY, 'history'] });
    },
  });
}

export function useRollbackWebsiteSettings() {
  const w = useWebsiteApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: number) => w.rollback(version),
    onSuccess: (result) => {
      qc.setQueryData([...KEY, 'settings'], result);
      qc.invalidateQueries({ queryKey: [...KEY, 'history'] });
    },
  });
}

export function useWebsiteLeads(filters: LeadListFilters) {
  const w = useWebsiteApi();
  return useQuery({
    queryKey: [
      ...KEY, 'leads',
      filters.stage ?? '', filters.source ?? '', filters.q ?? '',
      filters.limit ?? 50, filters.offset ?? 0,
    ],
    queryFn: () => w.leads(filters),
    // Filter/page change keeps the previous rows on screen instead of
    // flashing an empty table (two-signal loading rule).
    placeholderData: (previous) => previous,
  });
}

export function useWebsiteLead(id: string | undefined) {
  const w = useWebsiteApi();
  return useQuery({
    queryKey: [...KEY, 'lead', id],
    queryFn: () => w.lead(id as string),
    enabled: !!id,
  });
}

export function useWebsiteLeadStats() {
  const w = useWebsiteApi();
  return useQuery({ queryKey: [...KEY, 'stats'], queryFn: w.stats });
}

export function usePatchWebsiteLead(id: string) {
  const w = useWebsiteApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LeadPatchBody) => w.patchLead(id, body),
    onSuccess: (result) => {
      qc.setQueryData([...KEY, 'lead', id], (prev: LeadWithActivities | undefined) =>
        prev ? { ...prev, ...result } : prev);
      qc.invalidateQueries({ queryKey: [...KEY, 'leads'] });
    },
  });
}

export function useAddLeadActivity(id: string) {
  const w = useWebsiteApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { kind: ActivityKindWritable; body: string }) => w.addActivity(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...KEY, 'lead', id] });
    },
  });
}

export function useExportLeadsCsv() {
  const w = useWebsiteApi();
  return useMutation({ mutationFn: (filters: LeadListFilters) => w.exportCsv(filters) });
}

// ── formatting / labels ─────────────────────────────────────────────────

export const STAGE_LABEL: Record<LeadStage, string> = {
  novo: 'Novo',
  contatado: 'Contatado',
  qualificado: 'Qualificado',
  proposta: 'Proposta',
  ganho: 'Ganho',
  perdido: 'Perdido',
  descartado: 'Descartado',
};

export const SOURCE_LABEL: Record<LeadSource, string> = {
  waitlist: 'Lista de espera',
  brief: 'Briefing',
  contact: 'Contato',
  signup_intent: 'Intenção de cadastro',
};

export const ACTIVITY_LABEL: Record<ActivityKind, string> = {
  created: 'Lead criado',
  form_submit: 'Formulário enviado',
  note: 'Nota',
  stage_change: 'Mudança de estágio',
  whatsapp_out: 'WhatsApp enviado',
  whatsapp_in: 'WhatsApp recebido',
  email_out: 'E-mail enviado',
  call: 'Ligação',
  agent_action: 'Ação do agente',
  handoff: 'Transferência',
  fanout_failed: 'Falha no envio',
};

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('pt-BR');
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('pt-BR');
}

/** `https://wa.me/<digits>` per contract — digits only, no `+`/spaces/punctuation. */
export function whatsAppUrl(phoneE164: string | null | undefined, prefill?: string): string | null {
  if (!phoneE164) return null;
  const digits = phoneE164.replace(/\D/g, '');
  if (!digits) return null;
  return `https://wa.me/${digits}${prefill ? `?text=${encodeURIComponent(prefill)}` : ''}`;
}

/** A trust item is "published" only once BOTH `verified_by` and `verified_at`
 * are set (contract §6 "Confiança"; docs `11 §Configurações` P7) — either
 * alone is an unverifiable claim. */
export function isTrustItemPublished(item: TrustItem): boolean {
  return !!item.verified_by && !!item.verified_at;
}
