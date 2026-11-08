/**
 * Platform-admin half of the billing client (`/api/admin/billing/*`). Lives with the admin bundle:
 * the public build never carries these paths. The context value the admin surface provides is
 * `{ ...createBillingApi(api), ...createBillingAdminApi(api) }` (see `admin/AdminApis.tsx`).
 */
import type {
  AdminSubscription, BillingCycle, BillingPayment, BillingPlan, BillingSettings, BillingSummary, Gateway,
  GatewayMode, HttpClient, Page, PlanPrice, SecretField,
} from './billing';

export function createBillingAdminApi(http: HttpClient) {
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
  };
}

export type BillingAdminApi = ReturnType<typeof createBillingAdminApi>;
