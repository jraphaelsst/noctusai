/**
 * Core billing — typed client + react-query hooks.
 *
 * The HTTP client arrives through `BillingApiContext` (default: the app's
 * `api`), so tests render pages with a fake client instead of mocking
 * modules. Loading flags follow the two-signal rule:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';

export type Gateway = 'stripe' | 'asaas';
export type GatewayMode = 'test' | 'live';
export type BillingCycle = 'monthly' | 'yearly';
export type SubscriptionStatus =
  | 'incomplete' | 'trial' | 'active' | 'past_due' | 'grace' | 'canceled' | 'expired';
export type SecretField = 'secret_key' | 'webhook_secret' | 'api_key' | 'webhook_token';

export interface PlanPrice {
  id: string;
  plan_id?: string;
  billing_cycle: BillingCycle;
  currency: string;
  amount_cents: number;
  stripe_price_id_test?: string | null;
  stripe_price_id_live?: string | null;
  ativo?: boolean;
}

export interface BillingPlan {
  id: string;
  nome: string;
  slug: string;
  descricao?: string | null;
  product_id?: string | null;
  audience: 'individual' | 'company' | 'any';
  trial_days: number;
  grace_days?: number;
  ativo?: boolean;
  prices: PlanPrice[];
}

export interface SecretStatus {
  configured: boolean;
  source: 'db' | 'env' | null;
}

export interface BillingSettings {
  mode: GatewayMode;
  automations_enabled: boolean;
  encryption_configured: boolean;
  storage_price_usd_per_gb_month: string | null;
  gateways: Record<Gateway, {
    enabled: boolean;
    modes: Record<GatewayMode, Partial<Record<SecretField, SecretStatus>>>;
  }>;
  webhook_urls: Record<Gateway, string>;
}

export interface BillingSummary {
  mrr: number;
  arr: number;
  counted_subscriptions: number;
  non_brl_mrr: Record<string, number>;
  counts: Record<SubscriptionStatus, number>;
  mode: GatewayMode;
  automations_enabled: boolean;
}

export interface AdminSubscription {
  id: string;
  org_id: string;
  status: SubscriptionStatus;
  gateway: Gateway | 'manual' | null;
  gateway_mode?: GatewayMode | null;
  billing_cycle?: BillingCycle | null;
  billing_method?: string | null;
  amount_cents?: number | null;
  currency?: string | null;
  current_period_end?: string | null;
  trial_ends_at?: string | null;
  grace_ends_at?: string | null;
  cancel_at_period_end?: boolean;
  automation_managed: boolean;
  created_at: string;
  organizations?: { id: string; nome: string; slug: string } | null;
  plans?: { id: string; nome: string } | null;
}

export interface BillingPayment {
  id: string;
  org_id: string;
  gateway: Gateway;
  gateway_mode: GatewayMode;
  status: 'pending' | 'paid' | 'failed' | 'refunded';
  billing_method?: string | null;
  currency: string;
  gross_cents: number;
  fee_cents: number;
  net_cents: number;
  fee_pending?: boolean;
  paid_at?: string | null;
  created_at: string;
  organizations?: { id: string; nome: string } | null;
}

export interface Page<T> {
  data: T[];
  total: number | null;
  page: number;
  page_size: number;
}

export interface PublicCatalog {
  plans: BillingPlan[];
  gateways: Gateway[];
}

export interface SubscribeResult {
  subscription_id: string;
  checkout_url: string;
  gateway: Gateway;
  mode: GatewayMode;
  pix_qr: { payload: string; encoded_image: string; expiration_date?: string | null } | null;
}

/** The subset of the seed `ApiClient` billing uses. */
export interface HttpClient {
  get<T = any>(path: string): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  put<T = any>(path: string, body?: unknown): Promise<T>;
  patch<T = any>(path: string, body?: unknown): Promise<T>;
}

export function createBillingApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  return {
    summary: () => unwrap<BillingSummary>(http.get('/api/admin/billing/summary')),
    plans: () => unwrap<BillingPlan[]>(http.get('/api/admin/billing/plans')),
    createPlan: (body: Partial<BillingPlan>) => unwrap<BillingPlan>(http.post('/api/admin/billing/plans', body)),
    updatePlan: (id: string, body: Partial<BillingPlan>) =>
      unwrap<BillingPlan>(http.patch(`/api/admin/billing/plans/${id}`, body)),
    createPrice: (planId: string, body: { billing_cycle: BillingCycle; amount_cents: number; currency?: string;
      stripe_price_id_test?: string; stripe_price_id_live?: string }) =>
      unwrap<PlanPrice>(http.post(`/api/admin/billing/plans/${planId}/prices`, body)),
    updatePrice: (id: string, body: Partial<PlanPrice>) =>
      unwrap<PlanPrice>(http.patch(`/api/admin/billing/prices/${id}`, body)),
    settings: () => unwrap<BillingSettings>(http.get('/api/admin/billing/settings')),
    updateSettings: (body: Partial<{ mode: GatewayMode; automations_enabled: boolean; stripe_enabled: boolean;
      asaas_enabled: boolean; storage_price_usd_per_gb_month: string }>) =>
      unwrap<BillingSettings>(http.put('/api/admin/billing/settings', body)),
    saveSecret: (body: { gateway: Gateway; mode: GatewayMode; field: SecretField; value: string }) =>
      unwrap<BillingSettings>(http.put('/api/admin/billing/settings/secrets', body)),
    testConnection: (body: { gateway: Gateway; mode: GatewayMode }) =>
      unwrap<{ ok: boolean; message: string; webhook_configured?: boolean }>(
        http.post('/api/admin/billing/settings/test-connection', body)),
    subscriptions: (page: number, status?: string) =>
      http.get<Page<AdminSubscription>>(
        `/api/admin/billing/subscriptions?page=${page}&page_size=50${status ? `&status=${status}` : ''}`),
    onboard: (body: { org_id: string; plan_price_id: string; trial_days?: number; note?: string;
      current_period_end?: string }) =>
      unwrap<AdminSubscription>(http.post('/api/admin/billing/subscriptions/manual', body)),
    renew: (id: string, currentPeriodEnd: string) =>
      unwrap<AdminSubscription>(http.post(`/api/admin/billing/subscriptions/${id}/renew`,
        { current_period_end: currentPeriodEnd })),
    cancel: (id: string, atPeriodEnd: boolean) =>
      unwrap<AdminSubscription>(http.post(`/api/admin/billing/subscriptions/${id}/cancel`,
        { at_period_end: atPeriodEnd })),
    payments: (page: number) =>
      http.get<Page<BillingPayment> & { page_totals_brl: Record<string, number> }>(
        `/api/admin/billing/payments?page=${page}&page_size=50`),
    publicCatalog: () => unwrap<PublicCatalog>(http.get('/api/billing/plans')),
    subscribe: (body: { plan_price_id: string; gateway: Gateway; billing_method: string; tax_id?: string;
      success_url?: string; cancel_url?: string }) =>
      unwrap<SubscribeResult>(http.post('/api/billing/subscribe', body)),
  };
}

export type BillingApi = ReturnType<typeof createBillingApi>;

const BillingApiContext = createContext<BillingApi>(createBillingApi(api));

export function BillingApiProvider({ value, children }: { value: BillingApi; children: ReactNode }) {
  return createElement(BillingApiContext.Provider, { value }, children);
}

export function useBillingApi(): BillingApi {
  return useContext(BillingApiContext);
}

// ── queries ─────────────────────────────────────────────────────────────

const KEY = ['core-billing'] as const;

export function useBillingSummary() {
  const b = useBillingApi();
  return useQuery({ queryKey: [...KEY, 'summary'], queryFn: b.summary });
}

export function useBillingPlans() {
  const b = useBillingApi();
  return useQuery({ queryKey: [...KEY, 'plans'], queryFn: b.plans });
}

export function useBillingSettings() {
  const b = useBillingApi();
  return useQuery({ queryKey: [...KEY, 'settings'], queryFn: b.settings });
}

export function useAdminSubscriptions(page: number, status?: string) {
  const b = useBillingApi();
  return useQuery({
    queryKey: [...KEY, 'subscriptions', page, status ?? ''],
    queryFn: () => b.subscriptions(page, status),
    // Page/filter change keeps the previous rows on screen instead of
    // flashing an empty table.
    placeholderData: (previous) => previous,
  });
}

export function useBillingPayments(page: number) {
  const b = useBillingApi();
  return useQuery({
    queryKey: [...KEY, 'payments', page],
    queryFn: () => b.payments(page),
    placeholderData: (previous) => previous,
  });
}

export function usePublicCatalog() {
  const b = useBillingApi();
  return useQuery({ queryKey: [...KEY, 'catalog'], queryFn: b.publicCatalog });
}

/** Mutation that refreshes every billing query on success. */
export function useBillingMutation<TVars, TResult>(fn: (api: BillingApi, vars: TVars) => Promise<TResult>) {
  const b = useBillingApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => fn(b, vars),
    onSuccess: (result) => {
      // Settings writes return the fresh view — use it directly.
      if (result && typeof result === 'object' && 'webhook_urls' in (result as object)) {
        qc.setQueryData([...KEY, 'settings'], result);
      }
      return qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

// ── formatting ──────────────────────────────────────────────────────────

export function formatCents(cents: number | null | undefined, currency = 'BRL'): string {
  if (cents == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format(cents / 100);
}

export function formatMoney(value: number, currency = 'BRL'): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('pt-BR');
}

/** "R$ 12,34" → 1234. Returns null for anything that is not a money amount. */
export function parseMoneyToCents(input: string): number | null {
  const cleaned = input.replace(/[^\d,.-]/g, '').trim();
  if (!cleaned) return null;
  const normalized = cleaned.includes(',')
    ? cleaned.replace(/\./g, '').replace(',', '.')
    : cleaned;
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  return Math.round(Number(normalized) * 100);
}

export const STATUS_LABEL: Record<SubscriptionStatus, string> = {
  incomplete: 'Aguardando pagamento',
  trial: 'Trial',
  active: 'Ativa',
  past_due: 'Pagamento pendente',
  grace: 'Carência',
  canceled: 'Cancelada',
  expired: 'Expirada',
};

export const STATUS_VARIANT: Record<SubscriptionStatus, 'default' | 'destructive' | 'muted' | 'outline'> = {
  incomplete: 'muted',
  trial: 'outline',
  active: 'default',
  past_due: 'outline',
  grace: 'outline',
  canceled: 'destructive',
  expired: 'destructive',
};
