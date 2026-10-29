/**
 * Sessions tab of the client page: upcoming (soonest first) and past (latest first). Each row: when, duration, a
 * quick status switch in the status colour, the payment chip; a row opens the edit dialog. "Nova sessão" creates one.
 */
import { Plus } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

import { stageTagClasses } from '../components/pipeline/stageTokens';
import { Button } from '../design-system/ui/Button';
import { cn } from '../utils';
import { formatCents } from '../organ-kit/money';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { formatWhen, optionOf, PAYMENT_STATUS, tzOf } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, ToneBadge } from './parts';
import { SessionFormDialog } from './SessionFormDialog';
import type { Client, ClientsConfigData, Session } from './types';

export interface SessionRowProps {
  session: Session;
  config: ClientsConfigData | undefined;
  onOpen: (s: Session) => void;
  onStatus: (s: Session, status: string) => void;
  busy?: boolean;
}

/** One session line (shared by the client page). */
export function SessionRow({ session: s, config, onOpen, onStatus, busy }: SessionRowProps) {
  const tz = tzOf(config);
  const status = optionOf(config?.session_statuses, s.status);
  const pay = PAYMENT_STATUS[s.payment_status] ?? PAYMENT_STATUS.none;
  return (
    <li className="flex flex-wrap items-center gap-2 border-t px-3 py-2 first:border-t-0" data-testid={`session-row-${s.id}`}>
      <button type="button" className="min-w-0 flex-1 text-left hover:underline" onClick={() => onOpen(s)}>
        <span className="font-medium">{formatWhen(s.starts_at, tz)}</span>
        <span className="ml-2 text-xs text-muted-foreground">{t('sessions.minutes', { n: s.duration_min })}</span>
        {s.price_cents != null && !s.waive_charge && <span className="ml-2 text-xs text-muted-foreground">{formatCents(s.price_cents)}</span>}
        {s.notes && <span className="ml-2 truncate text-xs text-muted-foreground">· {s.notes}</span>}
      </button>
      <select
        aria-label={t('sessions.status_label')}
        className={cn('rounded-full border px-2 py-0.5 text-xs font-semibold', stageTagClasses(status.color))}
        value={s.status}
        disabled={busy}
        onChange={(e) => onStatus(s, e.target.value)}
        data-testid={`session-status-${s.id}`}
      >
        {(config?.session_statuses ?? [status]).map((o) => (
          <option key={o.slug} value={o.slug}>
            {o.label}
          </option>
        ))}
      </select>
      {s.waive_charge ? (
        <ToneBadge color="muted">{t('sessions.waived')}</ToneBadge>
      ) : s.payment_status !== 'none' ? (
        <ToneBadge color={pay.color} testId={`session-pay-${s.id}`}>
          {pay.label}
        </ToneBadge>
      ) : null}
    </li>
  );
}

export interface ClientSessionsTabProps {
  hooks: ClientsHooks;
  client: Client;
  /** Injectable clock for tests. */
  now?: number;
}

export function ClientSessionsTab({ hooks, client, now }: ClientSessionsTabProps) {
  const { data: config } = hooks.useClientsConfig();
  const sessions = hooks.useClientSessions(client.id);
  const update = hooks.useUpdateSession();
  const [editing, setEditing] = React.useState<Session | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const cut = new Date(now ?? Date.now()).toISOString();
  const all = sessions.data ?? [];
  const upcoming = all.filter((s) => new Date(s.starts_at).toISOString() >= cut).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const past = all.filter((s) => new Date(s.starts_at).toISOString() < cut);

  const changeStatus = (s: Session, status: string) => {
    setBusyId(s.id);
    update.mutate(
      { id: s.id, client_id: s.client_id, status },
      {
        onError: (err) => toast.error(t('sessions.status_error'), { description: clientsErrorText(err, 'sessions.status_error') }),
        onSettled: () => setBusyId(null),
      },
    );
  };

  const section = (title: string, rows: Session[], empty: string, testId: string) => (
    <section className="space-y-2" data-testid={testId}>
      <h3 className="text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <EmptyState message={empty} />
      ) : (
        <ul className="rounded-md border text-sm">
          {rows.map((s) => (
            <SessionRow key={s.id} session={s} config={config} onOpen={setEditing} onStatus={changeStatus} busy={busyId === s.id} />
          ))}
        </ul>
      )}
    </section>
  );

  return (
    <div className="space-y-4" data-testid="client-sessions">
      <div className="flex justify-end">
        <Button onClick={() => setCreating(true)} data-testid="sessions-new">
          <Plus className="mr-1 h-4 w-4" />
          {t('sessions.new')}
        </Button>
      </div>
      <RefreshingBar active={sessions.isRefreshing} label={t('common.refreshing')} />
      {sessions.showSkeleton ? (
        <ListSkeleton />
      ) : sessions.isError && !sessions.data ? (
        <RetryError message={`${t('sessions.error')} ${errorMessage(sessions.error)}`} onRetry={() => void sessions.refetch()} retryLabel={t('common.retry')} />
      ) : (
        <>
          {section(t('sessions.upcoming'), upcoming, t('sessions.empty_upcoming'), 'sessions-upcoming')}
          {section(t('sessions.past'), past, t('sessions.empty_past'), 'sessions-past')}
        </>
      )}
      <SessionFormDialog
        hooks={hooks}
        open={creating || !!editing}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        clientId={client.id}
        client={client}
        session={editing}
      />
    </div>
  );
}
