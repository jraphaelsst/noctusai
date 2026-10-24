/**
 * UnsavedChanges — a form that shows a value the server does not have yet MUST say so.
 *
 * The class (social-wiring F91, 2026-10-24): `ImovelCartorioCard` keeps a local
 * draft seeded from the server row and persists it on "Salvar". The operator
 * picked a condomínio, the chip rendered as if applied, they left the page —
 * and the link was gone on reload. Nothing on screen distinguished "typed" from
 * "saved". Five products' cards had hand-rolled their own `dirty` + beforeunload
 * (ImovelCartorioCard, CerebroEditor, CerebroPerguntas, SimecConfigEditor,
 * DreSettingsForm); this is the one shape.
 *
 * ```tsx
 * const [draft, setDraft] = useState(() => toDraft(dados));
 * const { dirty } = useUnsavedChanges(draft, dados ? toDraft(dados) : undefined);
 * ...
 * <UnsavedChangesNotice dirty={dirty} />
 * <Button onClick={salvar}>Salvar</Button>
 * ```
 *
 * - `saved` is the PERSISTED value in the draft's own shape (the same `toDraft`
 *   the draft was seeded with). `undefined` (still loading) ⇒ never dirty.
 * - Comparison is per field (`fields` narrows it) and value-wise: `null`,
 *   `undefined` and `""` are the same "empty" (an input cannot show the difference),
 *   arrays/objects compare structurally.
 * - While dirty, leaving the page (reload / close tab) asks first (`beforeunload`).
 *   In-app close of a drawer/modal is the container's job — pass `dirty` to
 *   `SideDrawer` (`dirty` prop) or `useConfirm`.
 * - A value that should be applied the instant it is picked (a selector whose
 *   chip LOOKS applied) is not a draft at all: persist it on pick (the F91 fix),
 *   and leave the rest of the card to this hook.
 *
 * → KB § PATTERNS/frontend/mutation-cache-writes.md ("Drafts say they are unsaved")
 */
import * as React from 'react';

export interface UseUnsavedChangesOptions<T> {
  /** Compare only these fields (default: every key of `draft` ∪ `saved`). */
  fields?: readonly (keyof T)[];
  /** Ask before leaving the page while dirty (default true). */
  guardNavigation?: boolean;
}

export interface UnsavedChanges<T> {
  dirty: boolean;
  /** The fields whose draft value differs from the saved one. */
  changed: (keyof T)[];
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '';
}

/** Value equality for form fields: empty ≡ empty, structural for arrays / plain objects. */
export function sameFieldValue(a: unknown, b: unknown): boolean {
  if (isEmpty(a) && isEmpty(b)) return true;
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    const bb = b as unknown[];
    return a.length === bb.length && a.every((x, i) => sameFieldValue(x, bb[i]));
  }
  const ka = Object.keys(a as object);
  const kb = Object.keys(b as object);
  const keys = new Set([...ka, ...kb]);
  for (const k of keys) {
    if (!sameFieldValue((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k])) return false;
  }
  return true;
}

/** Which fields of `draft` differ from `saved` (`saved` undefined ⇒ none). */
export function changedFields<T extends object>(
  draft: T,
  saved: T | null | undefined,
  fields?: readonly (keyof T)[],
): (keyof T)[] {
  if (!saved) return [];
  const keys = fields ?? ([...new Set([...Object.keys(draft), ...Object.keys(saved)])] as (keyof T)[]);
  return keys.filter((k) => !sameFieldValue(draft[k], saved[k]));
}

/**
 * Ask before a reload / tab close while `active` — the page-leave half on its own, for a
 * surface whose "unsaved" signal is not a draft-vs-saved comparison (autosave writes still
 * in flight, a custom equality the caller already computes).
 */
export function useBeforeUnloadGuard(active: boolean): void {
  React.useEffect(() => {
    if (!active) return;
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Legacy browsers only show the prompt when returnValue is set.
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [active]);
}

export function useUnsavedChanges<T extends object>(
  draft: T,
  saved: T | null | undefined,
  options: UseUnsavedChangesOptions<T> = {},
): UnsavedChanges<T> {
  const { fields, guardNavigation = true } = options;
  const changed = changedFields(draft, saved, fields);
  const dirty = changed.length > 0;
  useBeforeUnloadGuard(dirty && guardNavigation);
  return { dirty, changed };
}

export const UNSAVED_CHANGES_MESSAGE = 'Alterações não salvas — clique em Salvar.';

export interface UnsavedChangesNoticeProps {
  dirty: boolean;
  /** Default `UNSAVED_CHANGES_MESSAGE`. */
  children?: React.ReactNode;
  className?: string;
  'data-testid'?: string;
}

/** The on-screen half: renders nothing while clean. */
export function UnsavedChangesNotice({
  dirty,
  children,
  className,
  'data-testid': testId = 'unsaved-changes-notice',
}: UnsavedChangesNoticeProps) {
  if (!dirty) return null;
  return (
    <p role="status" data-testid={testId} className={className ?? 'text-sm text-amber-600'}>
      {children ?? UNSAVED_CHANGES_MESSAGE}
    </p>
  );
}
