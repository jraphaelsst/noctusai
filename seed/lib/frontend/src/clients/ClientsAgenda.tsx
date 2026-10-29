/**
 * `<ClientsAgenda/>` -- the week across every client (`GET /api/clients/sessions?from&to`), Monday to Sunday in the
 * org's zone. Previous / next week, "Hoje"; each session is a chip in its status colour (time + client); a chip opens
 * the session (edit, quick delete, "abrir <noun>"). The previous week stays on screen while the next one loads.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react';
import * as React from 'react';

import { stageTagClasses } from '../components/pipeline/stageTokens';
import { Button } from '../design-system/ui/Button';
import { cn } from '../utils';
import { ListSkeleton, RefreshingBar, RetryError } from './controls';
import { addDays, formatDay, formatDayShort, optionOf, todayIn, tzOf, WEEKDAYS_SHORT, weekStartOf, zonedParts } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { SessionFormDialog } from './SessionFormDialog';
import type { Session } from './types';

export interface ClientsAgendaProps {
  hooks: ClientsHooks;
  /** Host navigation to a client's page. */
  onOpenClient?: (clientId: string) => void;
  /** Injectable clock for tests. */
  now?: number;
}

export function ClientsAgenda({ hooks, onOpenClient, now }: ClientsAgendaProps) {
  const { data: config } = hooks.useClientsConfig();
  const tz = tzOf(config);
  const today = todayIn(tz, now);
  const [start, setStart] = React.useState(() => weekStartOf(today));
  const end = addDays(start, 6);
  const week = hooks.useAgendaSessions(start, end);
  const [open, setOpen] = React.useState<Session | null>(null);

  const days = React.useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(start, i)), [start]);
  const byDay = React.useMemo(() => {
    const map = new Map<string, { s: Session; time: string }[]>();
    for (const s of week.data ?? []) {
      const p = zonedParts(s.starts_at, tz);
      if (!p) continue;
      const list = map.get(p.date) ?? [];
      list.push({ s, time: p.time });
      map.set(p.date, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.time.localeCompare(b.time));
    return map;
  }, [week.data, tz]);

  return (
    <div className="space-y-3" data-testid="clients-agenda">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setStart(addDays(start, -7))} aria-label={t('agenda.prev')} data-testid="agenda-prev">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => setStart(weekStartOf(today))} data-testid="agenda-today">
          {t('agenda.today')}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setStart(addDays(start, 7))} aria-label={t('agenda.next')} data-testid="agenda-next">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <span className="text-sm font-medium" data-testid="agenda-range">
          {t('agenda.week', { from: formatDay(start), to: formatDay(end) })}
        </span>
        <RefreshingBar active={week.isRefreshing} label={t('common.refreshing')} />
      </div>
      {week.showSkeleton ? (
        <ListSkeleton rows={5} />
      ) : week.isError && !week.data ? (
        <RetryError message={`${t('agenda.error')} ${errorMessage(week.error)}`} onRetry={() => void week.refetch()} retryLabel={t('common.retry')} />
      ) : (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-7">
          {days.map((day, i) => {
            const items = byDay.get(day) ?? [];
            return (
              <div key={day} className={cn('min-h-[6rem] rounded-md border p-2', day === today && 'border-primary')} data-testid={`agenda-day-${day}`}>
                <p className={cn('mb-2 text-xs font-semibold uppercase', day === today ? 'text-primary' : 'text-muted-foreground')}>
                  {WEEKDAYS_SHORT[i]} {formatDayShort(day)}
                </p>
                {/* a stale week kept after a failed refetch never reads as "free" */}
                {!week.isError && items.length === 0 ? (
                  <p className="text-xs text-muted-foreground">{t('agenda.empty_day')}</p>
                ) : (
                  <ul className="space-y-1">
                    {items.map(({ s, time }) => {
                      const st = optionOf(config?.session_statuses, s.status);
                      return (
                        <li key={s.id}>
                          <button
                            type="button"
                            onClick={() => setOpen(s)}
                            title={`${st.label} · ${s.client_name}`}
                            className={cn('w-full truncate rounded border px-1.5 py-1 text-left text-xs', stageTagClasses(st.color))}
                            data-testid={`agenda-session-${s.id}`}
                          >
                            <span className="font-semibold">{time}</span> {s.client_name}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
      <SessionFormDialog
        hooks={hooks}
        open={!!open}
        onClose={() => setOpen(null)}
        clientId={open?.client_id ?? ''}
        session={open}
        onOpenClient={
          onOpenClient
            ? (id) => {
                setOpen(null);
                onOpenClient(id);
              }
            : undefined
        }
      />
    </div>
  );
}
