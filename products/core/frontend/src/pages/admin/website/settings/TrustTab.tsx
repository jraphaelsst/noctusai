/**
 * Confiança tab — trust items with icon, pt/EN text, and the
 * `verified_by`/`verified_at` pair required before an item counts as
 * "published" (contract §6 "Trust statements"; §2 public-subset filter
 * strips an item with no `verified_at`).
 */
import { Trash2 } from 'lucide-react';
import { Badge, Button, Input } from '@noctusai/lib/design-system';
import { isTrustItemPublished, type TrustItem } from '../../../../lib/website';
import type { SettingsTabProps } from './types';

function emptyItem(): TrustItem {
  return { key: `trust-${Date.now()}`, icon: 'shield', text: { pt: '', en: '' }, verified_by: null, verified_at: null };
}

export function TrustTab({ draft, onChange }: SettingsTabProps) {
  function patch(key: string, patchFn: (item: TrustItem) => TrustItem) {
    onChange((prev) => ({ ...prev, trust_items: prev.trust_items.map((i) => (i.key === key ? patchFn(i) : i)) }));
  }

  function remove(key: string) {
    onChange((prev) => ({ ...prev, trust_items: prev.trust_items.filter((i) => i.key !== key) }));
  }

  function add() {
    onChange((prev) => ({ ...prev, trust_items: [...prev.trust_items, emptyItem()] }));
  }

  return (
    <div className="space-y-3">
      {draft.trust_items.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">Nenhum item de confiança ainda.</p>
      )}
      {draft.trust_items.map((item) => {
        const published = isTrustItemPublished(item);
        return (
          <div key={item.key} className="space-y-2 rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <Badge variant={published ? 'default' : 'muted'}>{published ? 'Publicado' : 'Rascunho'}</Badge>
              <button
                type="button"
                aria-label={`Remover item ${item.key}`}
                onClick={() => remove(item.key)}
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input
                aria-label="Ícone"
                placeholder="Ícone (ex.: shield)"
                value={item.icon}
                onChange={(e) => patch(item.key, (i) => ({ ...i, icon: e.target.value }))}
              />
              <div />
              <Input
                aria-label="Texto pt-BR"
                placeholder="Texto (pt-BR)"
                value={item.text.pt}
                onChange={(e) => patch(item.key, (i) => ({ ...i, text: { ...i.text, pt: e.target.value } }))}
              />
              <Input
                aria-label="Texto EN"
                placeholder="Texto (EN)"
                value={item.text.en}
                onChange={(e) => patch(item.key, (i) => ({ ...i, text: { ...i.text, en: e.target.value } }))}
              />
              <Input
                aria-label="Verificado por"
                placeholder="Verificado por"
                value={item.verified_by ?? ''}
                onChange={(e) => patch(item.key, (i) => ({ ...i, verified_by: e.target.value || null }))}
              />
              <Input
                aria-label="Verificado em"
                type="date"
                value={item.verified_at ? item.verified_at.slice(0, 10) : ''}
                onChange={(e) =>
                  patch(item.key, (i) => ({
                    ...i,
                    verified_at: e.target.value ? new Date(e.target.value).toISOString() : null,
                  }))
                }
              />
            </div>
          </div>
        );
      })}
      <Button type="button" variant="outline" onClick={add}>Adicionar item</Button>
    </div>
  );
}
