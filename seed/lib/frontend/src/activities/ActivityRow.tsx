/** `<ActivityRow/>` — one activity: done toggle, title, type, due (overdue flagged), assignee, reschedule / reassign / cancel. */
import type * as React from 'react';
import { Badge, Button, Input, Select } from './controls';
import { defaultActivitiesT } from './i18n';
import { formatDue, fromLocalInput, toLocalInput, type ActivitiesOrganProps } from './shared';
import type { Activity } from './types';

export interface ActivityRowProps extends Pick<ActivitiesOrganProps, 't' | 'locale' | 'assigneeOptions' | 'assigneeLabel'> {
  activity: Activity;
  typeLabel: string;
  /** The row's pending write (its id) disables just this row. */
  busy?: boolean;
  onToggleDone: (activity: Activity) => void;
  onCancel: (activity: Activity) => void;
  onReschedule: (activity: Activity, dueAt: string | null) => void;
  onReassign: (activity: Activity, assigneeId: string | null) => void;
  /** MyTasks shows what the task is about; the panel (already inside the card) does not. */
  trailing?: React.ReactNode;
}

export function ActivityRow({
  activity: a,
  typeLabel,
  busy = false,
  onToggleDone,
  onCancel,
  onReschedule,
  onReassign,
  t = defaultActivitiesT,
  locale,
  assigneeOptions,
  assigneeLabel,
  trailing,
}: ActivityRowProps) {
  const done = !!a.done_at;
  const cancelled = !!a.cancelled_at;
  const closed = done || cancelled;
  const assignee = a.assignee_id ? assigneeLabel?.(a.assignee_id) ?? null : null;
  return (
    <li className="flex flex-wrap items-center gap-2 p-3 text-sm" data-testid="activity-row" aria-busy={busy}>
      <input
        type="checkbox"
        className="h-4 w-4"
        checked={done}
        disabled={busy || cancelled}
        aria-label={done ? t('row.undone') : t('row.done')}
        onChange={() => onToggleDone(a)}
      />
      <span className={done || cancelled ? 'text-muted-foreground line-through' : 'font-medium'}>{a.title}</span>
      <Badge variant="outline">{typeLabel}</Badge>
      {a.overdue ? <Badge variant="destructive">{t('row.overdue')}</Badge> : null}
      {cancelled ? <Badge variant="muted">{t('row.cancelled')}</Badge> : null}
      {done && a.outcome ? <Badge variant="muted">{t(`row.outcome.${a.outcome}`)}</Badge> : null}
      <span className="text-xs text-muted-foreground">{a.due_at ? t('row.due', { date: formatDue(a.due_at, locale) }) : t('row.no_due')}</span>
      {assignee ? <span className="text-xs text-muted-foreground">{t('row.assignee', { name: assignee })}</span> : null}
      {trailing}
      {!closed ? (
        <span className="ml-auto flex flex-wrap items-center gap-1">
          <Input
            type="datetime-local"
            className="h-7 w-44 text-xs"
            aria-label={t('row.reschedule')}
            value={toLocalInput(a.due_at)}
            disabled={busy}
            onChange={(e) => {
              const next = fromLocalInput(e.target.value);
              if (next !== a.due_at) onReschedule(a, next);
            }}
          />
          {assigneeOptions && assigneeOptions.length > 0 ? (
            <Select
              className="h-7 w-40 text-xs"
              aria-label={t('row.reassign')}
              value={a.assignee_id ?? ''}
              disabled={busy}
              onChange={(e) => onReassign(a, e.target.value || null)}
            >
              <option value="">{t('form.unassigned')}</option>
              {assigneeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </Select>
          ) : null}
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => onCancel(a)}>
            {t('row.cancel')}
          </Button>
        </span>
      ) : null}
    </li>
  );
}
