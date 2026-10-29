/**
 * `<LeadFormDialog/>` -- create / edit a lead. Few fields on purpose: name, phone, e-mail, origin, stage, notes, tags,
 * first contact. Server refusals (422 `telefone_invalido`...) are shown in pt-BR next to the form, never swallowed.
 */
import * as React from 'react';

import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { Field, FormError, Input, Select, Textarea } from './controls';
import { fromDateInput, splitTags, toDateInput } from './format';
import { warnStageHook } from './stageHook';
import { apiErrorCode, errorMessage, type LeadsHooks } from './hooks';
import { t } from './i18n';
import type { Lead, LeadInput } from './types';

export interface LeadFormDialogProps {
  hooks: LeadsHooks;
  open: boolean;
  /** `null` = create. */
  lead: Lead | null;
  onClose: () => void;
  onSaved?: (lead: Lead) => void;
  /** Stage preselected on create (e.g. "+" at the top of a column). */
  defaultStage?: string;
}

export function leadsErrorText(err: unknown): string {
  const code = apiErrorCode(err);
  const key = code ? `error.${code}` : '';
  const mapped = key ? t(key) : '';
  return mapped && mapped !== key ? mapped : `${t('form.error')}: ${errorMessage(err)}`;
}

function Form({ hooks, lead, onClose, onSaved, defaultStage }: Omit<LeadFormDialogProps, 'open'>) {
  const { data: config } = hooks.useLeadsConfig();
  const create = hooks.useCreateLead();
  const update = hooks.useUpdateLead();
  const [name, setName] = React.useState(lead?.name ?? '');
  const [phone, setPhone] = React.useState(lead?.phone ?? '');
  const [email, setEmail] = React.useState(lead?.email ?? '');
  const [origin, setOrigin] = React.useState(lead?.origin ?? '');
  const [stage, setStage] = React.useState(lead?.stage ?? defaultStage ?? '');
  const [notes, setNotes] = React.useState(lead?.notes ?? '');
  const [tags, setTags] = React.useState((lead?.tags ?? []).join(', '));
  const [firstContact, setFirstContact] = React.useState(toDateInput(lead?.first_contact_at));
  const [nameError, setNameError] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError(t('form.name_required'));
      return;
    }
    setNameError(null);
    setError(null);
    const body: LeadInput = {
      name: name.trim(),
      phone: phone.trim() || null,
      email: email.trim() || null,
      notes: notes.trim() || null,
      tags: splitTags(tags),
      ...(origin ? { origin } : {}),
      ...(stage ? { stage } : {}),
      // Only a date the user actually touched is sent: re-saving an untouched lead must not shift its first contact.
      ...(firstContact && firstContact !== toDateInput(lead?.first_contact_at) ? { first_contact_at: fromDateInput(firstContact) } : {}),
    };
    const done = {
      onSuccess: (saved: Lead) => {
        warnStageHook(saved);
        onSaved?.(saved);
        onClose();
      },
      onError: (err: unknown) => setError(leadsErrorText(err)),
    };
    if (lead) update.mutate({ id: lead.id, ...body }, done);
    else create.mutate(body, done);
  };

  return (
    <form onSubmit={submit} noValidate>
      <DialogHeader>
        <h2 className="text-lg font-semibold">{lead ? t('form.title_edit') : t('form.title_new')}</h2>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <Field label={t('form.name')} required error={nameError}>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={200} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('form.phone')}>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" maxLength={40} />
          </Field>
          <Field label={t('form.email')}>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} />
          </Field>
          <Field label={t('form.origin')}>
            <Select value={origin} onChange={(e) => setOrigin(e.target.value)}>
              {!lead && <option value="">{config?.origins.find((o) => o.slug === config.default_origin)?.label ?? ''}</option>}
              {config?.origins.map((o) => (
                <option key={o.slug} value={o.slug}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('form.stage')}>
            <Select value={stage} onChange={(e) => setStage(e.target.value)}>
              {!lead && !defaultStage && <option value="">{config?.stages[0]?.label ?? ''}</option>}
              {config?.stages.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label={t('form.first_contact')}>
          <Input type="date" value={firstContact} onChange={(e) => setFirstContact(e.target.value)} />
        </Field>
        <Field label={t('form.notes')}>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={5000} />
        </Field>
        <Field label={t('form.tags')}>
          <Input value={tags} onChange={(e) => setTags(e.target.value)} />
        </Field>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? t('common.saving') : t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function LeadFormDialog({ open, ...rest }: LeadFormDialogProps) {
  return (
    <Dialog open={open} onClose={rest.onClose} title={rest.lead ? t('form.title_edit') : t('form.title_new')}>
      {/* Mounted only while open: reopening starts from the lead's current values, not a stale draft. */}
      <Form key={rest.lead?.id ?? 'new'} {...rest} />
    </Dialog>
  );
}
