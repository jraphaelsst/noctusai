/** The NoctusAI funnel's data hooks -- the seed organ's `createFunnelHooks` bound to core's `api` and prefix. */
import { createFunnelHooks, type FunnelCard } from '@noctusai/lib/components';
import { api } from '../../../lib/api';

export const FUNNEL_PREFIX = '/api/admin/funnel';

export type NocCard = FunnelCard;

export const nocFunnelHooks = createFunnelHooks<NocCard>(
  {
    queryKey: 'noc-funil',
    prefix: FUNNEL_PREFIX,
    entityLabel: 'contato',
    // The seed stage editor ("Configurar etapas"): stages are editable (owner decision 2026-11-07).
    stagesEndpoint: `${FUNNEL_PREFIX}/etapas`,
  },
  api,
);
