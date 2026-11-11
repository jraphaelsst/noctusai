/**
 * `<MyTasksPage/>` — the caller's own activities across every entity (open / overdue / done), paged.
 *
 * The page a module mounts under `ACTIVITIES_PAGES.myTasks` (`crm_atividades`). What each task is ABOUT is the host's
 * business: pass `entityHref(kind, id)` to link it (omitted => no link).
 */
import * as React from 'react';
import { Button, EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { ActivityRow } from './ActivityRow';
import { activitiesErrorMessage, errorMessage } from './hooks';
import { defaultActivitiesT } from './i18n';
import type { ActivitiesOrganProps } from './shared';
import type { Activity, ActivityListParams } from './types';

type Tab = 'open' | 'overdue' | 'done';
const TABS: readonly Tab[] = ['open', 'overdue', 'done'];
const PAGE_SIZE = 25;

export interface MyTasksPageProps extends ActivitiesOrganProps {
  entityHref?: (entityKind: string, entityId: string) => string | null;
}

const paramsFor = (tab: Tab, page: number): Omit<ActivityListParams, 'assignee_id'> => ({
  status: tab === 'done' ? 'done' : 'open',
  overdue: tab === 'overdue' ? true : undefined,
  page,
  page_size: PAGE_SIZE,
});

export function MyTasksPage({ hooks, t = defaultActivitiesT, locale, assigneeOptions, assigneeLabel, entityHref }: MyTasksPageProps) {
  const [tab, setTab] = React.useState<Tab>('open');
  const [page, setPage] = React.useState(1);
  const list = hooks.useMyActivities(paramsFor(tab, page));
  const types = hooks.useActivityTypes();
  const m = hooks.useActivityMutations();
  const [err, setErr] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const typeLabel = new Map((types.data ?? []).map((x) => [x.slug, x.label]));

  async function run(id: string, p: Promise<unknown>) {
    setErr(null);
    setBusyId(id);
    try {
      await p;
    } catch (e) {
      setErr(activitiesErrorMessage(e, t));
    } finally {
      setBusyId(null);
    }
  }

  const body = (() => {
    if (list.showSkeleton) return <ListSkeleton rows={5} />;
    if (list.isError && !list.data) {
      return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
    }
    const rows = list.data?.data ?? [];
    if (rows.length === 0) return <EmptyState message={t(`mytasks.empty.${tab}`)} />;
    return (
      <ul className="divide-y rounded-md border">
        {rows.map((a: Activity) => {
          const href = entityHref?.(a.entity_kind, a.entity_id) ?? null;
          return (
            <ActivityRow
              key={a.id}
              activity={a}
              typeLabel={typeLabel.get(a.type_slug) ?? a.type_slug}
              busy={busyId === a.id}
              t={t}
              locale={locale}
              assigneeOptions={assigneeOptions}
              assigneeLabel={assigneeLabel}
              trailing={href ? <a className="text-xs underline" href={href}>{t('mytasks.open_entity')}</a> : null}
              onToggleDone={(x) => run(x.id, x.done_at ? m.reopen.mutateAsync({ id: x.id }) : m.complete.mutateAsync({ id: x.id }))}
              onCancel={(x) => run(x.id, m.cancel.mutateAsync({ id: x.id }))}
              onReschedule={(x, dueAt) => run(x.id, m.reschedule.mutateAsync({ id: x.id, due_at: dueAt }))}
              onReassign={(x, to) => run(x.id, m.reassign.mutateAsync({ id: x.id, assignee_id: to }))}
            />
          );
        })}
      </ul>
    );
  })();

  const total = list.data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-3" aria-busy={list.isRefreshing}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{t('mytasks.title')}</h2>
        <div role="group" aria-label={t('mytasks.title')} className="flex gap-1">
          {TABS.map((x) => (
            <Button
              key={x}
              size="sm"
              variant={tab === x ? 'primary' : 'ghost'}
              aria-pressed={tab === x}
              onClick={() => {
                setTab(x);
                setPage(1);
              }}
            >
              {t(`mytasks.filter.${x}`)}
            </Button>
          ))}
        </div>
        <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
        {list.data ? <span className="ml-auto text-xs text-muted-foreground">{t('mytasks.summary', { count: total })}</span> : null}
      </div>
      <FormError message={err} />
      {body}
      {pages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t('common.previous')}
          </Button>
          <span>{t('common.page', { page, pages })}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            {t('common.next')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
