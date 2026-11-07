/**
 * `FunnelActionDialog` — asks first (`confirm`) and/or collects the inputs a schema action declares.
 * Required inputs are validated inline before the request is made.
 */
import * as React from 'react';

import { Button } from '../../../design-system/ui/Button';
import { Input } from '../../../design-system/ui/Input';
import {
  Dialog as RadixDialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../design-system/ui/radix-dialog';
import { Textarea } from '../../../design-system/ui/textarea';
import type { FunnelActionDef } from './types';

export interface FunnelActionDialogProps {
  action: FunnelActionDef | null;
  busy?: boolean;
  error?: string | null;
  onConfirm: (inputs: Record<string, unknown>) => void;
  onCancel: () => void;
}

export function FunnelActionDialog({ action, busy = false, error, onConfirm, onCancel }: FunnelActionDialogProps) {
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [tentou, setTentou] = React.useState(false);

  React.useEffect(() => {
    setValues({});
    setTentou(false);
  }, [action?.code]);

  if (!action) return null;
  const inputs = action.inputs ?? [];

  function confirmar() {
    setTentou(true);
    if (inputs.some((i) => i.required && !(values[i.name] ?? '').trim())) return;
    const out: Record<string, unknown> = {};
    for (const i of inputs) {
      const raw = (values[i.name] ?? '').trim();
      if (raw === '') continue;
      out[i.name] = i.type === 'number' ? Number(raw.replace(',', '.')) : raw;
    }
    onConfirm(out);
  }

  return (
    <RadixDialog open onOpenChange={(next) => { if (!next) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{action.label}</DialogTitle>
          <DialogDescription>{action.confirm ?? 'Preencha para continuar.'}</DialogDescription>
        </DialogHeader>

        {inputs.map((i) => {
          const id = `funnel-action-${action.code}-${i.name}`;
          const invalid = tentou && i.required && !(values[i.name] ?? '').trim();
          const common = {
            id,
            value: values[i.name] ?? '',
            disabled: busy,
            required: i.required,
            'aria-invalid': invalid || undefined,
            'aria-describedby': invalid ? `${id}-erro` : undefined,
          };
          return (
            <div key={i.name} className="space-y-1">
              <label htmlFor={id} className="text-sm font-medium">{i.label}</label>
              {i.type === 'textarea' ? (
                <Textarea {...common} rows={3} onChange={(e) => setValues((v) => ({ ...v, [i.name]: e.target.value }))} />
              ) : (
                <Input
                  {...common}
                  type={i.type === 'number' ? 'text' : (i.type ?? 'text')}
                  inputMode={i.type === 'number' ? 'decimal' : undefined}
                  onChange={(e) => setValues((v) => ({ ...v, [i.name]: e.target.value }))}
                />
              )}
              {invalid && (
                <p id={`${id}-erro`} role="alert" className="text-sm text-destructive">
                  Informe {i.label.toLowerCase()}.
                </p>
              )}
            </div>
          );
        })}

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancelar</Button>
          <Button variant="primary" onClick={confirmar} disabled={busy}>{action.label}</Button>
        </DialogFooter>
      </DialogContent>
    </RadixDialog>
  );
}
