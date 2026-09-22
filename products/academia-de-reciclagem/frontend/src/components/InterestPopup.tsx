/**
 * The public "receber futuras comunicações?" popup — `projects/
 * interessados-CONTRACT.md` § Frontend obligations.
 *
 * Mounted once per public page (`Landing`, `OProjeto`, `ACarta`) inside
 * their `.academia-landing` scope, so the seed `Dialog`/`Button`/`Input`
 * primitives it's built from pick up the landing's own palette — those
 * primitives are styled entirely off the shared `--background`/`--primary`/
 * etc. custom properties (`design-system/tokens.css`), which
 * `.academia-landing` (`pages/landing.css`) re-assigns for its whole
 * subtree. No bespoke "popup CSS" needed for that reason.
 *
 * Storage is READ/WRITTEN INSIDE try/catch throughout (private-mode /
 * quota-exceeded browsers throw on `localStorage` access) — a storage
 * failure degrades to "always show the popup again next visit", never a
 * crash.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useLocation } from 'react-router-dom';

import {
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  Field,
  FormError,
  Input,
} from '@noctusai/lib/design-system';
import { isValidPhone } from '@noctusai/lib';
import { createInteressado } from '@/lib/api';
import { ApiError, errorMessage } from '@/lib/errors';

const STORAGE_KEY = 'academia:interessados-popup';
const SHOW_DELAY_MS = 3500;
const SUPPRESS_DAYS = 30;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface PopupState {
  /** epoch ms — a temporary dismissal ("X" / Esc / "Agora não"). */
  suppressUntil?: number;
  /** a successful submit — suppressed forever, no `suppressUntil` needed. */
  submitted?: boolean;
}

function readState(): PopupState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PopupState) : {};
  } catch {
    return {};
  }
}

function writeState(state: PopupState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage unavailable — the popup just won't remember the dismissal
    // across visits. Non-fatal: it never blocks the visitor from the page.
  }
}

function shouldShowOnMount(): boolean {
  const state = readState();
  if (state.submitted) return false;
  if (state.suppressUntil && Date.now() < state.suppressUntil) return false;
  return true;
}

interface FieldErrorState {
  field?: 'nome' | 'whatsapp' | 'email';
  message: string;
}

export function InterestPopup() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success'>('idle');
  const [fieldError, setFieldError] = useState<FieldErrorState | null>(null);
  const [nome, setNome] = useState('');
  const [whatsapp, setWhatsapp] = useState('');
  const [email, setEmail] = useState('');
  const originRef = useRef(location.pathname);

  // Mount-only: the popup's visibility decision is made once per page load,
  // not re-evaluated as the visitor navigates client-side.
  useEffect(() => {
    if (!shouldShowOnMount()) return;
    const timer = window.setTimeout(() => setOpen(true), SHOW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);

  function dismiss() {
    setOpen(false);
    writeState({ ...readState(), suppressUntil: Date.now() + SUPPRESS_DAYS * 24 * 60 * 60 * 1000 });
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFieldError(null);

    const trimmedNome = nome.trim();
    if (trimmedNome.length < 2) {
      setFieldError({ field: 'nome', message: 'Informe seu nome.' });
      return;
    }
    if (!isValidPhone(whatsapp)) {
      setFieldError({ field: 'whatsapp', message: 'Número de WhatsApp inválido.' });
      return;
    }
    const trimmedEmail = email.trim();
    if (!EMAIL_RE.test(trimmedEmail)) {
      setFieldError({ field: 'email', message: 'E-mail inválido.' });
      return;
    }

    setStatus('submitting');
    createInteressado({
      nome: trimmedNome,
      whatsapp,
      email: trimmedEmail,
      consentimento: true,
      origem: originRef.current,
    })
      .then(() => {
        writeState({ submitted: true });
        setStatus('success');
      })
      .catch((err: unknown) => {
        setStatus('idle');
        if (err instanceof ApiError && err.status === 429) {
          setFieldError({ message: 'Muitas tentativas. Tente novamente em alguns minutos.' });
          return;
        }
        const field = err instanceof ApiError ? (err.body as { field?: string } | undefined)?.field : undefined;
        setFieldError({
          field: field === 'nome' || field === 'whatsapp' || field === 'email' ? field : undefined,
          message: errorMessage(err),
        });
      });
  }

  if (!open) return null;

  return (
    <div className="academia-landing">
      <Dialog open onClose={dismiss} title="Receber futuras comunicações" className="max-w-md">
        {status === 'success' ? (
          <>
            <DialogHeader>
              <h2 className="text-lg font-semibold text-foreground">Obrigado!</h2>
            </DialogHeader>
            <DialogBody>
              <p data-testid="popup-success" className="text-sm text-muted-foreground">
                Você vai receber as próximas comunicações da Academia da Reciclagem no e-mail e WhatsApp informados.
              </p>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="primary" onClick={() => setOpen(false)} data-testid="button-popup-done">
                Fechar
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={handleSubmit} data-testid="form-interessado">
            <DialogHeader>
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  Gostaria de receber futuras comunicações?
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Usamos esses dados só para enviar novidades da Academia da Reciclagem. Ao enviar, você concorda em
                  receber essas mensagens.
                </p>
              </div>
              <button
                type="button"
                aria-label="Fechar"
                data-testid="button-popup-close"
                onClick={dismiss}
                className="text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </DialogHeader>
            <DialogBody className="space-y-3">
              <FormError message={fieldError && !fieldError.field ? fieldError.message : null} />
              <Field label="Nome" required error={fieldError?.field === 'nome' ? fieldError.message : null}>
                <Input
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  data-testid="input-nome"
                  autoComplete="name"
                  required
                />
              </Field>
              <Field label="WhatsApp" required error={fieldError?.field === 'whatsapp' ? fieldError.message : null}>
                <Input
                  value={whatsapp}
                  onChange={(e) => setWhatsapp(e.target.value)}
                  data-testid="input-whatsapp"
                  placeholder="(11) 98765-4321"
                  autoComplete="tel"
                  required
                />
              </Field>
              <Field label="E-mail" required error={fieldError?.field === 'email' ? fieldError.message : null}>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="input-email"
                  autoComplete="email"
                  required
                />
              </Field>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={dismiss} data-testid="button-popup-later">
                Agora não
              </Button>
              <Button type="submit" variant="primary" disabled={status === 'submitting'} data-testid="button-popup-submit">
                Quero receber
              </Button>
            </DialogFooter>
          </form>
        )}
      </Dialog>
    </div>
  );
}
