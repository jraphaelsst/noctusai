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
import { NotificationBell as SharedNotificationBell } from '@noctusai/lib/design-system';
import { createNotificationHooks } from '@noctusai/lib/notifications';
import { useNavigate } from 'react-router-dom';

import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';

// `createNotificationHooks` expects `useAuthStore: () => { user }`. Core's
// `useAuth` returns a richer shape; we adapt to the minimal required surface.
const useAuthStore = () => {
  const { user } = useAuth();
  return { user };
};

const hooks = createNotificationHooks(api, useAuthStore);

export function NotificationBell() {
  const navigate = useNavigate();
  return (
    <SharedNotificationBell
      hooks={hooks}
      onViewAll={() => navigate('/notifications')}
    />
  );
}
