/**
 * `<SideDrawer/>` — canonical right-side drawer (slide-over panel).
 *
 * Why: three Lais pages each hand-built a drawer (Conhecimento, Reengajamento,
 * Visitas config). One organ now covers them: title + description, optional
 * status chip, optional "Voltar" back affordance, close X, scrollable body,
 * sticky footer slot for actions, width variants, and a `dirty` guard that asks
 * the seed `useConfirm()` before any close (X, backdrop, Esc, Voltar).
 *
 * Confirm interplay: the drawer is rendered INLINE (no portal) at z-40, below
 * the ConfirmProvider dialog (z-50, mounted at the app root) — so the leave
 * confirm is always clickable. While a confirm is open, Esc / backdrop are
 * ignored by the drawer (the confirm dialog owns them), so a second confirm is
 * never queued on top of the first.
 *
 *   <SideDrawer open={open} onOpenChange={setOpen} title="Configurar" dirty={dirty}
 *     footer={<Button onClick={save}>Salvar</Button>}>…fields…</SideDrawer>
 */
import * as React from 'react';
import { ArrowLeft, X } from 'lucide-react';

import { cn } from '../utils';
import { Button } from '../design-system/ui/Button';
import { useConfirm } from './confirm';

export const SIDE_DRAWER_LEAVE_MESSAGE = 'Sair da edição? As modificações feitas não serão salvas.';

export type SideDrawerWidth = 'sm' | 'md' | 'lg' | 'xl';

const WIDTH_CLASS: Record<SideDrawerWidth, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-2xl',
};

export interface SideDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  /** Accessible name when `title` is not a plain string. */
  ariaLabel?: string;
  description?: React.ReactNode;
  /** Slot next to the title (e.g. an Ativo/Inativo chip). */
  statusChip?: React.ReactNode;
  /** Renders a "Voltar" button before the title; called after the dirty guard. */
  onBack?: () => void;
  backLabel?: string;
  /** Sticky footer slot (action buttons). A function receives `requestClose` (dirty-guarded) for a Cancelar button. */
  footer?: React.ReactNode | ((api: { requestClose: () => void }) => React.ReactNode);
  /** Default `md`. */
  width?: SideDrawerWidth;
  /** Unsaved changes: every close path asks for confirmation first. */
  dirty?: boolean;
  /** Default: "Sair da edição? As modificações feitas não serão salvas." */
  confirmMessage?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  testId?: string;
  className?: string;
  children: React.ReactNode;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function SideDrawer({
  open,
  onOpenChange,
  title,
  ariaLabel,
  description,
  statusChip,
  onBack,
  backLabel = 'Voltar',
  footer,
  width = 'md',
  dirty = false,
  confirmMessage = SIDE_DRAWER_LEAVE_MESSAGE,
  confirmLabel = 'Sair',
  cancelLabel = 'Continuar editando',
  testId = 'side-drawer',
  className,
  children,
}: SideDrawerProps) {
  const confirm = useConfirm();
  const panelRef = React.useRef<HTMLElement>(null);
  const confirmingRef = React.useRef(false);
  const dirtyRef = React.useRef(dirty);
  dirtyRef.current = dirty;
  const pressOriginRef = React.useRef<'backdrop' | 'panel' | null>(null);

  const guard = React.useCallback(async (): Promise<boolean> => {
    if (confirmingRef.current) return false;
    if (!dirtyRef.current) return true;
    confirmingRef.current = true;
    try {
      return await confirm({
        title: confirmMessage,
        confirmLabel,
        cancelLabel,
        tone: 'danger',
      });
    } finally {
      confirmingRef.current = false;
    }
  }, [confirm, confirmMessage, confirmLabel, cancelLabel]);

  const requestClose = React.useCallback(async () => {
    if (await guard()) onOpenChange(false);
  }, [guard, onOpenChange]);

  const requestBack = React.useCallback(async () => {
    if (await guard()) (onBack ?? (() => onOpenChange(false)))();
  }, [guard, onBack, onOpenChange]);

  React.useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    if (panel && !panel.contains(document.activeElement)) {
      (panel.querySelector<HTMLElement>(FOCUSABLE) ?? panel).focus();
    }
    return () => previous?.focus?.();
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !confirmingRef.current) void requestClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, requestClose]);

  if (!open) return null;

  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || confirmingRef.current) return;
    const nodes = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    if (nodes.length === 0) return;
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panelRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const label = ariaLabel ?? (typeof title === 'string' ? title : undefined);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/50"
      data-testid={`${testId}-backdrop`}
      onMouseDown={(e) => {
        pressOriginRef.current = e.target === e.currentTarget ? 'backdrop' : 'panel';
      }}
      onClick={(e) => {
        const fromBackdrop = pressOriginRef.current !== 'panel';
        pressOriginRef.current = null;
        if (e.target === e.currentTarget && fromBackdrop) void requestClose();
      }}
    >
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        data-testid={testId}
        onKeyDown={trapTab}
        className={cn(
          'flex h-full w-full flex-col bg-background shadow-xl outline-none',
          WIDTH_CLASS[width],
          className,
        )}
      >
        <header className="flex items-start justify-between gap-3 border-b border-border p-4">
          <div className="min-w-0 space-y-1">
            {onBack && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="-ml-2 mb-1"
                onClick={() => void requestBack()}
              >
                <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" /> {backLabel}
              </Button>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{title}</h2>
              {statusChip}
            </div>
            {description != null && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Fechar"
            onClick={() => void requestClose()}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto p-4" data-testid={`${testId}-body`}>
          {children}
        </div>
        {footer != null && (
          <footer
            className="flex justify-end gap-2 border-t border-border bg-background p-4"
            data-testid={`${testId}-footer`}
          >
            {typeof footer === 'function' ? footer({ requestClose: () => void requestClose() }) : footer}
          </footer>
        )}
      </aside>
    </div>
  );
}
