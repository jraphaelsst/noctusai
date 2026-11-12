/**
 * `<ActivitiesPanel/>` — the activities TAB of the card hub: the tasks / calls / meetings / visits about ONE
 * `(entityKind, entityId)`, with a quick-add form, done / undone, reschedule, reassign and cancel.
 *
 * Product-agnostic: the card hub registers it as a subpage (`render: () => <ActivitiesPanel hooks={hooks} entityKind="lead" entityId={id} />`);
 * which kinds exist is the market's data (`useActivityTypes`), never a branch here.
 */
import * as React from 'react';
import { Button, EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { ActivityRow } from './ActivityRow';
import { activitiesErrorMessage, errorMessage } from './hooks';
import { defaultActivitiesT } from './i18n';
import { fromLocalInput, type ActivitiesOrganProps } from './shared';
import type { Activity, ActivityStatus } from './types';

export interface ActivitiesPanelProps extends ActivitiesOrganProps {
  entityKind: string;
  entityId: string;
  /** Pre-selected assignee of a new activity (typically the current user). */
  defaultAssigneeId?: string | null;
  /** The nullable multi-branch convention: stamped on new activities, never interpreted. */
  orgUnitId?: string | null;
}

const FILTERS: readonly ActivityStatus[] = ['open', 'done', 'all'];

export function ActivitiesPanel({
  hooks,
  entityKind,
  entityId,
  defaultAssigneeId = null,
  orgUnitId = null,
  t = defaultActivitiesT,
  locale,
  assigneeOptions,
  assigneeLabel,
}: ActivitiesPanelProps) {
  const [status, setStatus] = React.useState<ActivityStatus>('open');
  const list = hooks.useActivities({ entity_kind: entityKind, entity_id: entityId, status, page_size: 100 });
  const types = hooks.useActivityTypes();
  const m = hooks.useActivityMutations();
  const [typeSlug, setTypeSlug] = React.useState('');
  const [title, setTitle] = React.useState('');
  const [due, setDue] = React.useState('');
  const [assignee, setAssignee] = React.useState(defaultAssigneeId ?? '');
  const [err, setErr] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const typeRows = types.data ?? [];
  const typeLabel = new Map(typeRows.map((x) => [x.slug, x.label]));
  const chosenType = typeSlug || typeRows[0]?.slug || '';

  async function run(id: string | null, p: Promise<unknown>) {
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

  async function add(ev: React.FormEvent) {
    ev.preventDefault();
    if (!title.trim()) {
      setErr(t('form.title_required'));
      return;
    }
    await run(
      null,
      m.create
        .mutateAsync({
          entity_kind: entityKind,
          entity_id: entityId,
          type_slug: chosenType,
          title: title.trim(),
          due_at: fromLocalInput(due),
          assignee_id: assignee || null,
          org_unit_id: orgUnitId,
        })
        .then(() => {
          setTitle('');
          setDue('');
        }),
    );
  }

  const body = (() => {
    if (list.showSkeleton) return <ListSkeleton rows={3} />;
    if (list.isError && !list.data) {
      return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
    }
    const rows = list.data?.data ?? [];
    if (rows.length === 0) return <EmptyState message={t(`panel.empty.${status}`)} />;
    return (
      <ul className="divide-y rounded-md border">
        {rows.map((a: Activity) => (
          <ActivityRow
            key={a.id}
            activity={a}
            typeLabel={typeLabel.get(a.type_slug) ?? a.type_slug}
            busy={busyId === a.id}
            t={t}
            locale={locale}
            assigneeOptions={assigneeOptions}
            assigneeLabel={assigneeLabel}
            onToggleDone={(x) => run(x.id, x.done_at ? m.reopen.mutateAsync({ id: x.id }) : m.complete.mutateAsync({ id: x.id }))}
            onCancel={(x) => run(x.id, m.cancel.mutateAsync({ id: x.id }))}
            onReschedule={(x, dueAt) => run(x.id, m.reschedule.mutateAsync({ id: x.id, due_at: dueAt }))}
            onReassign={(x, to) => run(x.id, m.reassign.mutateAsync({ id: x.id, assignee_id: to }))}
          />
        ))}
      </ul>
    );
  })();

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing} aria-label={t('panel.title')}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t('panel.title')}</h3>
        <div role="group" aria-label={t('panel.title')} className="flex gap-1">
          {FILTERS.map((f) => (
            <Button key={f} size="sm" variant={status === f ? 'primary' : 'ghost'} aria-pressed={status === f} onClick={() => setStatus(f)}>
              {t(`panel.filter.${f}`)}
            </Button>
          ))}
        </div>
        <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      </div>

      <form onSubmit={add} className="grid gap-2 rounded-md border p-3 sm:grid-cols-[10rem_1fr_12rem_10rem_auto]" aria-label={t('panel.new')}>
        <Field label={t('form.type')}>
          <Select value={chosenType} onChange={(e) => setTypeSlug(e.target.value)} disabled={typeRows.length === 0}>
            {typeRows.length === 0 ? <option value="">{t('form.no_types')}</option> : null}
            {typeRows.map((x) => (
              <option key={x.slug} value={x.slug}>
                {x.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('form.title')}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('form.title_placeholder')} maxLength={200} />
        </Field>
        <Field label={t('form.due')}>
          <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        {assigneeOptions && assigneeOptions.length > 0 ? (
          <Field label={t('form.assignee')}>
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">{t('form.unassigned')}</option>
              {assigneeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : (
          <span />
        )}
        <div className="flex items-end">
          <Button type="submit" disabled={m.create.isPending || !chosenType}>
            {m.create.isPending ? t('panel.adding') : t('panel.add')}
          </Button>
        </div>
      </form>
      <FormError message={err} />
      {body}
    </section>
  );
}
