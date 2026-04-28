/**
 * `<AIConsentToggles/>` — full settings-panel component for the X6 LGPD
 * per-feature AI consent catalog. Reads `useConsents()`, mutates via
 * `useUpdateConsent()`. Mounted by the framework's
 * `ConsentSettingsPage` at `/settings/ai`.
 *
 * **Grouping.** Items are grouped by `product` (catalog entries carry a
 * `product` slug). Order: products with the most pending decisions
 * first (so the user sees "what to decide" before "what's already
 * decided"); ties broken by alphabetical product slug for stability.
 *
 * **Toggle states (visual semantics):**
 *   - `granted=true`, `decision_recorded=true` → switch on, no badge.
 *   - `granted=false`, `decision_recorded=true` → switch off, no badge.
 *   - `granted=default_granted`, `decision_recorded=false` → switch
 *     reflects default + small "(padrão)" annotation. LGPD audit-trail
 *     UX: distinguishes "user actively granted" from "user hasn't seen".
 *   - `toggleable=false` → switch disabled + locked icon + rationale
 *     explains why ("infraestrutura essencial — visível para
 *     transparência de uso de tokens").
 *
 * **Empty catalog:** if a product has zero AI features registered, the
 * panel renders an explanatory empty state ("Nenhuma feature de IA
 * registrada por este produto.") rather than null — the page exists
 * for users to manage consent, even if there's nothing to manage today.
 */
import { useMemo } from 'react';
import { Lock, AlertCircle } from 'lucide-react';

import { useConsents, type ConsentItem } from './useConsents';
import { useUpdateConsent } from './useUpdateConsent';

const PRODUCT_LABELS: Record<string, string> = {
  erp: 'ERP Imobiliário',
  pf: 'Finanças Pessoais',
  daily_life: 'Daily Life',
  therapy: 'Terapia',
  mailing: 'Mailing',
  core: 'Core (plataforma)',
  adconnect: 'AdConnect',
};

function productLabel(slug: string | null): string {
  if (!slug) return 'Outros';
  return PRODUCT_LABELS[slug] ?? slug;
}

export interface AIConsentTogglesProps {
  /** Optional className appended to the root container. */
  className?: string;
}

export function AIConsentToggles({ className = '' }: AIConsentTogglesProps) {
  const { data, isLoading, isError, error } = useConsents();
  const update = useUpdateConsent();

  // Group by product, sort sections by descending pending-count then by slug.
  const sections = useMemo(() => {
    if (!data) return [] as Array<{ product: string | null; items: ConsentItem[]; pendingInGroup: number }>;
    const map = new Map<string | null, ConsentItem[]>();
    for (const item of data.items) {
      const arr = map.get(item.product) ?? [];
      arr.push(item);
      map.set(item.product, arr);
    }
    return Array.from(map.entries())
      .map(([product, items]) => ({
        product,
        items: items.slice().sort((a, b) => a.title.localeCompare(b.title, 'pt-BR')),
        pendingInGroup: items.filter((it) => !it.decision_recorded && it.toggleable).length,
      }))
      .sort((a, b) => {
        if (b.pendingInGroup !== a.pendingInGroup) return b.pendingInGroup - a.pendingInGroup;
        return (a.product ?? 'zzz').localeCompare(b.product ?? 'zzz');
      });
  }, [data]);

  if (isLoading) {
    return (
      <div className={`text-sm text-muted-foreground ${className}`}>
        Carregando preferências de IA…
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className={`inline-flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive ${className}`}
      >
        <AlertCircle className="h-4 w-4" aria-hidden="true" />
        <span>{error?.message || 'Não foi possível carregar suas preferências de IA.'}</span>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    // Global /settings/ai page — empty state means no AI features have
    // been registered (yet) by any product whose backend the user can
    // reach. Distinct from "this product has no AI features" (we're
    // not per-product).
    return (
      <div className={`text-sm text-muted-foreground ${className}`}>
        Nenhuma feature de IA registrada — nada para gerenciar no momento.
      </div>
    );
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {sections.map((section) => (
        <section key={section.product ?? '_none'} className="rounded-lg border border-border bg-background">
          <header className="flex items-center justify-between border-b border-border px-4 py-3">
            <h3 className="text-sm font-semibold text-foreground">{productLabel(section.product)}</h3>
            {section.pendingInGroup > 0 && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
                <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
                {section.pendingInGroup} pendente(s)
              </span>
            )}
          </header>
          <ul className="divide-y divide-border">
            {section.items.map((item) => (
              <ToggleRow
                key={item.key}
                item={item}
                onToggle={(granted) => update.mutate({ key: item.key, granted })}
                disabled={update.isPending}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

interface ToggleRowProps {
  item: ConsentItem;
  onToggle: (granted: boolean) => void;
  disabled: boolean;
}

function ToggleRow({ item, onToggle, disabled }: ToggleRowProps) {
  const showDefaultAnnotation = !item.decision_recorded && item.toggleable;
  const isLocked = !item.toggleable;
  const checked = item.granted;
  const switchDisabled = disabled || isLocked;

  return (
    <li className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{item.title}</span>
          {isLocked && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
              title="Recurso de infraestrutura — sempre ativo, visível para transparência de consumo de tokens"
            >
              <Lock className="h-2.5 w-2.5" aria-hidden="true" />
              infraestrutura
            </span>
          )}
          {showDefaultAnnotation && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              padrão
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{item.rationale}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={`${checked ? 'Desativar' : 'Ativar'} ${item.title}`}
        disabled={switchDisabled}
        onClick={() => onToggle(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${
          checked ? 'bg-primary' : 'bg-muted'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-background shadow ring-0 transition-transform ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
          aria-hidden="true"
        />
      </button>
    </li>
  );
}

export default AIConsentToggles;
