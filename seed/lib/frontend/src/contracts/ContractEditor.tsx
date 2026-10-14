/**
 * `<ContractEditor/>` — create / edit a contract in a dialog; the billing-model fields follow the `billing_model` seam:
 *
 * - `one_time`      value + first due date;
 * - `installments`  total value + number of parcelas + first due date (+ due day);
 * - `recurring`     value per period + periodicity + due day + first due date;
 * - `retainer`      monthly fee + included hours + excess rate per hour + due day + first due date.
 *
 * Lines (services / items) are optional; with lines the value is their sum and the field is derived (read-only).
 * A DRAFT is edited in place; a vigente contract is read-only here and changes through the action bar
 * (aditivo, reajuste, suspender, retomar, encerrar). `canWrite` is UX only — writes are admin-only on the server.
 * Money is integer cents on the wire; the inputs are BRL strings (`organ-kit/money`).
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { centsToInput, formatCents, parseMoneyToCents } from '../organ-kit/money';
import { AmendPanel, ReadjustPanel, SignaturePanel } from './ContractActions';
import { ContractBillingPreview } from './ContractBillingPreview';
import { ContractSuspendDialog } from './ContractSuspendDialog';
import { ContractTerminateDialog } from './ContractTerminateDialog';
import { ContractTimeline } from './ContractTimeline';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select, Textarea } from './controls';
import { contractsErrorText } from './errors';
import { bpToPercent, formatDate, hoursToMinutes, linesTotal, minutesToHours, percentToBp } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import {
  CONTRACT_BILLING_MODELS, CONTRACT_FREQUENCIES, CONTRACT_READJUSTMENT_INDEXES, type Contract, type ContractBillingModel,
  type ContractFrequency, type ContractInput, type ContractLine, type ContractReadjustmentIndex,
} from './types';

export interface ContractEditorProps {
  hooks: ContractsHooks;
  open: boolean;
  /** `null` = create a new contract. */
  contractId: string | null;
  onClose: () => void;
  /** Admin write access (UX only). Default `false` = read-only view. */
  canWrite?: boolean;
  onSaved?: (contract: Contract) => void;
  /** Optional party picker (the parties organ): render a selector that calls `onPick`. Without it the party is typed by name. */
  renderPartyPicker?: (props: { value: string | null; onPick: (party: { id: string; name: string } | null) => void }) => React.ReactNode;
}

interface LineState { description: string; quantity: string; price: string }
interface FormState {
  title: string; number: string; partyId: string | null; partyName: string; partyDoc: string; model: ContractBillingModel;
  amount: string; installments: string; frequency: ContractFrequency; dueDay: string; firstDue: string; start: string; end: string;
  autoRenew: boolean; renewalMonths: string; hours: string; excessRate: string; index: ContractReadjustmentIndex; indexPercent: string;
  indexEvery: string; notice: string; penalty: string; penaltyPercent: string; notes: string; lines: LineState[];
}

function fromContract(c: Contract | null): FormState {
  return {
    title: c?.title ?? '', number: c?.number ?? '', partyId: c?.party_id ?? null, partyName: c?.party_name ?? '', partyDoc: c?.party_doc ?? '',
    model: c?.billing_model ?? 'recurring', amount: c ? centsToInput(c.amount_cents) : '', installments: String(c?.installments_count ?? ''),
    frequency: c?.frequency ?? 'monthly', dueDay: String(c?.due_day ?? ''), firstDue: c?.first_due_date ?? '', start: c?.start_date ?? '',
    end: c?.end_date ?? '', autoRenew: c?.auto_renew ?? false, renewalMonths: String(c?.renewal_months ?? 12), hours: minutesToHours(c?.retainer_minutes),
    excessRate: c?.excess_rate_cents != null ? centsToInput(c.excess_rate_cents) : '', index: c?.readjustment_index ?? 'none',
    indexPercent: c?.readjustment_percent_bp != null ? bpToPercent(c.readjustment_percent_bp) : '', indexEvery: String(c?.readjustment_every_months ?? 12),
    notice: String(c?.notice_days ?? 0), penalty: c?.penalty_cents ? centsToInput(c.penalty_cents) : '', penaltyPercent: c?.penalty_bp ? bpToPercent(c.penalty_bp) : '',
    notes: c?.notes ?? '',
    lines: (c?.lines ?? []).map((l) => ({ description: l.description, quantity: String(l.quantity), price: centsToInput(l.unit_price_cents) })),
  };
}

const AMOUNT_LABEL: Record<ContractBillingModel, string> = {
  one_time: 'editor.amount_one_time', installments: 'editor.amount_installments', recurring: 'editor.amount_recurring', retainer: 'editor.amount_retainer',
};

/** Build the wire body from the form, or the first pt-BR error. Pure (tested directly). */
export function buildContractInput(f: FormState): { input: ContractInput } | { error: string } {
  if (!f.title.trim()) return { error: t('error.title_required') };
  const lines: ContractLine[] = [];
  for (const l of f.lines) {
    const cents = parseMoneyToCents(l.price);
    const qty = Number(l.quantity);
    if (!l.description.trim() || cents === null || !Number.isInteger(qty) || qty < 1) return { error: t('editor.lines') };
    lines.push({ description: l.description.trim(), quantity: qty, unit_price_cents: cents });
  }
  const total = lines.length ? linesTotal(lines) : parseMoneyToCents(f.amount);
  if (total === null || total <= 0) return { error: t('error.amount_required') };
  if (!f.firstDue && !f.start) return { error: t('error.date_required') };
  const input: ContractInput = {
    title: f.title.trim(), billing_model: f.model, number: f.number.trim() || null, party_id: f.partyId,
    party_name: f.partyId ? undefined : f.partyName.trim() || null, first_due_date: f.firstDue || null, start_date: f.start || null,
    end_date: f.end || null, auto_renew: f.autoRenew, renewal_months: Number(f.renewalMonths) || 12, readjustment_index: f.index,
    readjustment_every_months: Number(f.indexEvery) || 12, notice_days: Number(f.notice) || 0, notes: f.notes.trim() || null,
    due_day: f.dueDay ? Number(f.dueDay) : null,
  };
  if (lines.length) input.lines = lines;
  else input.amount_cents = total;
  if (f.partyDoc.trim() && !f.partyDoc.includes('*')) input.party_doc = f.partyDoc.trim();
  if (f.model === 'installments') {
    const n = Number(f.installments);
    if (!Number.isInteger(n) || n < 1) return { error: t('error.installments_required') };
    input.installments_count = n;
  }
  if (f.model === 'recurring') input.frequency = f.frequency;
  if (f.model === 'retainer') {
    const minutes = hoursToMinutes(f.hours);
    const rate = f.excessRate.trim() ? parseMoneyToCents(f.excessRate) : 0;
    if (minutes === null || rate === null) return { error: t('editor.retainer_hours') };
    input.retainer_minutes = minutes;
    input.excess_rate_cents = rate;
  }
  if (f.index === 'fixed') {
    const bp = percentToBp(f.indexPercent);
    if (bp === null) return { error: t('editor.index_percent') };
    input.readjustment_percent_bp = bp;
  }
  const penalty = f.penalty.trim() ? parseMoneyToCents(f.penalty) : 0;
  const penaltyBp = f.penaltyPercent.trim() ? percentToBp(f.penaltyPercent) : 0;
  if (penalty === null || penaltyBp === null) return { error: t('editor.penalty') };
  input.penalty_cents = penalty;
  input.penalty_bp = penaltyBp;
  return { input };
}

interface FormProps extends Omit<ContractEditorProps, 'open' | 'contractId'> {
  contract: Contract | null;
}

function ContractForm({ hooks, contract, onClose, canWrite = false, onSaved, renderPartyPicker }: FormProps) {
  const create = hooks.useCreateContract();
  const update = hooks.useUpdateContract();
  const remove = hooks.useDeleteContract();
  const activate = hooks.useActivateContract();
  const resume = hooks.useResumeContract();
  const [f, setF] = React.useState<FormState>(() => fromContract(contract));
  const [error, setError] = React.useState<string | null>(null);
  const [panel, setPanel] = React.useState<'amend' | 'readjust' | 'signature' | null>(null);
  const [dialog, setDialog] = React.useState<'suspend' | 'terminate' | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const status = contract?.status ?? 'draft';
  const editable = canWrite && status === 'draft';
  const readOnly = !editable;
  const hasLines = f.lines.length > 0;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setF((s) => ({ ...s, [key]: value }));
  const busy = create.isPending || update.isPending || remove.isPending || activate.isPending || resume.isPending;
  const open = contract !== null && canWrite && (status === 'active' || status === 'suspended');
  const done = (c: Contract) => onSaved?.(c);

  async function save() {
    const built = buildContractInput(f);
    if ('error' in built) return setError(built.error);
    setError(null);
    try {
      const saved = contract ? await update.mutateAsync({ id: contract.id, ...built.input }) : await create.mutateAsync(built.input);
      done(saved);
      if (!contract) onClose();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  async function run(fn: () => Promise<Contract | unknown>, closeAfter = false) {
    setError(null);
    try {
      const out = await fn();
      if (out && typeof out === 'object' && 'id' in (out as object)) done(out as Contract);
      if (closeAfter) onClose();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  const amountValue = hasLines ? centsToInput(linesTotal(f.lines.map((l) => ({ quantity: Number(l.quantity) || 0, unit_price_cents: parseMoneyToCents(l.price) ?? 0 })))) : f.amount;

  return (
    <>
      <DialogBody className="space-y-4">
        {contract ? (
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={status === 'active' ? 'default' : status === 'draft' ? 'muted' : 'outline'}>{t(`status.${status}`)}</Badge>
            <Badge variant="outline">{t(`signature.${contract.signature_status}`)}</Badge>
            <span className="text-xs text-muted-foreground">{t('timeline.version', { n: contract.version_n })}</span>
          </div>
        ) : null}
        {!canWrite ? <p className="text-xs text-muted-foreground">{t('editor.read_only')}</p> : status !== 'draft' ? <p className="text-xs text-muted-foreground">{t('editor.vigente_hint')}</p> : null}

        <div className="grid grid-cols-2 gap-3">
          <Field label={t('editor.field_title')} required><Input aria-label={t('editor.field_title')} value={f.title} disabled={status === 'terminated' || status === 'expired' || !canWrite} onChange={(e) => set('title', e.target.value)} /></Field>
          <Field label={t('editor.number')}><Input aria-label={t('editor.number')} value={f.number} disabled={!canWrite} onChange={(e) => set('number', e.target.value)} /></Field>
          {renderPartyPicker && editable ? (
            <div className="col-span-2">{renderPartyPicker({ value: f.partyId, onPick: (p) => setF((s) => ({ ...s, partyId: p?.id ?? null, partyName: p?.name ?? '' })) })}</div>
          ) : (
            <>
              <Field label={t('editor.party_name')}><Input aria-label={t('editor.party_name')} value={f.partyName} disabled={readOnly || !!f.partyId} onChange={(e) => set('partyName', e.target.value)} /></Field>
              <Field label={t('editor.party_doc')}>
                <Input aria-label={t('editor.party_doc')} value={f.partyDoc} disabled={readOnly || !!f.partyId || f.partyDoc.includes('*')} onChange={(e) => set('partyDoc', e.target.value)} />
              </Field>
            </>
          )}
          <Field label={t('editor.model')}>
            <Select aria-label={t('editor.model')} value={f.model} disabled={readOnly} onChange={(e) => set('model', e.target.value as ContractBillingModel)}>
              {CONTRACT_BILLING_MODELS.map((m) => <option key={m} value={m}>{t(`model.${m}`)}</option>)}
            </Select>
          </Field>
          <Field label={hasLines ? t('editor.amount_lines') : t(AMOUNT_LABEL[f.model])} required>
            <Input aria-label={hasLines ? t('editor.amount_lines') : t(AMOUNT_LABEL[f.model])} inputMode="decimal" value={amountValue} disabled={readOnly || hasLines} onChange={(e) => set('amount', e.target.value)} />
          </Field>
          {f.model === 'installments' ? (
            <Field label={t('editor.installments')} required><Input type="number" min={1} max={120} aria-label={t('editor.installments')} value={f.installments} disabled={readOnly} onChange={(e) => set('installments', e.target.value)} /></Field>
          ) : null}
          {f.model === 'recurring' ? (
            <Field label={t('editor.frequency')}>
              <Select aria-label={t('editor.frequency')} value={f.frequency} disabled={readOnly} onChange={(e) => set('frequency', e.target.value as ContractFrequency)}>
                {CONTRACT_FREQUENCIES.map((q) => <option key={q} value={q}>{t(`frequency.${q}`)}</option>)}
              </Select>
            </Field>
          ) : null}
          {f.model === 'retainer' ? (
            <>
              <Field label={t('editor.retainer_hours')} required><Input aria-label={t('editor.retainer_hours')} inputMode="decimal" value={f.hours} disabled={readOnly} onChange={(e) => set('hours', e.target.value)} /></Field>
              <Field label={t('editor.excess_rate')}><Input aria-label={t('editor.excess_rate')} inputMode="decimal" value={f.excessRate} disabled={readOnly} onChange={(e) => set('excessRate', e.target.value)} /></Field>
            </>
          ) : null}
          {f.model !== 'one_time' ? (
            <Field label={t('editor.due_day')}><Input type="number" min={1} max={31} aria-label={t('editor.due_day')} value={f.dueDay} disabled={readOnly} onChange={(e) => set('dueDay', e.target.value)} /></Field>
          ) : null}
          <Field label={t('editor.first_due')} required><Input type="date" aria-label={t('editor.first_due')} value={f.firstDue} disabled={readOnly} onChange={(e) => set('firstDue', e.target.value)} /></Field>
          <Field label={t('editor.start')}><Input type="date" aria-label={t('editor.start')} value={f.start} disabled={readOnly} onChange={(e) => set('start', e.target.value)} /></Field>
          <Field label={t('editor.end')}><Input type="date" aria-label={t('editor.end')} value={f.end} disabled={readOnly} onChange={(e) => set('end', e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.autoRenew} disabled={readOnly} onChange={(e) => set('autoRenew', e.target.checked)} />
            {t('editor.auto_renew')}
          </label>
          {f.model === 'recurring' || f.model === 'retainer' ? (
            <>
              <Field label={t('editor.index')}>
                <Select aria-label={t('editor.index')} value={f.index} disabled={readOnly} onChange={(e) => set('index', e.target.value as ContractReadjustmentIndex)}>
                  {CONTRACT_READJUSTMENT_INDEXES.map((i) => <option key={i} value={i}>{t(`index.${i}`)}</option>)}
                </Select>
              </Field>
              {f.index === 'fixed' ? <Field label={t('editor.index_percent')}><Input aria-label={t('editor.index_percent')} inputMode="decimal" value={f.indexPercent} disabled={readOnly} onChange={(e) => set('indexPercent', e.target.value)} /></Field> : null}
              {f.index !== 'none' ? <Field label={t('editor.index_every')}><Input type="number" min={1} aria-label={t('editor.index_every')} value={f.indexEvery} disabled={readOnly} onChange={(e) => set('indexEvery', e.target.value)} /></Field> : null}
            </>
          ) : null}
          <Field label={t('editor.notice_days')}><Input type="number" min={0} aria-label={t('editor.notice_days')} value={f.notice} disabled={readOnly} onChange={(e) => set('notice', e.target.value)} /></Field>
          <Field label={t('editor.penalty')}><Input aria-label={t('editor.penalty')} inputMode="decimal" value={f.penalty} disabled={readOnly} onChange={(e) => set('penalty', e.target.value)} /></Field>
          <Field label={t('editor.penalty_percent')}><Input aria-label={t('editor.penalty_percent')} inputMode="decimal" value={f.penaltyPercent} disabled={readOnly} onChange={(e) => set('penaltyPercent', e.target.value)} /></Field>
        </div>

        <fieldset className="space-y-2" disabled={readOnly}>
          <legend className="text-sm font-medium">{t('editor.lines')}</legend>
          {f.lines.map((l, i) => (
            <div key={i} className="grid grid-cols-[1fr_5rem_8rem_auto] items-end gap-2">
              <Input aria-label={`${t('editor.line_description')} ${i + 1}`} value={l.description} onChange={(e) => setF((s) => ({ ...s, lines: s.lines.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)) }))} />
              <Input aria-label={`${t('editor.line_quantity')} ${i + 1}`} inputMode="numeric" value={l.quantity} onChange={(e) => setF((s) => ({ ...s, lines: s.lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)) }))} />
              <Input aria-label={`${t('editor.line_price')} ${i + 1}`} inputMode="decimal" value={l.price} onChange={(e) => setF((s) => ({ ...s, lines: s.lines.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)) }))} />
              <Button type="button" size="sm" variant="ghost" aria-label={`${t('editor.line_remove')} ${i + 1}`} onClick={() => setF((s) => ({ ...s, lines: s.lines.filter((_, j) => j !== i) }))}>×</Button>
            </div>
          ))}
          {editable ? <Button type="button" size="sm" variant="outline" onClick={() => setF((s) => ({ ...s, lines: [...s.lines, { description: '', quantity: '1', price: '' }] }))}>{t('editor.line_add')}</Button> : null}
        </fieldset>

        <Field label={t('editor.notes')}><Textarea aria-label={t('editor.notes')} value={f.notes} disabled={!canWrite} onChange={(e) => set('notes', e.target.value)} /></Field>

        {contract && status === 'terminated' ? (
          <p className="text-sm">{t('status.terminated')}: {formatDate(contract.terminated_on)} — {contract.termination_reason}
            {contract.penalty_applied_cents ? ` (${formatCents(contract.penalty_applied_cents)})` : ''}</p>
        ) : null}
        <FormError message={error} />

        {open && contract ? (
          <div className="flex flex-wrap gap-2">
            {status === 'active' ? <Button type="button" variant="outline" onClick={() => setDialog('suspend')}>{t('action.suspend')}</Button> : null}
            {status === 'suspended' ? <Button type="button" variant="outline" disabled={busy} onClick={() => run(() => resume.mutateAsync({ id: contract.id }))}>{t('action.resume')}</Button> : null}
            <Button type="button" variant="outline" onClick={() => setPanel(panel === 'amend' ? null : 'amend')}>{t('action.amend')}</Button>
            {contract.billing_model === 'recurring' || contract.billing_model === 'retainer' ? (
              <Button type="button" variant="outline" onClick={() => setPanel(panel === 'readjust' ? null : 'readjust')}>{t('action.readjust')}</Button>
            ) : null}
            <Button type="button" variant="destructive" onClick={() => setDialog('terminate')}>{t('action.terminate')}</Button>
          </div>
        ) : null}
        {contract && canWrite && status !== 'terminated' && status !== 'expired' ? (
          <Button type="button" size="sm" variant="ghost" onClick={() => setPanel(panel === 'signature' ? null : 'signature')}>{t('action.send_signature')}</Button>
        ) : null}
        {contract && panel === 'amend' ? <AmendPanel hooks={hooks} contract={contract} onDone={() => setPanel(null)} /> : null}
        {contract && panel === 'readjust' ? <ReadjustPanel hooks={hooks} contract={contract} onDone={() => setPanel(null)} /> : null}
        {contract && panel === 'signature' ? <SignaturePanel hooks={hooks} contract={contract} /> : null}

        {contract ? <ContractBillingPreview hooks={hooks} contractId={contract.id} /> : null}
        {contract ? <ContractTimeline hooks={hooks} contractId={contract.id} /> : null}
      </DialogBody>
      <DialogFooter className="items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {contract && canWrite && status === 'draft' ? (
            confirmDelete ? (
              <>
                <span className="text-sm">{t('editor.delete_confirm')}</span>
                <Button type="button" variant="destructive" disabled={busy} onClick={() => run(() => remove.mutateAsync(contract.id), true)}>{t('editor.delete_confirm_yes')}</Button>
                <Button type="button" variant="ghost" onClick={() => setConfirmDelete(false)}>{t('common.cancel')}</Button>
              </>
            ) : (
              <Button type="button" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(true)}>{t('editor.delete')}</Button>
            )
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>{readOnly ? t('common.close') : t('common.cancel')}</Button>
          {contract && canWrite && status === 'draft' ? <Button type="button" variant="outline" disabled={busy} onClick={() => run(() => activate.mutateAsync({ id: contract.id }))}>{t('action.activate')}</Button> : null}
          {editable ? <Button type="button" disabled={busy} onClick={save}>{busy ? t('common.saving') : t('common.save')}</Button> : null}
        </div>
      </DialogFooter>
      {contract && dialog === 'suspend' ? <ContractSuspendDialog hooks={hooks} contractId={contract.id} open onClose={() => setDialog(null)} onDone={done} /> : null}
      {contract && dialog === 'terminate' ? <ContractTerminateDialog hooks={hooks} contract={contract} open onClose={() => setDialog(null)} onDone={done} /> : null}
    </>
  );
}

export function ContractEditor({ hooks, open, contractId, onClose, canWrite = false, onSaved, renderPartyPicker }: ContractEditorProps) {
  const q = hooks.useContract(open ? contractId : null);
  const title = contractId ? t('editor.title_edit') : t('editor.title_new');
  let body: React.ReactNode;
  if (contractId && q.showSkeleton) {
    body = <DialogBody><ListSkeleton rows={6} /></DialogBody>;
  } else if (contractId && q.isError && !q.data) {
    body = <DialogBody><RetryError message={`${t('common.error_loading')}: ${contractsErrorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t('common.retry')} /></DialogBody>;
  } else if (contractId && !q.data) {
    body = <DialogBody><EmptyState message={t('editor.not_found')} /></DialogBody>;
  } else {
    // keyed on id + version: a refetch after an action re-seeds the form from the server's truth.
    body = (
      <>
        <RefreshingBar active={q.isRefreshing} label={t('common.refreshing')} />
        <ContractForm key={`${q.data?.id ?? 'new'}:${q.data?.version_n ?? 0}:${q.data?.status ?? ''}`} hooks={hooks} contract={q.data ?? null} onClose={onClose} canWrite={canWrite} onSaved={onSaved} renderPartyPicker={renderPartyPicker} />
      </>
    );
  }
  return (
    <Dialog open={open} onClose={onClose} title={title} className="max-w-4xl">
      <DialogHeader>{title}</DialogHeader>
      {body}
    </Dialog>
  );
}
