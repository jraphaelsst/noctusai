/**
 * `<SessionFormDialog/>` -- create / edit one session (date + time typed in the ORG's zone, duration, status, price,
 * "não cobrar", notes) and delete it. A refusal (`SESSAO_COM_PAGAMENTO`...) is shown in the form, in pt-BR.
 */
import { Trash2 } from 'lucide-react';
import * as React from 'react';

import { useConfirm } from '../components/confirm/ConfirmProvider';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { centsToInput, parseMoneyToCents } from '../organ-kit/money';
import { Field, FormError, Input, Select, Textarea } from './controls';
import { todayIn, tzOf, zonedIso, zonedParts } from './format';
import type { ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, nounVars } from './parts';
import type { Client, Session, SessionInput } from './types';

export interface SessionFormDialogProps {
  hooks: ClientsHooks;
  open: boolean;
  onClose: () => void;
  /** The session's client (create needs it; edit reads `session.client_id`). Its defaults prefill a new session. */
  clientId: string;
  client?: Pick<Client, 'default_price_cents' | 'session_duration_min'> | null;
  /** `null` = create. */
  session: Session | null;
  /** Prefill of a new session (`YYYY-MM-DD`). */
  defaultDate?: string;
  /** Shown on edit when the host can navigate to the client (agenda). */
  onOpenClient?: (clientId: string) => void;
}

function Form({ hooks, onClose, clientId, client, session, defaultDate, onOpenClient }: Omit<SessionFormDialogProps, 'open'>) {
  const confirm = useConfirm();
  const { data: config } = hooks.useClientsConfig();
  const create = hooks.useCreateSession();
  const update = hooks.useUpdateSession();
  const del = hooks.useDeleteSession();
  const tz = tzOf(config);
  const vars = nounVars(config);
  const at = zonedParts(session?.starts_at, tz);
  const [date, setDate] = React.useState(at?.date ?? defaultDate ?? todayIn(tz));
  const [time, setTime] = React.useState(at?.time ?? '');
  const [duration, setDuration] = React.useState(String(session?.duration_min ?? client?.session_duration_min ?? config?.default_duration_min ?? ''));
  const [status, setStatus] = React.useState(session?.status ?? config?.default_session_status ?? '');
  const [price, setPrice] = React.useState(centsToInput(session?.price_cents));
  const [waive, setWaive] = React.useState(session?.waive_charge ?? false);
  const [notes, setNotes] = React.useState(session?.notes ?? '');
  const [error, setError] = React.useState<string | null>(null);
  const pending = create.isPending || update.isPending || del.isPending;
  const defaultPrice = client?.default_price_cents ?? config?.default_price_cents ?? null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const starts_at = zonedIso(date, time, tz);
    if (!starts_at) return setError(t('session_form.when_required'));
    const cents = price.trim() ? parseMoneyToCents(price) : null;
    if (price.trim() && cents === null) return setError(t('form.price_invalid'));
    const minutes = Number(duration);
    if (duration.trim() && (!Number.isInteger(minutes) || minutes <= 0)) return setError(t('form.duration_invalid'));
    setError(null);
    const body: SessionInput = {
      starts_at,
      price_cents: cents,
      waive_charge: waive,
      notes: notes.trim() || null,
      ...(duration.trim() ? { duration_min: minutes } : {}),
      ...(status ? { status } : {}),
    };
    const done = { onSuccess: onClose, onError: (err: unknown) => setError(clientsErrorText(err, 'form.error', vars)) };
    if (session) {
      // Only what changed: re-sending an untouched price of a settled session would be refused.
      const patch: Partial<SessionInput> = {};
      if (starts_at !== zonedIso(at?.date ?? '', at?.time ?? '', tz)) patch.starts_at = starts_at;
      if (body.duration_min !== undefined && body.duration_min !== session.duration_min) patch.duration_min = body.duration_min;
      if (body.status && body.status !== session.status) patch.status = body.status;
      if (cents !== session.price_cents) patch.price_cents = cents;
      if (waive !== session.waive_charge) patch.waive_charge = waive;
      if ((body.notes ?? null) !== (session.notes ?? null)) patch.notes = body.notes;
      if (Object.keys(patch).length === 0) return onClose();
      update.mutate({ id: session.id, client_id: session.client_id, ...patch }, done);
    } else {
      create.mutate({ clientId, ...body }, done);
    }
  };

  const remove = async () => {
    if (!session) return;
    const ok = await confirm({ title: t('sessions.delete_title'), description: t('sessions.delete_body'), confirmLabel: t('common.delete'), tone: 'danger' });
    if (!ok) return;
    setError(null);
    del.mutate({ id: session.id, client_id: session.client_id }, { onSuccess: onClose, onError: (err) => setError(clientsErrorText(err, 'sessions.delete_error')) });
  };

  return (
    <form onSubmit={submit} noValidate data-testid="session-form">
      <DialogHeader>
        <h2 className="text-lg font-semibold">{session ? t('session_form.title_edit') : t('session_form.title_new')}</h2>
        {session && <p className="text-sm text-muted-foreground">{session.client_name}</p>}
      </DialogHeader>
      <DialogBody className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('session_form.date')} required>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label={t('session_form.time')} required>
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </Field>
          <Field label={t('session_form.duration')}>
            <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
          </Field>
          <Field label={t('session_form.status')}>
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {config?.session_statuses.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label={t('session_form.price')}>
          <Input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder={centsToInput(defaultPrice) || '0,00'} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={waive} onChange={(e) => setWaive(e.target.checked)} />
          {t('session_form.waive')}
        </label>
        <Field label={t('session_form.notes')}>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={5000} />
        </Field>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter className="justify-between gap-2">
        <div className="flex gap-2">
          {session && (
            <Button type="button" variant="destructive" size="sm" onClick={() => void remove()} disabled={pending} data-testid="session-delete">
              <Trash2 className="mr-1 h-4 w-4" />
              {t('common.delete')}
            </Button>
          )}
          {session && onOpenClient && (
            <Button type="button" variant="outline" size="sm" onClick={() => onOpenClient(session.client_id)} data-testid="session-open-client">
              {t('session_form.go_client', vars)}
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={pending} data-testid="session-save">
            {pending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </DialogFooter>
    </form>
  );
}

export function SessionFormDialog({ open, ...rest }: SessionFormDialogProps) {
  return (
    <Dialog open={open} onClose={rest.onClose} title={rest.session ? t('session_form.title_edit') : t('session_form.title_new')}>
      <Form key={rest.session?.id ?? `new-${rest.defaultDate ?? ''}`} {...rest} />
    </Dialog>
  );
}
