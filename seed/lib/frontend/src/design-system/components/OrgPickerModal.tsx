/**
 * `<OrgPickerModal/>` — popup where platform staff, and members with >=2 eligible orgs for
 * this product (owner D1, 2026-10-14), choose which org to enter. ONE picker for both.
 *
 * Shown by `<OrgSelectionGate/>` on every ENTRY into the product (non-dismissible
 * while required — see `org-visit.ts`), and reopened by "Trocar org" (dismissible).
 * Client orgs are listed first; the home org LAST as "Entrar como NoctusAI (minha org)". Staff
 * without an aal2 session see a 2FA CTA instead of the list (server also
 * refuses with `mfa_required`). While non-dismissible it covers the header, so
 * it carries its own "Sair" (logout) — otherwise a staff user who cannot pick
 * (2FA broken, no licensed org, list error) is trapped (2026-10-09).
 *
 * Member view (`memberView`): the server order is kept (their last-active org first), every
 * row names the org and the member's role THERE (owner in A can be a viewer in B), and the
 * org already in use is marked "Atual" on a "Trocar organização". No 2FA (Q1), no NoctusAI label.
 *
 * `OrgPickerModalView` is the pure presentational half; `OrgPickerModal`
 * binds it to `useOrgSelection()`.
 */
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import type { OrgChoice } from '../../access';
import { env } from '../../env';
import { ORG_ROLE_LABELS } from '../../roles';
import { useOrgSelection } from '../../org-selection';
import { setOrgPickerOpen } from '../../org-pin';
import { Button } from '../ui/Button';
import { Dialog, DialogBody, DialogHeader } from '../ui/Dialog';

export interface OrgPickerModalViewProps {
  open: boolean;
  /** Non-dismissible when true (no Escape / backdrop / close button). */
  required: boolean;
  onClose: () => void;
  mfaRequired: boolean;
  /** Core page where the user enrols 2FA. */
  mfaUrl: string;
  choices: OrgChoice[] | undefined;
  loading: boolean;
  /** List visible but choosing not yet allowed (entry DELETE still in flight). */
  chooseBlocked?: boolean;
  error: boolean;
  onRetry: () => void;
  onChoose: (orgId: string) => void;
  /** Org id being entered (button spinner). */
  choosingId?: string | null;
  chooseErrorMessage?: string | null;
  /** Shell logout. Shown as "Sair" only while `required` (the modal hides the header's avatar menu). */
  onSignOut?: () => void | Promise<void>;
  /** A member (not platform staff) is choosing: see the module doc. */
  memberView?: boolean;
  /** Member view: the org this visit is already in (marked "Atual"); `null` on an entry. */
  currentOrgId?: string | null;
}

function roleLabel(role: string | undefined): string | null {
  if (!role) return null;
  return ORG_ROLE_LABELS[role as keyof typeof ORG_ROLE_LABELS] ?? role;
}

const noop = () => {};

export function OrgPickerModalView(props: OrgPickerModalViewProps) {
  const {
    open, required, onClose, mfaRequired, mfaUrl, choices, loading, error, onRetry,
    onChoose, chooseBlocked = false, choosingId = null, chooseErrorMessage = null, onSignOut,
    memberView = false, currentOrgId = null,
  } = props;
  const busy = choosingId !== null || chooseBlocked;

  let body: React.ReactNode;
  if (mfaRequired) {
    body = (
      <div data-testid="org-picker-mfa" className="space-y-3 text-sm">
        <p>Para entrar em outra organização você precisa ativar a verificação em duas etapas (2FA).</p>
        <a
          href={mfaUrl}
          className="inline-flex items-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Configurar 2FA
        </a>
      </div>
    );
  } else if (loading) {
    body = (
      <div data-testid="org-picker-loading" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando organizações...
      </div>
    );
  } else if (error) {
    body = (
      <div data-testid="org-picker-error" className="space-y-3 text-sm">
        <p className="text-destructive">Não foi possível carregar as organizações.</p>
        <Button type="button" onClick={onRetry}>Tentar novamente</Button>
      </div>
    );
  } else if (!choices || choices.length === 0) {
    body = (
      <p data-testid="org-picker-empty" className="text-sm text-muted-foreground">
        Nenhuma organização com licença ativa para este produto.
      </p>
    );
  } else if (memberView) {
    // Server order: the member's last-active org first, then by name.
    body = (
      <ul className="space-y-2" data-testid="org-picker-list">
        {choices.map((c) => {
          const current = c.id === currentOrgId;
          const role = roleLabel(c.org_role);
          return (
            <li key={c.id}>
              <button
                type="button"
                disabled={busy || current}
                aria-current={current ? 'true' : undefined}
                onClick={() => onChoose(c.id)}
                className="flex w-full items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{c.nome}</span>
                  {role && <span className="block text-xs text-muted-foreground">{role}</span>}
                </span>
                {choosingId === c.id
                  ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                  : current && <span className="shrink-0 text-xs text-muted-foreground">Atual</span>}
              </button>
            </li>
          );
        })}
      </ul>
    );
  } else {
    // Client orgs first (server order: by name), the home org LAST (owner 2026-10-12).
    const ordered = [...choices.filter((c) => !c.is_home), ...choices.filter((c) => c.is_home)];
    body = (
      <ul className="space-y-2" data-testid="org-picker-list">
        {ordered.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => onChoose(c.id)}
              className="flex w-full items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50"
            >
              <span>{c.is_home ? 'Entrar como NoctusAI (minha org)' : c.nome}</span>
              {choosingId === c.id && <Loader2 className="h-4 w-4 animate-spin" />}
            </button>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <Dialog open={open} onClose={required ? noop : onClose} title="Escolher organização">
      <DialogHeader>
        <h2 className="text-base font-semibold">Em qual organização deseja entrar?</h2>
        {!required && (
          <button type="button" aria-label="Fechar" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            x
          </button>
        )}
      </DialogHeader>
      <DialogBody>
        {memberView && !mfaRequired && (
          <p className="mb-3 text-sm text-muted-foreground">
            Você participa de mais de uma organização com acesso a este produto.
          </p>
        )}
        {body}
        {chooseErrorMessage && (
          <p role="alert" className="mt-3 text-sm text-destructive">{chooseErrorMessage}</p>
        )}
        {required && onSignOut && (
          <div className="mt-4 flex justify-end border-t border-border pt-3">
            <Button type="button" variant="ghost" disabled={busy} onClick={() => void onSignOut()}>
              Sair
            </Button>
          </div>
        )}
      </DialogBody>
    </Dialog>
  );
}

/** Core's 2FA enrolment page (`/security` in the core SPA). */
export function coreMfaUrl(): string {
  return `${env.CORE_URL.replace(/\/$/, '')}/security`;
}

export function OrgPickerModal({ onSignOut }: { onSignOut?: () => void | Promise<void> } = {}) {
  const sel = useOrgSelection();
  const [choosingId, setChoosingId] = useState<string | null>(null);
  const [chooseErr, setChooseErr] = useState<string | null>(null);

  const open = sel.selection.available && (sel.pickerRequired || sel.pickerForced);
  // Let Radix modals (the card hub) yield while the picker is up — see org-pin.
  useEffect(() => {
    setOrgPickerOpen(open);
    return () => setOrgPickerOpen(false);
  }, [open]);
  const onChoose = (orgId: string) => {
    setChooseErr(null);
    setChoosingId(orgId);
    sel.choose(orgId).catch((err: unknown) => {
      setChoosingId(null);
      setChooseErr(err instanceof Error ? err.message : 'Não foi possível entrar na organização.');
    });
  };

  return (
    <OrgPickerModalView
      open={open}
      required={sel.pickerRequired}
      onClose={sel.closePicker}
      mfaRequired={sel.selection.mfa_required}
      mfaUrl={coreMfaUrl()}
      choices={sel.choices}
      loading={sel.choicesLoading}
      chooseBlocked={sel.chooseBlocked}
      error={sel.choicesError}
      onRetry={sel.refetchChoices}
      onChoose={onChoose}
      choosingId={choosingId}
      chooseErrorMessage={chooseErr}
      onSignOut={onSignOut}
      memberView={sel.memberPicker}
      currentOrgId={sel.selection.selection_id && !sel.pickerRequired ? sel.selection.org?.id ?? null : null}
    />
  );
}
