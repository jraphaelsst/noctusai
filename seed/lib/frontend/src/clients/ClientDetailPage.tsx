/**
 * `<ClientDetailPage/>` -- one client: header (status, tags, next session, sessions done, open amount) and the tabs
 * Sessões · Agenda fixa · Financeiro · Dados. Router-agnostic: the host passes the id and its navigation callbacks.
 * Delete is admin-only (the server enforces it); a client with booked receivables cannot be deleted
 * (409 `CLIENTE_COM_FINANCEIRO`) -- the page offers to close it (the "encerrado" status) instead.
 */
import { ArrowLeft, Trash2 } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

import { useConfirm } from '../components/confirm/ConfirmProvider';
import { Button } from '../design-system/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../design-system/ui/tabs';
import { formatCents } from '../organ-kit/money';
import { apiErrorStatus } from '../organ-kit/query';
import { ClientFinanceTab } from './ClientFinanceTab';
import { ClientForm } from './ClientForm';
import { ClientSchedulesTab } from './ClientSchedulesTab';
import { ClientSessionsTab } from './ClientSessionsTab';
import { ErrorState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { displayPhone } from '../leads/format';
import { formatWhen, optionOf, tzOf } from './format';
import { apiErrorCode, errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, nounVars, StatTile, TagChips, ToneBadge } from './parts';
import type { Client, ClientsConfigData } from './types';

export type ClientDetailTab = 'sessoes' | 'agenda' | 'financeiro' | 'dados';

export interface ClientDetailPageProps {
  hooks: ClientsHooks;
  clientId: string;
  /** UX gate for delete + payments (the server enforces both). */
  isAdmin?: boolean;
  onBack?: () => void;
  /** After a delete (host navigates away). */
  onDeleted?: () => void;
  /** Controlled tab (e.g. from the URL); local state when omitted. */
  tab?: ClientDetailTab;
  onTabChange?: (tab: ClientDetailTab) => void;
}

/** The status a client is CLOSED with: `encerrado` when configured, else the last configured status. */
function closedStatus(config: ClientsConfigData | undefined) {
  return config?.statuses.find((s) => s.slug === 'encerrado') ?? config?.statuses[config.statuses.length - 1];
}

function DataTab({ hooks, client, isAdmin, onDeleted }: { hooks: ClientsHooks; client: Client; isAdmin: boolean; onDeleted?: () => void }) {
  const confirm = useConfirm();
  const { data: config } = hooks.useClientsConfig();
  const del = hooks.useDeleteClient();
  const update = hooks.useUpdateClient();
  const vars = nounVars(config);
  const [error, setError] = React.useState<string | null>(null);
  const [blocked, setBlocked] = React.useState(false);
  const closed = closedStatus(config);

  const remove = async () => {
    const ok = await confirm({ title: t('data.delete_title', vars), description: t('data.delete_body'), confirmLabel: t('common.delete'), tone: 'danger' });
    if (!ok) return;
    setError(null);
    setBlocked(false);
    del.mutate(client.id, {
      onSuccess: () => onDeleted?.(),
      onError: (err) => {
        setBlocked(apiErrorCode(err)?.toUpperCase() === 'CLIENTE_COM_FINANCEIRO');
        setError(clientsErrorText(err, 'data.delete_error', vars));
      },
    });
  };

  const closeInstead = () => {
    if (!closed) return;
    update.mutate(
      { id: client.id, status: closed.slug },
      { onSuccess: () => { setBlocked(false); setError(null); }, onError: (err) => setError(clientsErrorText(err, 'form.error', vars)) },
    );
  };

  return (
    <div className="space-y-4" data-testid="client-data">
      <div className="rounded-md border">
        <ClientForm key={client.updated_at} hooks={hooks} client={client} isAdmin={isAdmin} onSaved={() => toast.success(t('data.saved'))} />
      </div>
      {isAdmin && (
        <div className="space-y-2">
          <FormError message={error} />
          <div className="flex flex-wrap gap-2">
            {blocked && closed && client.status !== closed.slug && (
              <Button variant="outline" onClick={closeInstead} disabled={update.isPending} data-testid="client-close-instead">
                {t('data.close_instead', { status: closed.label })}
              </Button>
            )}
            <Button variant="destructive" onClick={() => void remove()} disabled={del.isPending} data-testid="client-delete">
              <Trash2 className="mr-1 h-4 w-4" />
              {t('data.delete', vars)}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ClientDetailPage({ hooks, clientId, isAdmin = false, onBack, onDeleted, tab: controlled, onTabChange }: ClientDetailPageProps) {
  const { data: config } = hooks.useClientsConfig();
  const q = hooks.useClient(clientId);
  const [local, setLocal] = React.useState<ClientDetailTab>('sessoes');
  const tab = controlled ?? local;
  const setTab = (next: string) => {
    if (controlled === undefined) setLocal(next as ClientDetailTab);
    onTabChange?.(next as ClientDetailTab);
  };
  const vars = nounVars(config);
  const tz = tzOf(config);
  const client = q.data;

  const back = onBack ? (
    <Button variant="ghost" size="sm" onClick={onBack} data-testid="client-back">
      <ArrowLeft className="mr-1 h-4 w-4" />
      {t('detail.back', vars)}
    </Button>
  ) : null;

  if (q.showSkeleton) {
    return (
      <div className="space-y-3" data-testid="client-detail">
        {back}
        <ListSkeleton rows={5} />
      </div>
    );
  }
  if (!client) {
    const notFound = apiErrorStatus(q.error) === 404;
    return (
      <div className="space-y-3" data-testid="client-detail">
        {back}
        {notFound ? (
          <ErrorState message={t('detail.not_found', vars)} />
        ) : (
          <RetryError message={`${t('detail.error', vars)} ${errorMessage(q.error)}`} onRetry={() => void q.refetch()} retryLabel={t('common.retry')} />
        )}
      </div>
    );
  }

  const status = optionOf(config?.statuses, client.status);
  const s = client.summary;

  return (
    <div className="space-y-4" data-testid="client-detail">
      {back}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-foreground">{client.name}</h1>
          <ToneBadge color={status.color} testId="client-status">
            {status.label}
          </ToneBadge>
          <TagChips tags={client.tags} testId="client-tags" />
        </div>
        <p className="text-sm text-muted-foreground">{[displayPhone(client.phone), client.email].filter(Boolean).join(' · ')}</p>
        <RefreshingBar active={q.isRefreshing} label={t('common.refreshing')} />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label={t('detail.next')} value={formatWhen(s.next_session_at, tz) || '—'} testId="client-next" />
        <StatTile label={t('detail.done')} value={s.sessions_done} testId="client-done" />
        <StatTile label={t('detail.open')} value={formatCents(s.open_cents)} tone={s.overdue_cents > 0 ? 'destructive' : undefined} testId="client-open" />
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList aria-label={client.name}>
          <TabsTrigger value="sessoes" data-testid="client-tab-sessoes">{t('detail.tab_sessions')}</TabsTrigger>
          <TabsTrigger value="agenda" data-testid="client-tab-agenda">{t('detail.tab_schedules')}</TabsTrigger>
          <TabsTrigger value="financeiro" data-testid="client-tab-financeiro">{t('detail.tab_finance')}</TabsTrigger>
          <TabsTrigger value="dados" data-testid="client-tab-dados">{t('detail.tab_data')}</TabsTrigger>
        </TabsList>
        <TabsContent value="sessoes" className="pt-3">
          <ClientSessionsTab hooks={hooks} client={client} />
        </TabsContent>
        <TabsContent value="agenda" className="pt-3">
          <ClientSchedulesTab hooks={hooks} client={client} />
        </TabsContent>
        <TabsContent value="financeiro" className="pt-3">
          <ClientFinanceTab hooks={hooks} client={client} isAdmin={isAdmin} />
        </TabsContent>
        <TabsContent value="dados" className="pt-3">
          <DataTab hooks={hooks} client={client} isAdmin={isAdmin} onDeleted={onDeleted} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
