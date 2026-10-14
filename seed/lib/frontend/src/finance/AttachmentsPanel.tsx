/** `<AttachmentsPanel/>` — upload / list / delete an entry's attachments (comprovantes, notas). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { ConfirmButton, EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { formatBytes } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;
export const ATTACHMENT_ACCEPT = '.pdf,.png,.jpg,.jpeg,.xml';

export interface AttachmentsPanelProps {
  hooks: FinanceHooks;
  entryId: string;
  isAdmin?: boolean;
}

export function AttachmentsPanel({ hooks, entryId, isAdmin = false }: AttachmentsPanelProps) {
  const list = hooks.useAttachments(entryId);
  const m = hooks.useAttachmentMutations(entryId);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = React.useState<string | null>(null);

  async function onPick(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    ev.target.value = '';
    if (!file) return;
    if (file.size > ATTACHMENT_MAX_BYTES) {
      setLocalError(t('attachments.too_big'));
      return;
    }
    setLocalError(null);
    try {
      await m.upload.mutateAsync(file);
    } catch {
      // Surfaced below.
    }
  }

  if (list.showSkeleton) return <ListSkeleton rows={2} />;
  if (list.isError && !list.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = list.data ?? [];
  const err = localError ?? (m.upload.error ?? m.remove.error ? errorMessage(m.upload.error ?? m.remove.error) : null);

  return (
    <section className="space-y-2" aria-busy={list.isRefreshing} aria-label={t('attachments.title')}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">{t('attachments.title')}</h4>
        {isAdmin ? (
          <>
            <input
              ref={inputRef}
              type="file"
              accept={ATTACHMENT_ACCEPT}
              className="hidden"
              aria-label={t('attachments.choose')}
              onChange={onPick}
            />
            <Button size="sm" variant="outline" disabled={m.upload.isPending} onClick={() => inputRef.current?.click()}>
              {m.upload.isPending ? t('attachments.uploading') : t('attachments.add')}
            </Button>
          </>
        ) : null}
      </div>
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      <FormError message={err} />
      {rows.length === 0 ? (
        <EmptyState message={t('attachments.empty')} />
      ) : (
        <ul className="divide-y rounded-md border text-sm">
          {rows.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 p-2">
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="truncate underline">
                {a.filename}
              </a>
              <span className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{formatBytes(a.size_bytes)}</span>
                {isAdmin ? (
                  <ConfirmButton
                    label={t('common.remove')}
                    pending={m.remove.isPending}
                    onConfirm={async () => {
                      try {
                        await m.remove.mutateAsync(a.id);
                      } catch {
                        // Surfaced through `m.remove.error`.
                      }
                    }}
                  />
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t('attachments.help')}</p>
    </section>
  );
}
