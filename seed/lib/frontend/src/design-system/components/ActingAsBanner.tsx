/**
 * `<ActingAsBanner/>` — persistent top bar shown while the platform
 * superadmin is inside a product AS a customer org (Round 2 act-as-org).
 *
 *   "Você está acessando como **{org_nome}**"  [Sair]
 *
 * Reads `GET /api/me/context` (product API, license-gated like any route) and
 * renders NOTHING when `acting` is null — a customer never sees it. "Sair"
 * calls `DELETE {core}/api/admin/act-as/current` with the Supabase bearer
 * (`coreApi`) and then hard-navigates to core's admin "Organizações" page.
 *
 * Mounted once by the seed shell layout (`createProductLayout`) — products
 * ship zero code for it. `ActingAsBannerView` is the pure presentational half.
 */
import { useMutation, useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { api, coreApi } from '@noctusai/seed/infra';

import type { ActingInfo, MeContext } from '../../access';
import { env } from '../../env';

export const ME_CONTEXT_QUERY_KEY = ['me', 'context'] as const;

export interface ActingAsBannerViewProps {
  orgNome: string;
  onExit: () => void;
  exiting?: boolean;
}

export function ActingAsBannerView({ orgNome, onExit, exiting = false }: ActingAsBannerViewProps) {
  return (
    <div
      role="status"
      data-testid="acting-as-banner"
      className="sticky top-0 z-40 flex items-center justify-center gap-3 border-b border-amber-500/40 bg-amber-500/15 px-4 py-2 text-sm text-amber-900 dark:text-amber-200"
    >
      <span>
        Você está acessando como <strong>{orgNome}</strong>
      </span>
      <button
        type="button"
        onClick={onExit}
        disabled={exiting}
        className="inline-flex items-center gap-1 rounded-md border border-amber-600/50 bg-background px-3 py-1 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50"
      >
        {exiting && <Loader2 className="h-3 w-3 animate-spin" />}
        Sair
      </button>
    </div>
  );
}

/** Where "Sair" lands: core's admin Organizações page. */
export function coreOrganizacoesUrl(): string {
  return `${env.CORE_URL.replace(/\/$/, '')}/admin/organizacoes`;
}

export function ActingAsBanner() {
  // `data` drives visibility (never `isLoading`): no banner until context
  // answers, and a background refetch never flickers it away.
  const { data } = useQuery<MeContext>({
    queryKey: ME_CONTEXT_QUERY_KEY,
    queryFn: () => api.get<MeContext>('/api/me/context'),
    staleTime: 60_000,
    retry: false,
  });

  const exit = useMutation({
    mutationFn: () => coreApi.delete<{ ended: boolean }>('/api/admin/act-as/current'),
    onSuccess: () => {
      window.location.assign(coreOrganizacoesUrl());
    },
    onError: (err) => {
      toast.error('Não foi possível sair da organização', {
        description: err instanceof Error ? err.message : undefined,
      });
    },
  });

  const acting: ActingInfo | null | undefined = data?.acting;
  if (!acting) return null;
  return (
    <ActingAsBannerView
      orgNome={acting.org_nome}
      onExit={() => exit.mutate()}
      exiting={exit.isPending}
    />
  );
}
