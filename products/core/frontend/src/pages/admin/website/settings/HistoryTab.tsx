/**
 * Histórico tab — versions list (`GET .../settings/history`) + rollback
 * (admin only, `POST .../settings/rollback` 🔒). Owns its own query/mutation
 * (unlike the other tabs, which edit the shared draft) — history is a
 * read+act surface, not a form field.
 */
import { useState } from 'react';
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, Skeleton } from '@noctusai/lib/design-system';
import {
  formatDateTime,
  useRollbackWebsiteSettings,
  useWebsiteSettingsHistory,
  type WebsiteSettingsHistoryEntry,
} from '../../../../lib/website';

export interface HistoryTabProps {
  isMarketing: boolean;
  currentVersion: number;
}

export function HistoryTab({ isMarketing, currentVersion }: HistoryTabProps) {
  const { data, isPending, isFetching, error } = useWebsiteSettingsHistory();
  const rollback = useRollbackWebsiteSettings();
  const [pending, setPending] = useState<WebsiteSettingsHistoryEntry | null>(null);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (error && !data) {
    return <p role="alert" className="text-sm text-destructive">{error.message}</p>;
  }
  if (!data || data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Nenhuma versão salva ainda.</p>;
  }

  return (
    <div className="space-y-2" aria-busy={isRefreshing}>
      {rollback.error && (
        <p role="alert" className="text-sm text-destructive">{rollback.error.message}</p>
      )}
      {rollback.isSuccess && !pending && (
        <p className="text-sm text-muted-foreground">Revertido — uma nova versão foi criada a partir da anterior.</p>
      )}
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr><th className="p-2">Versão</th><th>Criada em</th><th>Criada por</th><th>Ações</th></tr>
          </thead>
          <tbody>
            {data.map((entry) => (
              <tr key={entry.version} className="border-t border-border">
                <td className="p-2">
                  {entry.version}
                  {entry.version === currentVersion && <Badge className="ml-2" variant="default">atual</Badge>}
                </td>
                <td>{formatDateTime(entry.created_at)}</td>
                <td>{entry.created_by ?? '—'}</td>
                <td className="py-2">
                  {!isMarketing && entry.version !== currentVersion && (
                    <Button size="sm" variant="outline" onClick={() => setPending(entry)}>Reverter</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!pending} onClose={() => setPending(null)} title="Reverter versão">
        {pending && (
          <>
            <DialogHeader><h3 className="font-semibold text-foreground">Reverter para a versão {pending.version}</h3></DialogHeader>
            <DialogBody>
              <p className="text-sm text-foreground">
                Isto cria uma NOVA versão com o conteúdo da versão {pending.version} de {formatDateTime(pending.created_at)}.
                Continuar?
              </p>
            </DialogBody>
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setPending(null)}>Cancelar</Button>
              <Button
                variant="primary"
                disabled={rollback.isPending}
                onClick={() => rollback.mutate(pending.version, { onSuccess: () => setPending(null) })}
              >
                Confirmar
              </Button>
            </DialogFooter>
          </>
        )}
      </Dialog>
    </div>
  );
}
