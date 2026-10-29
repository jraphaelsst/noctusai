/**
 * `<ClientForm/>` -- create / edit a client (inline on the detail's "Dados" tab, or inside `<ClientFormDialog/>`).
 * Only fields the user changed are sent on edit (a masked CPF the server returned must never be written back).
 * Server refusals are shown next to the form, in pt-BR, never swallowed.
 */
import * as React from 'react';

import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { splitTags } from '../leads/format';
import { centsToInput, parseMoneyToCents } from '../organ-kit/money';
import { Field, FormError, Input, Select, Textarea } from './controls';
import { docDigits } from './format';
import type { ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, nounVars } from './parts';
import type { Client, ClientInput } from './types';

export interface ClientFormProps {
  hooks: ClientsHooks;
  /** `null` = create. */
  client: Client | null;
  onSaved?: (client: Client) => void;
  onCancel?: () => void;
  /** The CPF is masked for non-admins by the server: they see it, they cannot edit it. */
  isAdmin?: boolean;
  /** Render the title (dialog) or not (inline tab). */
  showTitle?: boolean;
}

export function ClientForm({ hooks, client, onSaved, onCancel, isAdmin = true, showTitle = false }: ClientFormProps) {
  const { data: config } = hooks.useClientsConfig();
  const create = hooks.useCreateClient();
  const update = hooks.useUpdateClient();
  const vars = nounVars(config);
  const initial = React.useMemo(
    () => ({
      name: client?.name ?? '',
      phone: client?.phone ?? '',
      email: client?.email ?? '',
      doc: client?.doc ?? '',
      birth_date: client?.birth_date ?? '',
      status: client?.status ?? '',
      tags: (client?.tags ?? []).join(', '),
      notes: client?.notes ?? '',
      price: centsToInput(client?.default_price_cents),
      duration: client?.session_duration_min != null ? String(client.session_duration_min) : '',
      started_at: client?.started_at ?? '',
    }),
    [client],
  );
  const [v, setV] = React.useState(initial);
  const [fieldError, setFieldError] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);
  const pending = create.isPending || update.isPending;
  const set = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setV((prev) => ({ ...prev, [k]: e.target.value }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!v.name.trim()) errs.name = t('form.name_required');
    const price = v.price.trim() ? parseMoneyToCents(v.price) : null;
    if (v.price.trim() && price === null) errs.price = t('form.price_invalid');
    const duration = v.duration.trim() ? Number(v.duration) : null;
    if (duration !== null && (!Number.isInteger(duration) || duration <= 0)) errs.duration = t('form.duration_invalid');
    setFieldError(errs);
    if (Object.keys(errs).length) return;
    setError(null);
    const full: ClientInput = {
      name: v.name.trim(),
      phone: v.phone.trim() || null,
      email: v.email.trim() || null,
      doc: docDigits(v.doc),
      birth_date: v.birth_date || null,
      tags: splitTags(v.tags),
      notes: v.notes.trim() || null,
      default_price_cents: price,
      session_duration_min: duration,
      ...(v.status ? { status: v.status } : {}),
      ...(v.started_at ? { started_at: v.started_at } : {}),
    };
    const done = {
      onSuccess: (saved: Client) => onSaved?.(saved),
      onError: (err: unknown) => setError(clientsErrorText(err, 'form.error', vars)),
    };
    if (!client) {
      create.mutate(full, done);
      return;
    }
    // Edit: only what changed (field name -> its form key).
    const keyOf: Record<string, keyof typeof initial> = {
      name: 'name', phone: 'phone', email: 'email', doc: 'doc', birth_date: 'birth_date', status: 'status', tags: 'tags',
      notes: 'notes', default_price_cents: 'price', session_duration_min: 'duration', started_at: 'started_at',
    };
    const patch = Object.fromEntries(Object.entries(full).filter(([k]) => v[keyOf[k]] !== initial[keyOf[k]]));
    if (Object.keys(patch).length === 0) {
      onSaved?.(client);
      return;
    }
    update.mutate({ id: client.id, ...patch }, done);
  };

  return (
    <form onSubmit={submit} noValidate data-testid="client-form">
      {showTitle && (
        <DialogHeader>
          <h2 className="text-lg font-semibold">{client ? t('form.title_edit', vars) : t('form.title_new', vars)}</h2>
        </DialogHeader>
      )}
      <DialogBody className="space-y-3">
        <Field label={t('form.name')} required error={fieldError.name}>
          <Input value={v.name} onChange={set('name')} autoFocus={!client} maxLength={200} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('form.phone')}>
            <Input value={v.phone} onChange={set('phone')} inputMode="tel" maxLength={40} />
          </Field>
          <Field label={t('form.email')}>
            <Input type="email" value={v.email} onChange={set('email')} maxLength={254} />
          </Field>
          <Field label={t('form.doc')}>
            <Input value={v.doc} onChange={set('doc')} inputMode="numeric" maxLength={20} disabled={!!client && !isAdmin} />
          </Field>
          <Field label={t('form.birth_date')}>
            <Input type="date" value={v.birth_date} onChange={set('birth_date')} />
          </Field>
          <Field label={t('form.status')}>
            <Select value={v.status} onChange={set('status')}>
              {!client && <option value="">{config?.statuses[0]?.label ?? ''}</option>}
              {config?.statuses.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('form.started_at')}>
            <Input type="date" value={v.started_at} onChange={set('started_at')} />
          </Field>
          <Field label={t('form.default_price')} error={fieldError.price}>
            <Input value={v.price} onChange={set('price')} inputMode="decimal" placeholder={centsToInput(config?.default_price_cents) || '0,00'} />
          </Field>
          <Field label={t('form.duration')} error={fieldError.duration}>
            <Input type="number" min={1} value={v.duration} onChange={set('duration')} placeholder={String(config?.default_duration_min ?? '')} />
          </Field>
        </div>
        <Field label={t('form.tags')}>
          <Input value={v.tags} onChange={set('tags')} />
        </Field>
        <Field label={t('form.notes')}>
          <Textarea value={v.notes} onChange={set('notes')} rows={3} maxLength={5000} />
        </Field>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>
            {t('common.cancel')}
          </Button>
        )}
        <Button type="submit" disabled={pending} data-testid="client-form-save">
          {pending ? t('common.saving') : t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}

export interface ClientFormDialogProps extends Omit<ClientFormProps, 'showTitle' | 'onCancel'> {
  open: boolean;
  onClose: () => void;
}

export function ClientFormDialog({ open, onClose, onSaved, ...rest }: ClientFormDialogProps) {
  const { data: config } = rest.hooks.useClientsConfig();
  const vars = nounVars(config);
  return (
    <Dialog open={open} onClose={onClose} title={rest.client ? t('form.title_edit', vars) : t('form.title_new', vars)}>
      {/* Mounted only while open: reopening starts from the client's current values, not a stale draft. */}
      <ClientForm
        key={rest.client?.id ?? 'new'}
        {...rest}
        showTitle
        onCancel={onClose}
        onSaved={(c) => {
          onSaved?.(c);
          onClose();
        }}
      />
    </Dialog>
  );
}
