/**
 * AI credits (core `/api/credits/*` + `/api/admin/credits/*`, migration 093) — typed client + hooks.
 *
 * The HTTP client arrives through `CreditsApiContext` (default: the app's `api`), so page tests
 * inject a fake client instead of mocking modules. Org reads are keyed by the EFFECTIVE org
 * (org picker, no reload) and carry no placeholderData: a fresh org shows a skeleton, never the
 * previous org's balance. Writes follow noc-cache-writes: the server's answer (the new wallet /
 * the updated pricing list) is committed into the cache the moment it arrives; a grant/adjustment
 * also refreshes the derived views in the background.
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import { useEffectiveSSOContext } from '@noctusai/lib/design-system';
import { api } from './api';
import type { HttpClient } from './billing';

export type WalletMode = 'prepaid' | 'postpaid_trusted' | 'byok';

export interface WalletView {
  exists: boolean;
  mode: WalletMode | null;
  balance_credits: number;
  balance_brl: number;
  overdraft_limit_credits: number;
  alert_thresholds: number[];
  alert_base_credits?: number;
  consumed_pct: number;
  credit_unit_brl: number;
  blocked: boolean;
  charge_from?: string | null;
  updated_at?: string | null;
}

export interface CreditEntry {
  id: number;
  created_at: string;
  product?: string | null;
  feature?: string | null;
  kind: 'purchase' | 'grant' | 'adjustment' | 'usage_debit' | 'refund';
  source: string;
  credits: number;
  balance_after: number;
  brl_amount?: number | null;
  reason?: string | null;
}

export interface CreditPurchase {
  id: string;
  credits: number;
  amount_cents: number;
  gateway: 'asaas' | 'stripe';
  billing_method: string;
  status: 'pending' | 'paid' | 'failed' | 'canceled' | 'refunded';
  checkout_url?: string | null;
  created_at: string;
  paid_at?: string | null;
}

export interface MyWallet {
  wallet: WalletView;
  entries: CreditEntry[];
  purchases: CreditPurchase[];
  gateways: Array<'asaas' | 'stripe'>;
}

export interface UsageBucket {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  tokens: number;
  credits: number;
  brl: number;
  pending_calls: number;
}

export interface UsageReport {
  window: { from: string; to: string };
  credit_unit_brl: number;
  totals: UsageBucket;
  per_product: Array<UsageBucket & { product: string; per_feature: Array<UsageBucket & { feature: string }> }>;
  daily: Array<Record<string, number | string> & { day: string }>;
  products: string[];
}

export interface PurchaseResult {
  purchase_id: string;
  credits: number;
  amount_cents: number;
  checkout_url: string | null;
  gateway: string;
  pix_qr: { payload: string; encoded_image: string; expiration_date?: string | null } | null;
}

export interface AdminWalletRow extends WalletView {
  org_id: string;
  org_nome?: string | null;
  org_slug?: string | null;
}

export interface PricingVersion {
  version: number;
  credit_unit_brl: number;
  margin: number;
  fx_buffer_brl: number;
  iof_rate: number;
  import_tax_rate: number;
  simples_rate: number;
  gateway_fee_rate: number;
  effective_from?: string | null;
  notes?: string | null;
  gross_margin: number;
  created_at?: string | null;
}

export interface MarginRow {
  revenue_brl: number;
  provider_cost_brl: number;
  gross_margin_brl: number;
  gross_margin_pct: number | null;
  debited_credits: number;
  byok_calls: number;
}

export interface MarginReport {
  window: { from: string; to: string };
  totals: { revenue_brl: number; provider_cost_brl: number; purchased_brl: number; granted_brl: number;
    gross_margin_brl: number; gross_margin_pct: number | null };
  per_org: Array<MarginRow & { org_id: string; purchased_brl: number; granted_brl: number; refunded_brl: number;
    per_product: Array<MarginRow & { product: string }> }>;
}

export interface GrantInput { orgId: string; credits?: string; usd?: string; reason: string }
export interface PricingInput {
  credit_unit_brl: string; margin: string; fx_buffer_brl: string; iof_rate: string;
  import_tax_rate: string; simples_rate: string; gateway_fee_rate: string; notes?: string;
}

export function createCreditsApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  const qs = (params: Record<string, string | undefined>) => {
    const s = new URLSearchParams(Object.entries(params).filter(([, v]) => !!v) as [string, string][]).toString();
    return s ? `?${s}` : '';
  };
  return {
    wallet: () => unwrap<MyWallet>(http.get('/api/credits/wallet')),
    usage: (from?: string, to?: string) => unwrap<UsageReport>(http.get(`/api/credits/usage${qs({ from, to })}`)),
    purchase: (body: { amount_brl: string; gateway: 'asaas' | 'stripe'; billing_method: string; tax_id?: string }) =>
      unwrap<PurchaseResult>(http.post('/api/credits/purchase', body)),
    adminWallets: () => unwrap<AdminWalletRow[]>(http.get('/api/admin/credits/wallets')),
    grant: ({ orgId, ...body }: GrantInput) =>
      unwrap<{ status: string; credits: number; balance_credits: number | null }>(
        http.post(`/api/admin/credits/${orgId}/grant`, {
          reason: body.reason, ...(body.usd ? { usd: body.usd } : { credits: body.credits }),
        })),
    adjust: (orgId: string, credits: string, reason: string) =>
      unwrap<{ status: string; balance_credits: number | null }>(
        http.post(`/api/admin/credits/${orgId}/adjustments`, { credits, reason })),
    setWallet: (orgId: string, body: { mode?: WalletMode; overdraft_limit_credits?: string }) =>
      unwrap<WalletView>(http.put(`/api/admin/credits/${orgId}/wallet`, body)),
    pricing: () => unwrap<PricingVersion[]>(http.get('/api/admin/credits/pricing')),
    createPricing: (body: PricingInput) => unwrap<PricingVersion[]>(http.post('/api/admin/credits/pricing', body)),
    margin: (from?: string, to?: string) => unwrap<MarginReport>(http.get(`/api/admin/credits/margin${qs({ from, to })}`)),
  };
}

export type CreditsApi = ReturnType<typeof createCreditsApi>;

const CreditsApiContext = createContext<CreditsApi>(createCreditsApi(api));

export function CreditsApiProvider({ value, children }: { value: CreditsApi; children: ReactNode }) {
  return createElement(CreditsApiContext.Provider, { value }, children);
}

export function useCreditsApi(): CreditsApi {
  return useContext(CreditsApiContext);
}

export const creditKeys = {
  wallet: (orgId: string) => ['core-credits', orgId, 'wallet'] as const,
  usage: (orgId: string, from: string, to: string) => ['core-credits', orgId, 'usage', from, to] as const,
  usagePrefix: (orgId: string) => ['core-credits', orgId, 'usage'] as const,
  adminWallets: ['core-credits-admin', 'wallets'] as const,
  pricing: ['core-credits-admin', 'pricing'] as const,
  margin: (from: string, to: string) => ['core-credits-admin', 'margin', from, to] as const,
  marginPrefix: ['core-credits-admin', 'margin'] as const,
};

function useOrgId(): string {
  return useEffectiveSSOContext().orgId ?? '';
}

// ── org ─────────────────────────────────────────────────────────────────

export function useMyWallet() {
  const c = useCreditsApi();
  const orgId = useOrgId();
  return useQuery({ queryKey: creditKeys.wallet(orgId), queryFn: c.wallet, enabled: !!orgId, retry: false });
}

export function useMyUsage(from: string, to: string) {
  const c = useCreditsApi();
  const orgId = useOrgId();
  return useQuery({
    queryKey: creditKeys.usage(orgId, from, to),
    queryFn: () => c.usage(from, to),
    enabled: !!orgId,
    retry: false,
  });
}

/** Opens a charge; nothing is credited until the gateway's paid webhook — the purchase row
 * (status `pending`) joins the wallet's list now, the balance moves when the payment lands. */
export function useBuyCredits() {
  const c = useCreditsApi();
  const orgId = useOrgId();
  return useCacheWriteMutation<PurchaseResult, Parameters<CreditsApi['purchase']>[0]>({
    mutationFn: (body) => c.purchase(body),
    targets: (vars) => [
      {
        queryKey: creditKeys.wallet(orgId),
        commit: (old: MyWallet | undefined, res) =>
          old
            ? {
                ...old,
                purchases: [
                  {
                    id: res.purchase_id, credits: res.credits, amount_cents: res.amount_cents,
                    gateway: vars.gateway, billing_method: vars.billing_method, status: 'pending' as const,
                    checkout_url: res.checkout_url, created_at: new Date().toISOString(),
                  },
                  ...old.purchases,
                ],
              }
            : old,
      },
    ],
  });
}

// ── admin ───────────────────────────────────────────────────────────────

export function useAdminWallets() {
  const c = useCreditsApi();
  return useQuery({ queryKey: creditKeys.adminWallets, queryFn: c.adminWallets });
}

export function usePricingVersions() {
  const c = useCreditsApi();
  return useQuery({ queryKey: creditKeys.pricing, queryFn: c.pricing });
}

export function useMarginReport(from: string, to: string) {
  const c = useCreditsApi();
  return useQuery({ queryKey: creditKeys.margin(from, to), queryFn: () => c.margin(from, to) });
}

const setBalance = (orgId: string, balance: number | null) => (old: AdminWalletRow[] | undefined) => {
  if (!old || balance == null) return old;
  const unit = old.find((r) => r.org_id === orgId)?.credit_unit_brl ?? old[0]?.credit_unit_brl ?? 0.01;
  return old.some((r) => r.org_id === orgId)
    ? old.map((r) => (r.org_id === orgId
      ? { ...r, exists: true, balance_credits: balance, balance_brl: Math.round(balance * unit * 100) / 100,
        blocked: r.mode === 'prepaid' && balance <= -r.overdraft_limit_credits }
      : r))
    : old; // a first grant creates the wallet: settle reads the new row (org name, mode)
};

export function useGrantCredits() {
  const c = useCreditsApi();
  return useCacheWriteMutation<Awaited<ReturnType<CreditsApi['grant']>>, GrantInput>({
    mutationFn: (vars) => c.grant(vars),
    targets: (vars) => [
      { queryKey: creditKeys.adminWallets, commit: (old: AdminWalletRow[] | undefined, res) => setBalance(vars.orgId, res.balance_credits)(old) },
    ],
    invalidate: [creditKeys.marginPrefix],
  });
}

export function useAdjustCredits() {
  const c = useCreditsApi();
  return useCacheWriteMutation<Awaited<ReturnType<CreditsApi['adjust']>>, { orgId: string; credits: string; reason: string }>({
    mutationFn: (v) => c.adjust(v.orgId, v.credits, v.reason),
    targets: (vars) => [
      { queryKey: creditKeys.adminWallets, commit: (old: AdminWalletRow[] | undefined, res) => setBalance(vars.orgId, res.balance_credits)(old) },
    ],
  });
}

export function useSetWalletMode() {
  const c = useCreditsApi();
  return useCacheWriteMutation<WalletView, { orgId: string; mode: WalletMode }>({
    mutationFn: (v) => c.setWallet(v.orgId, { mode: v.mode }),
    targets: (vars) => [
      {
        queryKey: creditKeys.adminWallets,
        optimistic: (old: AdminWalletRow[] | undefined) =>
          old?.map((r) => (r.org_id === vars.orgId ? { ...r, mode: vars.mode } : r)),
        commit: (old: AdminWalletRow[] | undefined, saved) =>
          old?.map((r) => (r.org_id === vars.orgId ? { ...r, ...saved } : r)),
      },
    ],
  });
}

export function useCreatePricing() {
  const c = useCreditsApi();
  return useCacheWriteMutation<PricingVersion[], PricingInput>({
    mutationFn: (body) => c.createPricing(body),
    targets: [{ queryKey: creditKeys.pricing, commit: (_old: PricingVersion[] | undefined, list) => list }],
  });
}

// ── formatting ──────────────────────────────────────────────────────────

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const NUM = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });

export const formatBrl = (v: number | null | undefined) => (v == null ? '—' : BRL.format(v));
export const formatCredits = (v: number | null | undefined) => (v == null ? '—' : NUM.format(v));
export const formatTokens = (v: number) => NUM.format(v);
export const formatPct = (v: number | null | undefined) => (v == null ? '—' : `${NUM.format(v * 100)}%`);

export const MODE_LABEL: Record<WalletMode, string> = {
  prepaid: 'Pré-pago',
  postpaid_trusted: 'Pós-pago (confiável)',
  byok: 'Chave própria (BYOK)',
};

export const KIND_LABEL: Record<CreditEntry['kind'], string> = {
  purchase: 'Compra',
  grant: 'Concessão',
  adjustment: 'Ajuste',
  usage_debit: 'Uso',
  refund: 'Estorno',
};
