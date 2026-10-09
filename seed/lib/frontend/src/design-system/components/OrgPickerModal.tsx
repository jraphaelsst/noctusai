/**
 * `<OrgPickerModal/>` — popup where platform staff choose which org to enter.
 *
 * Shown by `<OrgSelectionGate/>` once per login (non-dismissible while the
 * server says `required`), and reopened by "Trocar org" (dismissible).
 * The home org is listed first as "Entrar como NoctusAI (minha org)". Staff
 * without an aal2 session see a 2FA CTA instead of the list (server also
 * refuses with `mfa_required`). While non-dismissible it covers the header, so
 * it carries its own "Sair" (logout) — otherwise a staff user who cannot pick
 * (2FA broken, no licensed org, list error) is trapped (2026-10-09).
 *
 * `OrgPickerModalView` is the pure presentational half; `OrgPickerModal`
 * binds it to `useOrgSelection()`.
 */
import { useState } from 'react';
import { Loader2 } from 'lucide-react';

import type { OrgChoice } from '../../access';
import { env } from '../../env';
import { useOrgSelection } from '../../org-selection';
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
  error: boolean;
  onRetry: () => void;
  onChoose: (orgId: string) => void;
  /** Org id being entered (button spinner). */
  choosingId?: string | null;
  chooseErrorMessage?: string | null;
  /** Shell logout. Shown as "Sair" only while `required` (the modal hides the header's avatar menu). */
  onSignOut?: () => void | Promise<void>;
}

const noop = () => {};

export function OrgPickerModalView(props: OrgPickerModalViewProps) {
  const {
    open, required, onClose, mfaRequired, mfaUrl, choices, loading, error, onRetry,
    onChoose, choosingId = null, chooseErrorMessage = null, onSignOut,
  } = props;
  const busy = choosingId !== null;

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
  } else {
    body = (
      <ul className="space-y-2" data-testid="org-picker-list">
        {choices.map((c) => (
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
      error={sel.choicesError}
      onRetry={sel.refetchChoices}
      onChoose={onChoose}
      choosingId={choosingId}
      chooseErrorMessage={chooseErr}
      onSignOut={onSignOut}
    />
  );
}
