/**
 * Rastreamento tab — Plausible/GA4/Meta Pixel ids (contract §2 `tracking`,
 * D8: these only load client-side once an id is set AND consent is
 * granted). The warning text is required per contract §6 — the privacy
 * policy must be updated BEFORE any of these go live.
 */
import { Input, Field } from '@noctusai/lib/design-system';
import type { SettingsTabProps } from './types';

export function TrackingTab({ draft, onChange }: SettingsTabProps) {
  return (
    <div className="space-y-4">
      <p role="alert" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-foreground">
        Atenção: a política de privacidade precisa ser atualizada ANTES de ativar GA4, Meta Pixel ou qualquer outro
        script de terceiros. Os scripts só carregam quando um id está configurado E o visitante deu consentimento
        (nunca por padrão).
      </p>
      <div className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-3">
        <Field label="Plausible / Umami — domínio">
          <Input
            value={draft.tracking.plausible_domain ?? ''}
            placeholder="noctusai.com"
            onChange={(e) =>
              onChange((prev) => ({ ...prev, tracking: { ...prev.tracking, plausible_domain: e.target.value || null } }))
            }
          />
        </Field>
        <Field label="GA4 ID">
          <Input
            value={draft.tracking.ga4_id ?? ''}
            placeholder="G-XXXXXXXXXX"
            onChange={(e) => onChange((prev) => ({ ...prev, tracking: { ...prev.tracking, ga4_id: e.target.value || null } }))}
          />
        </Field>
        <Field label="Meta Pixel ID">
          <Input
            value={draft.tracking.meta_pixel_id ?? ''}
            placeholder="000000000000000"
            onChange={(e) =>
              onChange((prev) => ({ ...prev, tracking: { ...prev.tracking, meta_pixel_id: e.target.value || null } }))
            }
          />
        </Field>
      </div>
    </div>
  );
}
