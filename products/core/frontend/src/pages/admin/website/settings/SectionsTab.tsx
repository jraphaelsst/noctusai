/**
 * Seções tab — one switch per home section key (contract §2 `sections`).
 * `social_proof` is disabled with a hint while `social_proof_items` is
 * empty — the backend refuses `sections.social_proof=true` with 0 items
 * (`422`), so the FE mirrors the same rule instead of round-tripping a
 * guaranteed-failing save.
 */
import type { SectionKey } from '../../../../lib/website';
import type { SettingsTabProps } from './types';

const SECTION_LABEL: Record<SectionKey, string> = {
  audiences: 'Audiências',
  products: 'Produtos',
  custom_builds: 'Projetos sob medida',
  trust: 'Confiança',
  social_proof: 'Prova social',
  pricing: 'Preços',
  news: 'Novidades (v1.1 — desligado por padrão)',
  faq: 'Perguntas frequentes',
  hero_update_card: 'Card de atualização no hero',
};

const SECTION_ORDER: SectionKey[] = [
  'audiences', 'products', 'custom_builds', 'trust', 'social_proof', 'pricing', 'news', 'faq', 'hero_update_card',
];

export function SectionsTab({ draft, onChange }: SettingsTabProps) {
  const socialProofEmpty = draft.social_proof_items.length === 0;

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-4">
      {SECTION_ORDER.map((key) => {
        const disabled = key === 'social_proof' && socialProofEmpty;
        return (
          <div key={key} className="flex items-center justify-between border-b border-border py-2 last:border-b-0">
            <div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label={SECTION_LABEL[key]}
                  checked={draft.sections[key]}
                  disabled={disabled}
                  onChange={(e) =>
                    onChange((prev) => ({ ...prev, sections: { ...prev.sections, [key]: e.target.checked } }))
                  }
                />
                {SECTION_LABEL[key]}
              </label>
              {disabled && (
                <p className="pl-6 text-xs text-muted-foreground">
                  Adicione pelo menos um item em "Prova social" antes de ligar esta seção.
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
