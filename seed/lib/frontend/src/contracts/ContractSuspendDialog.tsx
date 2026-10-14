/** `<ContractSuspendDialog/>` — suspend an active contract with a reason. Periods due while suspended are not billed. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { Field, FormError, Textarea } from './controls';
import { contractsErrorText } from './errors';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import type { Contract } from './types';

export interface ContractSuspendDialogProps {
  hooks: ContractsHooks;
  contractId: string;
  open: boolean;
  onClose: () => void;
  onDone?: (contract: Contract) => void;
}

export function ContractSuspendDialog({ hooks, contractId, open, onClose, onDone }: ContractSuspendDialogProps) {
  const suspend = hooks.useSuspendContract();
  const [reason, setReason] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    if (!reason.trim()) return setError(t('error.reason_required'));
    setError(null);
    try {
      const c = await suspend.mutateAsync({ id: contractId, body: { reason: reason.trim() } });
      onDone?.(c);
      onClose();
    } catch (err) {
      setError(contractsErrorText(err));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('suspend.title')}>
      <DialogHeader>{t('suspend.title')}</DialogHeader>
      <DialogBody className="space-y-3">
        <p className="text-sm text-muted-foreground">{t('suspend.note')}</p>
        <Field label={t('suspend.reason')}>
          <Textarea aria-label={t('suspend.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter className="justify-end gap-2">
        <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={submit} disabled={suspend.isPending}>{suspend.isPending ? t('common.working') : t('suspend.submit')}</Button>
      </DialogFooter>
    </Dialog>
  );
}
