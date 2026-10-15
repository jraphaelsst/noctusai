/**
 * `<ConfirmProvider/>` + `useConfirm()` — the canonical replacement for the
 * native `window.confirm()`.
 *
 * Why: the native dialog blocks the renderer thread (browser automation / E2E
 * hang on it), is unstyled, ignores the design system and is inconsistent
 * across browsers. This organ renders the same question with the design-system
 * `Dialog` + `Button` and exposes it as a promise, so call sites keep the
 * exact shape they had:
 *
 *   const confirm = useConfirm();
 *   if (!(await confirm({ title: 'Excluir cliente?', tone: 'danger' }))) return;
 *
 * Mounted ONCE by the seed `createProductApp` — products never wire it.
 *
 * Behaviour: resolves `true` on confirm, `false` on cancel / Esc / backdrop.
 * Concurrent calls queue (FIFO) — a second `confirm()` waits for the first to
 * be answered rather than clobbering it. Focus lands on the confirm button
 * (on the CANCEL button for `tone: 'danger'` so a stray Enter cannot destroy
 * data), Tab is trapped between the two buttons, and focus returns to the
 * previously focused element on close.
 */
import * as React from 'react';

import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';

export interface ConfirmOptions {
  title: string;
  description?: React.ReactNode;
  /** Default "Confirmar". */
  confirmLabel?: string;
  /** Default "Cancelar". */
  cancelLabel?: string;
  /** `danger` styles the confirm button destructive. Default `default`. */
  tone?: 'default' | 'danger';
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

interface Pending {
  id: number;
  options: ConfirmOptions;
  resolve: (value: boolean) => void;
}

const ConfirmContext = React.createContext<ConfirmFn | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [queue, setQueue] = React.useState<Pending[]>([]);
  const seq = React.useRef(0);

  const confirm = React.useCallback<ConfirmFn>(
    (options) =>
      new Promise<boolean>((resolve) => {
        setQueue((q) => [...q, { id: ++seq.current, options, resolve }]);
      }),
    [],
  );

  const current = queue[0] ?? null;

  const currentRef = React.useRef<Pending | null>(null);
  currentRef.current = current;

  const settle = React.useCallback((value: boolean) => {
    const head = currentRef.current;
    if (!head) return;
    head.resolve(value); // idempotent: a double-click resolves once
    setQueue((q) => q.filter((p) => p.id !== head.id));
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {current && <ConfirmDialog key={current.id} pending={current} onSettle={settle} />}
    </ConfirmContext.Provider>
  );
}

function ConfirmDialog({ pending, onSettle }: { pending: Pending; onSettle: (v: boolean) => void }) {
  const { title, description, confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', tone = 'default' } =
    pending.options;
  const danger = tone === 'danger';
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const confirmRef = React.useRef<HTMLButtonElement>(null);
  const cancel = React.useCallback(() => onSettle(false), [onSettle]);

  React.useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    (danger ? cancelRef : confirmRef).current?.focus();
    return () => previous?.focus?.();
  }, [danger]);

  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== 'Tab') return;
    const first = cancelRef.current;
    const last = confirmRef.current;
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <Dialog open onClose={cancel} title={title}>
      <div onKeyDown={trapTab} role="alertdialog" aria-label={title} data-testid="confirm-dialog">
        <DialogHeader>
          <h2 className="text-base font-semibold">{title}</h2>
        </DialogHeader>
        {description != null && (
          <DialogBody>
            <div className="text-sm text-muted-foreground">{description}</div>
          </DialogBody>
        )}
        <DialogFooter className="gap-2">
          <Button ref={cancelRef} type="button" variant="outline" onClick={cancel}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            type="button"
            variant={danger ? 'destructive' : 'primary'}
            onClick={() => onSettle(true)}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </div>
    </Dialog>
  );
}

const NO_PROVIDER = 'confirm() called outside <ConfirmProvider/> (mounted by createProductApp).';
const missingProvider: ConfirmFn = () => Promise.reject(new Error(NO_PROVIDER));

/**
 * Returns `confirm(options) => Promise<boolean>`. Outside a `<ConfirmProvider/>`
 * the returned function REJECTS when called — loud, never a silent fallback to
 * `window.confirm` (that would hide the missing mount and reintroduce the
 * renderer-blocking dialog). It fails at CALL time, not render time, so a
 * consumer's existing render tests (which never click a destructive action)
 * keep working untouched. `createProductApp` mounts the provider; tests that
 * exercise a confirm flow wrap in `<ConfirmProvider>`.
 */
export function useConfirm(): ConfirmFn {
  return React.useContext(ConfirmContext) ?? missingProvider;
}
