/**
 * Finance-local UI helpers on top of the same seed form primitives the commerce organ is drawn
 * with (the shared organ kit: one import seam, no second copy of skeleton / retry / refreshing).
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { t } from './i18n';
import type { EntryStatus } from './types';

export {
  Field,
  FormError,
  EmptyState,
  ErrorState,
  Select,
  Textarea,
  Card,
  Input,
  ListSkeleton,
  RetryError,
  RefreshingBar,
} from '../organ-kit/controls';

/** Entry status as a chip. `overdue` is computed server-side and wins over `open`/`partial`. */
export function EntryStatusChip({ status, overdue }: { status: EntryStatus; overdue?: boolean }) {
  const open = status === 'open' || status === 'partial';
  if (overdue && open) return <Badge variant="destructive">{t('entry_status.overdue')}</Badge>;
  const variant = status === 'paid' ? 'default' : status === 'cancelled' ? 'muted' : 'outline';
  return <Badge variant={variant}>{t(`entry_status.${status}`)}</Badge>;
}

/** Inline two-step confirm (replaces `window.confirm`, which tests and kiosks can't answer). */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  pending,
  variant = 'ghost',
  disabled,
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
  pending?: boolean;
  variant?: 'ghost' | 'outline' | 'destructive';
  disabled?: boolean;
}) {
  const [armed, setArmed] = React.useState(false);
  if (!armed) {
    return (
      <Button size="sm" variant={variant} disabled={disabled} onClick={() => setArmed(true)}>
        {label}
      </Button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        size="sm"
        variant="destructive"
        disabled={pending}
        onClick={async () => {
          try {
            await onConfirm();
          } finally {
            setArmed(false);
          }
        }}
      >
        {confirmLabel ?? t('common.confirm')}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setArmed(false)}>
        {t('common.cancel')}
      </Button>
    </span>
  );
}

/** A "?" that reveals plain-language help inline (keyboard/touch friendly; no hover-only tooltip). */
export function HelpTip({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <span className="inline-block align-middle">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((v) => !v)}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-muted-foreground/40 text-[10px] text-muted-foreground hover:bg-accent"
      >
        ?
      </button>
      {open ? (
        <span role="note" className="mt-1 block max-w-prose rounded-md bg-muted p-2 text-xs font-normal text-foreground">
          {children}
        </span>
      ) : null}
    </span>
  );
}

export function Notice({
  tone = 'info',
  children,
  role,
}: {
  tone?: 'info' | 'warning' | 'critical';
  children: React.ReactNode;
  role?: string;
}) {
  const cls =
    tone === 'critical'
      ? 'border-destructive/40 bg-destructive/10 text-destructive'
      : tone === 'warning'
        ? 'border-amber-500/40 bg-amber-500/10 text-foreground'
        : 'border-border bg-muted text-foreground';
  return (
    <div role={role ?? (tone === 'info' ? 'status' : 'alert')} className={`rounded-md border px-3 py-2 text-sm ${cls}`}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** Previous / next pager shared by the paginated lists. */
export function Pager({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-end gap-2 text-sm">
      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        {t('common.previous')}
      </Button>
      <span>
        {page} / {totalPages}
      </span>
      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        {t('common.next')}
      </Button>
    </div>
  );
}

export function totalPagesOf(pg?: { page_size: number; total: number; total_pages?: number }): number {
  if (!pg) return 1;
  return pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size));
}
