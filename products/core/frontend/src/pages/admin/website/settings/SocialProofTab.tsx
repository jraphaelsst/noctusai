/**
 * Prova social tab — logos / testimonials / metrics, each requiring a
 * `consent_ref` (who approved, when, document link — contract §2/§6). The
 * "Seções" tab disables `sections.social_proof` while this list is empty,
 * so this is the tab that unblocks it.
 */
import { Trash2 } from 'lucide-react';
import { Button, Input } from '@noctusai/lib/design-system';
import type { SocialProofItem, SocialProofKind } from '../../../../lib/website';
import type { SettingsTabProps } from './types';

const KIND_LABEL: Record<SocialProofKind, string> = { logo: 'Logo', testimonial: 'Depoimento', metric: 'Métrica' };

function emptyItem(): SocialProofItem { return { kind: 'logo', name: '', consent_ref: '' }; }

export function SocialProofTab({ draft, onChange }: SettingsTabProps) {
  function patch(index: number, patchFn: (item: SocialProofItem) => SocialProofItem) {
    onChange((prev) => ({
      ...prev,
      social_proof_items: prev.social_proof_items.map((i, idx) => (idx === index ? patchFn(i) : i)),
    }));
  }

  function remove(index: number) {
    onChange((prev) => ({ ...prev, social_proof_items: prev.social_proof_items.filter((_, idx) => idx !== index) }));
  }

  function add() {
    onChange((prev) => ({ ...prev, social_proof_items: [...prev.social_proof_items, emptyItem()] }));
  }

  return (
    <div className="space-y-3">
      {draft.social_proof_items.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">Nenhum item de prova social ainda.</p>
      )}
      {draft.social_proof_items.map((item, index) => {
        const missingConsent = !item.consent_ref.trim();
        return (
          <div key={index} className="space-y-2 rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <select
                aria-label="Tipo"
                className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                value={item.kind}
                onChange={(e) => patch(index, (i) => ({ ...i, kind: e.target.value as SocialProofKind }))}
              >
                {(Object.keys(KIND_LABEL) as SocialProofKind[]).map((k) => (
                  <option key={k} value={k}>{KIND_LABEL[k]}</option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`Remover item ${index + 1}`}
                onClick={() => remove(index)}
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input
                aria-label="Nome"
                placeholder="Nome (empresa/pessoa/métrica)"
                value={item.name}
                onChange={(e) => patch(index, (i) => ({ ...i, name: e.target.value }))}
              />
              <Input
                aria-label="URL da imagem"
                placeholder="URL da imagem — opcional"
                value={item.image_url ?? ''}
                onChange={(e) => patch(index, (i) => ({ ...i, image_url: e.target.value || undefined }))}
              />
              <Input
                aria-label="Texto pt-BR"
                placeholder="Texto (pt-BR) — depoimento/métrica"
                value={item.text?.pt ?? ''}
                onChange={(e) => patch(index, (i) => ({ ...i, text: { pt: e.target.value, en: i.text?.en ?? '' } }))}
              />
              <Input
                aria-label="Texto EN"
                placeholder="Texto (EN)"
                value={item.text?.en ?? ''}
                onChange={(e) => patch(index, (i) => ({ ...i, text: { pt: i.text?.pt ?? '', en: e.target.value } }))}
              />
              <Input
                aria-label="Referência de consentimento"
                placeholder="Referência de consentimento (quem aprovou, quando, link)"
                value={item.consent_ref}
                onChange={(e) => patch(index, (i) => ({ ...i, consent_ref: e.target.value }))}
                className={missingConsent ? 'border-destructive' : undefined}
              />
            </div>
            {missingConsent && (
              <p className="text-xs text-destructive">
                Uma referência de consentimento é obrigatória para exibir este item.
              </p>
            )}
          </div>
        );
      })}
      <Button type="button" variant="outline" onClick={add}>Adicionar item</Button>
    </div>
  );
}
