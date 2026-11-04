/**
 * NotificationBell — framework-delegated shim.
 *
 * Rewritten in `projects/core-seed-wiring-v2/` Phase 3 (2026-04-23) from a
 * 186-LOC full reimplementation to a ~20-LOC shim on the shared component.
 * Identical pattern to ERP's NotificationBell — imports the design-system
 * component from `@noctusai/lib/design-system` and wires product-local
 * hooks that target the framework's `/api/notificacoes` endpoints.
 *
 * Core's frontend consumers (`Layout.tsx`, `Dashboard.tsx`, `Pricing.tsx`,
 * `TeamManagement.tsx`, `BillingSettings.tsx`) continue to import
 * `NotificationBell` from this file with no prop changes.
 */
// @consumes-organ NotificationBell@1.0 +seam=hooks-binding
import { NotificationBell as SharedNotificationBell } from '@noctusai/lib/design-system';
import { createNotificationHooks } from '@noctusai/lib/notifications';
import { createOpenInProduct, env } from '@noctusai/lib';
import { useNavigate } from 'react-router-dom';

import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';

// `createNotificationHooks` expects `useAuthStore: () => { user }`. Core's
// `useAuth` returns a richer shape; we adapt to the minimal required surface.
const useAuthStore = () => {
  const { user } = useAuth();
  return { user };
};

/** ONE hooks object: the header bell and the shell's live pop-ups (main.tsx) share the same query cache. */
export const notificationHooks = createNotificationHooks(api, useAuthStore);

/** Open a notice's link in another product: core mints the SSO launch URL (licence + known-product check). */
export const openInProduct = createOpenInProduct(async (product) => {
  const res = await api.post('/api/sso/token', { product_slug: product });
  return res.redirect_url as string;
});

export function NotificationBell() {
  const navigate = useNavigate();
  return (
    <SharedNotificationBell
      hooks={notificationHooks}
      onNavigate={(link) => navigate(link)}
      currentProduct={env.PRODUCT_SLUG}
      onNavigateProduct={openInProduct}
    />
  );
}
