/**
 * `<PartyEditor/>` — create / edit / archive / delete a party in a dialog.
 *
 * - PF takes a CPF, PJ a CNPJ (check digits validated client-side with `identificador.ts`; the server
 *   is the validator of record and its codes are mapped to pt-BR messages).
 * - A masked document (non-admin reader) is shown but never edited or sent back.
 * - `canWrite=false` renders a read-only view (UX only — writes are admin-only on the server).
 * - Archive is the normal retirement; delete is refused by the server while the party is referenced
 *   (409 `parceiro_em_uso`) and the message says to archive instead.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select, Textarea } from './controls';
import { formatDoc, isMaskedDoc, isValidDoc, isValidEmail, maskDocInput, onlyAlnum, splitPhones } from './format';
import { apiErrorCode, errorMessage, type PartiesHooks } from './hooks';
import { t } from './i18n';
import { RolePicker } from './RoleChips';
import { ADDRESS_FIELDS, PARTY_KINDS, type Party, type PartyAddress, type PartyInput, type PartyKind, type PartyRole } from './types';

export interface PartyEditorProps {
  hooks: PartiesHooks;
  open: boolean;
  /** `null` = create a new party. */
  partyId: string | null;
  onClose: () => void;
  /** Admin write access (UX only). Default `false` = read-only view. */
  canWrite?: boolean;
  onSaved?: (party: Party) => void;
  /** Pre-selected roles for a NEW party (e.g. the list is filtered to suppliers). */
  defaultRoles?: PartyRole[];
}

const DOC_FIELD_CODES = new Set(['documento_invalido', 'documento_duplicado']);

/** pt-BR message of a failed call: the mapped code when the organ knows it, else the server's own text. */
export function partiesErrorText(err: unknown): string {
  const code = apiErrorCode(err);
  const key = code ? `error.${code}` : '';
  const mapped = key ? t(key) : '';
  return mapped && mapped !== key ? mapped : `${t('error.generic')}: ${errorMessage(err)}`;
}

function cleanAddress(a: PartyAddress): PartyAddress {
  const out: PartyAddress = {};
  for (const k of ADDRESS_FIELDS) if (a[k]?.trim()) out[k] = a[k]!.trim();
  return out;
}

interface FormProps extends Omit<PartyEditorProps, 'open' | 'partyId'> {
  party: Party | null;
}

function PartyForm({ hooks, party, onClose, canWrite = false, onSaved, defaultRoles }: FormProps) {
  const create = hooks.useCreateParty();
  const update = hooks.useUpdateParty();
  const archive = hooks.useArchiveParty();
  const remove = hooks.useDeleteParty();

  const docLocked = isMaskedDoc(party?.doc);
  const readOnly = !canWrite;
  const [kind, setKind] = React.useState<PartyKind>(party?.kind ?? 'PF');
  const [doc, setDoc] = React.useState(party ? formatDoc(party.kind, party.doc) : '');
  const [legalName, setLegalName] = React.useState(party?.legal_name ?? '');
  const [tradeName, setTradeName] = React.useState(party?.trade_name ?? '');
  const [email, setEmail] = React.useState(party?.email ?? '');
  const [phones, setPhones] = React.useState((party?.phones ?? []).join(', '));
  const [address, setAddress] = React.useState<PartyAddress>(party?.address ?? {});
  const [stateReg, setStateReg] = React.useState(party?.state_registration ?? '');
  const [municipalReg, setMunicipalReg] = React.useState(party?.municipal_registration ?? '');
  const [notes, setNotes] = React.useState(party?.notes ?? '');
  const [roles, setRoles] = React.useState<PartyRole[]>(party?.roles ?? defaultRoles ?? []);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const saving = create.isPending || update.isPending;

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!legalName.trim()) next.legal_name = t('error.name_required');
    if (!docLocked && !isValidDoc(kind, doc)) next.doc = t(`error.doc_invalid_${kind}`);
    if (email.trim() && !isValidEmail(email)) next.email = t('error.email_invalid');
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function failed(err: unknown) {
    const code = apiErrorCode(err);
    if (code && DOC_FIELD_CODES.has(code)) setErrors((e) => ({ ...e, doc: partiesErrorText(err) }));
    else setFormError(partiesErrorText(err));
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setFormError(null);
    if (readOnly || !validate()) return;
    const body: PartyInput = {
      kind,
      legal_name: legalName.trim(),
      trade_name: tradeName.trim() || null,
      email: email.trim() || null,
      phones: splitPhones(phones),
      address: cleanAddress(address),
      state_registration: stateReg.trim() || null,
      municipal_registration: municipalReg.trim() || null,
      notes: notes.trim() || null,
      roles,
    };
    if (!docLocked) body.doc = onlyAlnum(doc) || null;
    try {
      const saved = party ? await update.mutateAsync({ id: party.id, ...body }) : await create.mutateAsync(body);
      onSaved?.(saved);
      onClose();
    } catch (err) {
      failed(err);
    }
  }

  async function toggleArchive() {
    if (!party) return;
    setFormError(null);
    try {
      const saved = await archive.mutateAsync({ id: party.id, restore: !party.is_active });
      onSaved?.(saved);
      onClose();
    } catch (err) {
      failed(err);
    }
  }

  async function doDelete() {
    if (!party) return;
    setFormError(null);
    try {
      await remove.mutateAsync(party.id);
      onClose();
    } catch (err) {
      setConfirmDelete(false);
      failed(err);
    }
  }

  const setAddr = (k: keyof PartyAddress) => (e: React.ChangeEvent<HTMLInputElement>) => setAddress((a) => ({ ...a, [k]: e.target.value }));
  const busy = saving || archive.isPending || remove.isPending;
  const docLabel = kind === 'PF' ? t('editor.doc_cpf') : t('editor.doc_cnpj');

  return (
    <form onSubmit={submit} noValidate>
      <DialogBody className="space-y-4">
        {readOnly ? <p className="text-xs text-muted-foreground">{t('editor.read_only')}</p> : null}
        <FormError message={formError} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.kind')}>
            <Select
              value={kind}
              disabled={readOnly || !!party}
              onChange={(e) => {
                const next = e.target.value as PartyKind;
                setKind(next);
                if (!docLocked) setDoc((d) => maskDocInput(next, d));
              }}
            >
              {PARTY_KINDS.map((k) => (
                <option key={k} value={k}>{t(`kind.${k}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={docLabel} error={errors.doc}>
            <Input
              value={doc}
              inputMode="text"
              disabled={readOnly || docLocked}
              title={docLocked ? t('editor.doc_masked') : undefined}
              onChange={(e) => setDoc(maskDocInput(kind, e.target.value))}
              aria-invalid={!!errors.doc}
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={kind === 'PF' ? t('editor.legal_name_pf') : t('editor.legal_name_pj')} required error={errors.legal_name}>
            <Input value={legalName} disabled={readOnly} onChange={(e) => setLegalName(e.target.value)} aria-invalid={!!errors.legal_name} />
          </Field>
          <Field label={t('editor.trade_name')}>
            <Input value={tradeName} disabled={readOnly} onChange={(e) => setTradeName(e.target.value)} />
          </Field>
          <Field label={t('editor.email')} error={errors.email}>
            <Input type="email" value={email} disabled={readOnly} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!errors.email} />
          </Field>
          <Field label={t('editor.phones')}>
            <Input value={phones} disabled={readOnly} onChange={(e) => setPhones(e.target.value)} />
          </Field>
          <Field label={t('editor.state_registration')}>
            <Input value={stateReg} disabled={readOnly} onChange={(e) => setStateReg(e.target.value)} />
          </Field>
          <Field label={t('editor.municipal_registration')}>
            <Input value={municipalReg} disabled={readOnly} onChange={(e) => setMunicipalReg(e.target.value)} />
          </Field>
        </div>
        <div className="space-y-2">
          <span className="block text-xs font-medium">{t('role.group')}</span>
          <RolePicker value={roles} onChange={setRoles} disabled={readOnly} />
        </div>
        <fieldset className="space-y-2">
          <legend className="text-xs font-medium">{t('editor.address')}</legend>
          <div className="grid gap-3 sm:grid-cols-4">
            {ADDRESS_FIELDS.map((k) => (
              <Field key={k} label={t(`address.${k}`)}>
                <Input value={address[k] ?? ''} disabled={readOnly} maxLength={k === 'state' ? 2 : undefined} onChange={setAddr(k)} />
              </Field>
            ))}
          </div>
        </fieldset>
        <Field label={t('editor.notes')}>
          <Textarea value={notes} rows={3} disabled={readOnly} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </DialogBody>
      <DialogFooter className="items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {party && canWrite ? (
            <>
              <Button type="button" variant="outline" disabled={busy} onClick={toggleArchive}>
                {party.is_active ? t('editor.archive') : t('editor.restore')}
              </Button>
              {confirmDelete ? (
                <span className="flex items-center gap-2 text-xs">
                  {t('editor.delete_confirm')}
                  <Button type="button" variant="outline" disabled={busy} onClick={doDelete}>{t('editor.delete_confirm_yes')}</Button>
                  <Button type="button" variant="ghost" onClick={() => setConfirmDelete(false)}>{t('common.cancel')}</Button>
                </span>
              ) : (
                <Button type="button" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(true)}>{t('editor.delete')}</Button>
              )}
            </>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>{readOnly ? t('common.close') : t('common.cancel')}</Button>
          {readOnly ? null : (
            <Button type="submit" disabled={busy}>{saving ? t('common.saving') : t('common.save')}</Button>
          )}
        </div>
      </DialogFooter>
    </form>
  );
}

export function PartyEditor({ hooks, open, partyId, onClose, canWrite = false, onSaved, defaultRoles }: PartyEditorProps) {
  const existing = hooks.useParty(open ? partyId : null);
  const title = partyId === null ? t('editor.title_new') : canWrite ? t('editor.title_edit') : t('editor.title_view');

  let body: React.ReactNode;
  if (partyId === null) {
    body = <PartyForm hooks={hooks} party={null} onClose={onClose} canWrite={canWrite} onSaved={onSaved} defaultRoles={defaultRoles} />;
  } else if (existing.showSkeleton) {
    body = <div className="p-6"><ListSkeleton rows={5} /></div>;
  } else if (existing.isError && !existing.data) {
    body = (
      <div className="p-6">
        <RetryError message={`${t('common.error_loading')}: ${errorMessage(existing.error)}`} onRetry={() => existing.refetch()} retryLabel={t('common.retry')} />
      </div>
    );
  } else if (!existing.data) {
    body = <EmptyState message={t('editor.not_found')} />;
  } else {
    // keyed by id + updated_at: a refetch that brings a newer row remounts the form with fresh values
    body = (
      <>
        <RefreshingBar active={existing.isRefreshing} label={t('common.refreshing')} />
        <PartyForm
          key={`${existing.data.id}:${existing.data.updated_at}`}
          hooks={hooks}
          party={existing.data}
          onClose={onClose}
          canWrite={canWrite}
          onSaved={onSaved}
        />
      </>
    );
  }

  return (
    <Dialog open={open} onClose={onClose} title={title} className="max-w-3xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">{title}</h2>
      </DialogHeader>
      {body}
    </Dialog>
  );
}
