/**
 * `useFunnelActionFlow` — the ONE path for running a schema action, from the board face and from the
 * card dialog: ask first when the action declares `confirm`/`inputs`, otherwise run at once; success
 * is a `toast.success` (the user triggered it), a refusal stays in the dialog.
 */
import * as React from 'react';
import { toast } from 'sonner';

import type { FunnelHooks } from './createFunnelHooks';
import { FunnelActionDialog } from './FunnelActionDialog';
import { parseFunnelError } from './funnelError';
import type { FunnelActionDef, FunnelCard } from './types';

export function useFunnelActionFlow<TCard extends FunnelCard>(hooks: FunnelHooks<TCard>) {
  const [pending, setPending] = React.useState<{ cardId: string; def: FunnelActionDef } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const mutation = hooks.useAction({
    onError: (e) => {
      const msg = parseFunnelError(e).mensagem;
      // With a dialog open the refusal is shown inline; without one it must still be seen.
      if (pending) setError(msg);
      else toast.error('Não foi possível executar a ação', { description: msg });
    },
  });

  const run = (cardId: string, def: FunnelActionDef, inputs?: Record<string, unknown>) => {
    setError(null);
    mutation.mutate(
      { cardId, codigo: def.code, inputs },
      {
        onSuccess: () => {
          setPending(null);
          toast.success(`${def.label}: feito`);
        },
      },
    );
  };

  const start = (cardId: string, def: FunnelActionDef) => {
    if (def.confirm || (def.inputs && def.inputs.length > 0)) {
      setError(null);
      setPending({ cardId, def });
    } else {
      run(cardId, def);
    }
  };

  const dialog = (
    <FunnelActionDialog
      action={pending?.def ?? null}
      busy={mutation.isPending}
      error={error}
      onCancel={() => setPending(null)}
      onConfirm={(inputs) => pending && run(pending.cardId, pending.def, inputs)}
    />
  );

  return { start, dialog, isPending: mutation.isPending };
}
