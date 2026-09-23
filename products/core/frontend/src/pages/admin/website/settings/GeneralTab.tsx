/**
 * Geral tab — `site_enabled` kill switch, `signup_enabled` (admin-only),
 * WhatsApp number + default prefill message pt/EN + floating-button toggle
 * (contract §6 "Site" / "Conversion").
 *
 * `site_enabled`/`signup_enabled` are the two admin-only, high-blast-radius
 * switches — flipping either goes through a confirm dialog before it lands
 * in the shared draft (brief: "confirmation dialog before toggling
 * site_enabled off/on or signup_enabled").
 */
import { useState } from 'react';
import { Dialog, DialogHeader, DialogBody, DialogFooter, Button, Field, Input } from '@noctusai/lib/design-system';
import type { SettingsTabProps } from './types';

type PendingToggle = { field: 'site_enabled' | 'signup_enabled'; nextValue: boolean } | null;

const CONFIRM_COPY: Record<'site_enabled' | 'signup_enabled', { title: string; body: (next: boolean) => string }> = {
  site_enabled: {
    title: 'Site',
    body: (next) =>
      next
        ? 'Ligar o site voltará a servir as páginas públicas no lugar da landing legada. Continuar?'
        : 'Desligar o site derruba as páginas públicas e volta a servir a landing legada em todas as rotas. Continuar?',
  },
  signup_enabled: {
    title: 'Cadastro',
    body: (next) =>
      next
        ? 'Ligar o cadastro volta a aceitar novos usuários por /login. Continuar?'
        : 'Desligar o cadastro fecha novos cadastros (POST /api/auth/signup passa a responder 403) e troca os CTAs pela lista de espera. Continuar?',
  },
};

export function GeneralTab({ draft, onChange, isMarketing }: SettingsTabProps) {
  const [pending, setPending] = useState<PendingToggle>(null);

  function requestToggle(field: 'site_enabled' | 'signup_enabled', nextValue: boolean) {
    setPending({ field, nextValue });
  }

  function confirmToggle() {
    if (!pending) return;
    const { field, nextValue } = pending;
    onChange((prev) => ({ ...prev, [field]: nextValue }));
    setPending(null);
  }

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h2 className="font-semibold text-foreground">Site</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Site habilitado"
            checked={draft.site_enabled}
            disabled={isMarketing}
            onChange={(e) => requestToggle('site_enabled', e.target.checked)}
          />
          Site habilitado (desligar volta para a landing legada)
        </label>
        {isMarketing && (
          <p className="text-xs text-muted-foreground">Apenas administradores podem alterar este campo.</p>
        )}
      </section>

      <section className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h2 className="font-semibold text-foreground">Conversão</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Cadastro habilitado"
            checked={draft.signup_enabled}
            disabled={isMarketing}
            onChange={(e) => requestToggle('signup_enabled', e.target.checked)}
          />
          Cadastro habilitado (desligar troca os CTAs pela lista de espera)
        </label>
        {isMarketing && (
          <p className="text-xs text-muted-foreground">Apenas administradores podem alterar este campo.</p>
        )}

        <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
          <Field label="Número do WhatsApp (E.164)">
            <Input
              value={draft.whatsapp.number_e164 ?? ''}
              placeholder="+5511999999999"
              onChange={(e) =>
                onChange((prev) => ({ ...prev, whatsapp: { ...prev.whatsapp, number_e164: e.target.value || null } }))
              }
            />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input
              type="checkbox"
              checked={draft.whatsapp.float_enabled}
              onChange={(e) =>
                onChange((prev) => ({ ...prev, whatsapp: { ...prev.whatsapp, float_enabled: e.target.checked } }))
              }
            />
            Botão flutuante de WhatsApp
          </label>
          <Field label="Mensagem padrão (pt-BR)">
            <Input
              value={draft.whatsapp.default_message.pt}
              onChange={(e) =>
                onChange((prev) => ({
                  ...prev,
                  whatsapp: { ...prev.whatsapp, default_message: { ...prev.whatsapp.default_message, pt: e.target.value } },
                }))
              }
            />
          </Field>
          <Field label="Mensagem padrão (EN)">
            <Input
              value={draft.whatsapp.default_message.en}
              onChange={(e) =>
                onChange((prev) => ({
                  ...prev,
                  whatsapp: { ...prev.whatsapp, default_message: { ...prev.whatsapp.default_message, en: e.target.value } },
                }))
              }
            />
          </Field>
        </div>
      </section>

      <Dialog open={!!pending} onClose={() => setPending(null)} title={pending ? CONFIRM_COPY[pending.field].title : undefined}>
        {pending && (
          <>
            <DialogHeader>
              <h3 className="font-semibold text-foreground">{CONFIRM_COPY[pending.field].title}</h3>
            </DialogHeader>
            <DialogBody>
              <p className="text-sm text-foreground">{CONFIRM_COPY[pending.field].body(pending.nextValue)}</p>
            </DialogBody>
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setPending(null)}>Cancelar</Button>
              <Button variant="primary" onClick={confirmToggle}>Confirmar</Button>
            </DialogFooter>
          </>
        )}
      </Dialog>
    </div>
  );
}
