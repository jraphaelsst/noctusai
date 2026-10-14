/**
 * `<ContractTerminateDialog/>` — terminate with notice. The effective date defaults to today + the contract's notice;
 * choosing an earlier one needs "dispensar aviso" and then a penalty applies (unless waived). The server is the judge of
 * the rule (409 `aviso_previo_nao_cumprido`); the dialog explains it up front and maps the refusal to pt-BR.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { Field, FormError, Input, Textarea } from './controls';
import { contractsErrorText } from './errors';
import { bpToPercent, formatDate } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import { formatCents } from '../organ-kit/money';
import type { Contract } from './types';

export interface ContractTerminateDialogProps {
  hooks: ContractsHooks;
  contract: Pick<Contract, 'id' | 'notice_days' | 'terminable_from' | 'penalty_cents' | 'penalty_bp'>;
  open: boolean;
  onClose: () => void;
  onDone?: (contract: Contract) => void;
}

export function ContractTerminateDialog({ hooks, contract, open, onClose, onDone }: ContractTerminateDialogProps) {
  const terminate = hooks.useTerminateContract();
  const [reason, setReason] = React.useState('');
  const [effective, setEffective] = React.useState(contract.terminable_from);
  const [waiveNotice, setWaiveNotice] = React.useState(false);
  const [waivePenalty, setWaivePenalty] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const early = effective < contract.terminable_from;
  const hasPenalty = contract.penalty_cents > 0 || contract.penalty_bp > 0;

  async function submit() {
    if (!reason.trim()) return setError(t('error.reason_required'));
    setError(null);
    try {
      const c = await terminate.mutateAsync({
        id: contract.id,
        body: { reason: reason.trim(), effective_on: effective || null, waive_notice: early && waiveNotice, waive_penalty: early && waiveNotice && waivePenalty },
      });
      onDone?.(c);
      onClose();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('terminate.title')}>
      <DialogHeader>{t('terminate.title')}</DialogHeader>
      <DialogBody className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {t('terminate.notice', { days: contract.notice_days, date: formatDate(contract.terminable_from) })}
        </p>
        <Field label={t('terminate.effective')}>
          <Input type="date" aria-label={t('terminate.effective')} value={effective} onChange={(e) => setEffective(e.target.value)} />
        </Field>
        {early ? (
          <div className="space-y-1 rounded border p-2 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={waiveNotice} onChange={(e) => setWaiveNotice(e.target.checked)} />
              {t('terminate.waive_notice')}
            </label>
            {waiveNotice && hasPenalty ? (
              <>
                <p className="text-xs text-muted-foreground">
                  {t('terminate.penalty_note', { fixed: formatCents(contract.penalty_cents), percent: bpToPercent(contract.penalty_bp) })}
                </p>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={waivePenalty} onChange={(e) => setWaivePenalty(e.target.checked)} />
                  {t('terminate.waive_penalty')}
                </label>
              </>
            ) : null}
          </div>
        ) : null}
        <Field label={t('terminate.reason')}>
          <Textarea aria-label={t('terminate.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <p className="text-xs text-muted-foreground">{t('terminate.warning')}</p>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter className="justify-end gap-2">
        <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="destructive" onClick={submit} disabled={terminate.isPending}>
          {terminate.isPending ? t('common.working') : t('terminate.submit')}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
