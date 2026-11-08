/**
 * Hands the admin pages the FULL billing + credits clients: the public half every page already has,
 * plus the platform-admin half (`*.admin.ts`) that is only ever bundled with the platform admin surface.
 */
import type { ReactNode } from 'react';
import { api } from '../lib/api';
import { BillingApiProvider, createBillingApi } from '../lib/billing';
import { createBillingAdminApi } from '../lib/billing.admin';
import { CreditsApiProvider, createCreditsApi } from '../lib/credits';
import { createCreditsAdminApi } from '../lib/credits.admin';

const billing = { ...createBillingApi(api), ...createBillingAdminApi(api) };
const credits = { ...createCreditsApi(api), ...createCreditsAdminApi(api) };

export function AdminApis({ children }: { children: ReactNode }) {
  return (
    <BillingApiProvider value={billing}>
      <CreditsApiProvider value={credits}>{children}</CreditsApiProvider>
    </BillingApiProvider>
  );
}
