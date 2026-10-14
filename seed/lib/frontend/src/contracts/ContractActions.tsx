/** Inline panels of a VIGENTE contract: amendment (aditivo), readjustment (preview then apply) and e-signature. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input, Textarea } from './controls';
import { contractsErrorText } from './errors';
import { bpToPercent, formatDate, percentToBp } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import { centsToInput, formatCents, parseMoneyToCents } from '../organ-kit/money';
import type { Contract, ContractReadjustResult } from './types';

interface PanelProps {
  hooks: ContractsHooks;
  contract: Contract;
}

export function AmendPanel({ hooks, contract, onDone }: PanelProps & { onDone: () => void }) {
  const amend = hooks.useAmendContract();
  const finite = contract.billing_model === 'one_time' || contract.billing_model === 'installments';
  const [summary, setSummary] = React.useState('');
  const [amount, setAmount] = React.useState(centsToInput(contract.amount_cents));
  const [end, setEnd] = React.useState(contract.end_date ?? '');
  const [notice, setNotice] = React.useState(String(contract.notice_days));
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    if (!summary.trim()) return setError(t('error.reason_required'));
    const changes: Record<string, unknown> = {};
    if (!finite) {
      const cents = parseMoneyToCents(amount);
      if (cents === null || cents <= 0) return setError(t('error.amount_required'));
      if (cents !== contract.amount_cents) changes.amount_cents = cents;
    }
    if (end && end !== contract.end_date) changes.end_date = end;
    if (Number(notice) !== contract.notice_days) changes.notice_days = Number(notice);
    setError(null);
    try {
      await amend.mutateAsync({ id: contract.id, summary: summary.trim(), changes });
      setSummary('');
      onDone();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  return (
    <section className="space-y-2 rounded border p-3" aria-label={t('amend.title')}>
      <h3 className="text-sm font-semibold">{t('amend.title')}</h3>
      <Field label={t('amend.summary')}><Textarea aria-label={t('amend.summary')} value={summary} onChange={(e) => setSummary(e.target.value)} /></Field>
      <div className="grid grid-cols-3 gap-2">
        {finite ? null : <Field label={t('amend.amount')}><Input aria-label={t('amend.amount')} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>}
        <Field label={t('amend.end')}><Input type="date" aria-label={t('amend.end')} value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        <Field label={t('amend.notice')}><Input type="number" min={0} aria-label={t('amend.notice')} value={notice} onChange={(e) => setNotice(e.target.value)} /></Field>
      </div>
      <FormError message={error} />
      <Button size="sm" onClick={submit} disabled={amend.isPending}>{amend.isPending ? t('common.working') : t('amend.submit')}</Button>
    </section>
  );
}

export function ReadjustPanel({ hooks, contract, onDone }: PanelProps & { onDone: () => void }) {
  const readjust = hooks.useReadjustContract();
  const [percent, setPercent] = React.useState(contract.readjustment_percent_bp != null ? bpToPercent(contract.readjustment_percent_bp) : '');
  const [result, setResult] = React.useState<ContractReadjustResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function run(apply: boolean) {
    const bp = percentToBp(percent);
    if (bp === null && !(contract.readjustment_index === 'fixed' && !percent.trim())) return setError(t('readjust.percent'));
    setError(null);
    try {
      const r = await readjust.mutateAsync({ id: contract.id, percent_bp: bp, apply });
      setResult(r);
      if (apply) onDone();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  return (
    <section className="space-y-2 rounded border p-3" aria-label={t('readjust.title')}>
      <h3 className="text-sm font-semibold">{t('readjust.title')} · {t(`index.${contract.readjustment_index}`)}</h3>
      <p className="text-xs text-muted-foreground">{t('readjust.manual_note')}</p>
      {contract.readjustment_due_on ? <p className="text-xs">{t('readjust.due', { date: formatDate(contract.readjustment_due_on) })}</p> : null}
      <Field label={t('readjust.percent')}><Input aria-label={t('readjust.percent')} inputMode="decimal" value={percent} onChange={(e) => { setPercent(e.target.value); setResult(null); }} /></Field>
      {result ? (
        <p role="status" className="text-sm">
          {t('readjust.result', { before: formatCents(result.amount_cents_before), after: formatCents(result.amount_cents_after) })}
        </p>
      ) : null}
      <FormError message={error} />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => run(false)} disabled={readjust.isPending}>{t('readjust.preview')}</Button>
        <Button size="sm" onClick={() => run(true)} disabled={readjust.isPending || !result || result.applied}>{t('readjust.apply')}</Button>
      </div>
    </section>
  );
}

export function SignaturePanel({ hooks, contract }: PanelProps) {
  const render = hooks.useRenderDocument();
  const send = hooks.useSendSignature();
  const sync = hooks.useSyncSignature();
  const [signer, setSigner] = React.useState({ name: contract.party_name ?? '', email: '', cpf: '' });
  const [error, setError] = React.useState<string | null>(null);
  const pending = contract.signature_status === 'pendente' || contract.signature_status === 'parcial';
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  };

  return (
    <section className="space-y-2 rounded border p-3" aria-label={t('action.send_signature')}>
      <h3 className="text-sm font-semibold">{t(`signature.${contract.signature_status}`)}</h3>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={render.isPending} onClick={() => run(() => render.mutateAsync({ id: contract.id, body: {} }))}>{t('action.render')}</Button>
        {pending ? <Button size="sm" variant="outline" disabled={sync.isPending} onClick={() => run(() => sync.mutateAsync({ id: contract.id }))}>{t('action.sync_signature')}</Button> : null}
      </div>
      {!pending && contract.signature_status !== 'concluido' ? (
        <div className="grid grid-cols-3 gap-2">
          <Input aria-label="Nome do signatário" placeholder="Nome" value={signer.name} onChange={(e) => setSigner({ ...signer, name: e.target.value })} />
          <Input aria-label="E-mail do signatário" placeholder="E-mail" value={signer.email} onChange={(e) => setSigner({ ...signer, email: e.target.value })} />
          <Input aria-label="CPF do signatário" placeholder="CPF" value={signer.cpf} onChange={(e) => setSigner({ ...signer, cpf: e.target.value })} />
          <div className="col-span-3">
            <Button size="sm" disabled={send.isPending} onClick={() => run(() => send.mutateAsync({ id: contract.id, body: { signers: [signer] } }))}>{t('action.send_signature')}</Button>
          </div>
        </div>
      ) : null}
      {contract.signature_link ? <a className="text-sm underline" href={contract.signature_link} target="_blank" rel="noreferrer">{contract.signature_link}</a> : null}
      <FormError message={error} />
    </section>
  );
}
