/**
 * Platform-admin half of the credits client (`/api/admin/credits/*`). Lives with the admin bundle: the
 * public build never carries these paths. See `admin/AdminApis.tsx` for how the full value is provided.
 */
import type { HttpClient } from './billing';
import type {
  AdminWalletRow, GrantInput, MarginReport, PricingInput, PricingVersion, WalletMode, WalletView,
} from './credits';

export function createCreditsAdminApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  const qs = (params: Record<string, string | undefined>) => {
    const s = new URLSearchParams(Object.entries(params).filter(([, v]) => !!v) as [string, string][]).toString();
    return s ? `?${s}` : '';
  };
  return {
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

export type CreditsAdminApi = ReturnType<typeof createCreditsAdminApi>;
