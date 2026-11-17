/**
 * "Atendimento semanal" tab: the client's weekly slots (weekday + time, duration, price, period, "cobrar faltas").
 * Create / edit / pause / resume / end / delete; the server keeps the session of the week ahead created (one week
 * before), so the sessions refresh with every write. An edit can leave the session already created as it is.
 */
import { Pause, Pencil, Play, Plus, Square, Trash2 } from 'lucide-react';
import * as React from 'react';

import { useConfirm } from '../components/confirm/ConfirmProvider';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { centsToInput, formatCents, parseMoneyToCents } from '../organ-kit/money';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatDay, SCHEDULE_STATUS, todayIn, tzOf, WEEKDAYS } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, ToneBadge } from './parts';
import type { Client, Schedule, ScheduleInput } from './types';

function ScheduleForm({ hooks, client, schedule, onClose }: { hooks: ClientsHooks; client: Client; schedule: Schedule | null; onClose: () => void }) {
  const { data: config } = hooks.useClientsConfig();
  const create = hooks.useCreateSchedule();
  const update = hooks.useUpdateSchedule();
  const [weekday, setWeekday] = React.useState(String(schedule?.weekday ?? 0));
  const [time, setTime] = React.useState(schedule?.time ?? '');
  const [duration, setDuration] = React.useState(String(schedule?.duration_min ?? client.session_duration_min ?? config?.default_duration_min ?? ''));
  const [price, setPrice] = React.useState(centsToInput(schedule?.price_cents));
  // A new slot leaves "a partir de" empty: the server starts it at least a day ahead (never today).
  const [startsOn, setStartsOn] = React.useState(schedule?.starts_on ?? '');
  const [endsOn, setEndsOn] = React.useState(schedule?.ends_on ?? '');
  const [chargeAbsences, setChargeAbsences] = React.useState(schedule?.charge_absences ?? true);
  const [applyExisting, setApplyExisting] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{2}:\d{2}$/.test(time)) return setError(t('schedule_form.time_required'));
    const cents = price.trim() ? parseMoneyToCents(price) : null;
    if (price.trim() && cents === null) return setError(t('form.price_invalid'));
    const minutes = Number(duration);
    if (duration.trim() && (!Number.isInteger(minutes) || minutes <= 0)) return setError(t('form.duration_invalid'));
    setError(null);
    const body: ScheduleInput = {
      weekday: Number(weekday),
      time,
      price_cents: cents,
      starts_on: startsOn || undefined,
      ends_on: endsOn || null,
      charge_absences: chargeAbsences,
      ...(duration.trim() ? { duration_min: minutes } : {}),
    };
    const done = { onSuccess: onClose, onError: (err: unknown) => setError(clientsErrorText(err)) };
    if (schedule) update.mutate({ id: schedule.id, client_id: client.id, ...body, apply_to_existing: applyExisting }, done);
    else create.mutate({ clientId: client.id, ...body }, done);
  };

  return (
    <form onSubmit={submit} noValidate data-testid="schedule-form">
      <DialogHeader>
        <h2 className="text-lg font-semibold">{schedule ? t('schedule_form.title_edit') : t('schedule_form.title_new')}</h2>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('schedule_form.weekday')}>
            <Select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
              {WEEKDAYS.map((d, i) => (
                <option key={d} value={i}>
                  {d}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('schedule_form.time')} required>
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </Field>
          <Field label={t('schedule_form.duration')}>
            <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
          </Field>
          <Field label={t('schedule_form.price')}>
            <Input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder={centsToInput(client.default_price_cents ?? config?.default_price_cents) || '0,00'} />
          </Field>
          <Field label={t('schedule_form.starts_on')}>
            <Input type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
          </Field>
          <Field label={t('schedule_form.ends_on')}>
            <Input type="date" value={endsOn} min={startsOn || undefined} onChange={(e) => setEndsOn(e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={chargeAbsences} onChange={(e) => setChargeAbsences(e.target.checked)} data-testid="schedule-charge-absences" />
          {t('schedule_form.charge_absences')}
        </label>
        {schedule && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={applyExisting} onChange={(e) => setApplyExisting(e.target.checked)} data-testid="schedule-apply-existing" />
            {t('schedule_form.apply_existing')}
          </label>
        )}
        <FormError message={error} />
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={pending} data-testid="schedule-save">
          {pending ? t('common.saving') : t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ClientSchedulesTab({ hooks, client }: { hooks: ClientsHooks; client: Client }) {
  const confirm = useConfirm();
  const { data: config } = hooks.useClientsConfig();
  const schedules = hooks.useSchedules(client.id);
  const update = hooks.useUpdateSchedule();
  const del = hooks.useDeleteSchedule();
  const [editing, setEditing] = React.useState<Schedule | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const rows = schedules.data ?? [];

  const fail = (err: unknown) => setError(clientsErrorText(err, 'schedules.action_error'));
  const toggle = (s: Schedule) => {
    setError(null);
    update.mutate({ id: s.id, client_id: client.id, active: !s.active }, { onError: fail });
  };
  const end = async (s: Schedule) => {
    const ok = await confirm({ title: t('schedules.end_title'), description: t('schedules.end_body'), confirmLabel: t('schedules.end') });
    if (!ok) return;
    setError(null);
    update.mutate({ id: s.id, client_id: client.id, ends_on: todayIn(tzOf(config)) }, { onError: fail });
  };
  const remove = async (s: Schedule) => {
    const ok = await confirm({ title: t('schedules.delete_title'), description: t('schedules.delete_body'), confirmLabel: t('common.delete'), tone: 'danger' });
    if (!ok) return;
    setError(null);
    del.mutate({ id: s.id, client_id: client.id }, { onError: fail });
  };

  return (
    <div className="space-y-3" data-testid="client-schedules">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{t('schedules.intro')}</p>
        <Button onClick={() => setCreating(true)} data-testid="schedules-new">
          <Plus className="mr-1 h-4 w-4" />
          {t('schedules.new')}
        </Button>
      </div>
      <RefreshingBar active={schedules.isRefreshing} label={t('common.refreshing')} />
      <FormError message={error} />
      {schedules.showSkeleton ? (
        <ListSkeleton rows={2} />
      ) : schedules.isError && !schedules.data ? (
        <RetryError message={`${t('schedules.error')} ${errorMessage(schedules.error)}`} onRetry={() => void schedules.refetch()} retryLabel={t('common.retry')} />
      ) : rows.length === 0 ? (
        <EmptyState message={t('schedules.empty')} />
      ) : (
        <ul className="rounded-md border text-sm">
          {rows.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2 border-t px-3 py-2 first:border-t-0" data-testid={`schedule-row-${s.id}`}>
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t('schedules.every', { weekday: WEEKDAYS[s.weekday]?.toLowerCase() ?? String(s.weekday), time: s.time })}</p>
                <p className="text-xs text-muted-foreground">
                  {t('sessions.minutes', { n: s.duration_min })}
                  {s.price_cents != null ? ` · ${formatCents(s.price_cents)}` : ''} · {t('schedules.since', { date: formatDay(s.starts_on) })}
                  {s.ends_on ? ` ${t('schedules.until', { date: formatDay(s.ends_on) })}` : ''} · {s.charge_absences ? t('schedules.charges_absences') : t('schedules.waives_absences')}
                </p>
              </div>
              <ToneBadge color={SCHEDULE_STATUS[s.status]?.color ?? 'muted'} testId={`schedule-status-${s.id}`}>
                {SCHEDULE_STATUS[s.status]?.label ?? s.status}
              </ToneBadge>
              {s.status !== 'encerrada' && (
                <>
                  <Button variant="ghost" size="sm" onClick={() => toggle(s)} data-testid={`schedule-toggle-${s.id}`}>
                    {s.active ? <Pause className="mr-1 h-4 w-4" /> : <Play className="mr-1 h-4 w-4" />}
                    {s.active ? t('schedules.pause') : t('schedules.resume')}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => void end(s)} data-testid={`schedule-end-${s.id}`}>
                    <Square className="mr-1 h-4 w-4" />
                    {t('schedules.end')}
                  </Button>
                </>
              )}
              <Button variant="ghost" size="sm" onClick={() => setEditing(s)} aria-label={t('common.edit')}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void remove(s)} aria-label={t('common.delete')} data-testid={`schedule-delete-${s.id}`}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Dialog
        open={creating || !!editing}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        title={editing ? t('schedule_form.title_edit') : t('schedule_form.title_new')}
      >
        <ScheduleForm
          key={editing?.id ?? 'new'}
          hooks={hooks}
          client={client}
          schedule={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      </Dialog>
    </div>
  );
}
