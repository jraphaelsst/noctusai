/**
 * FAQ tab — pt/EN question/answer pairs (contract §2/§6).
 */
import { Trash2 } from 'lucide-react';
import { Button, Input, Textarea } from '@noctusai/lib/design-system';
import type { FaqItem } from '../../../../lib/website';
import type { SettingsTabProps } from './types';

function emptyItem(): FaqItem { return { q: { pt: '', en: '' }, a: { pt: '', en: '' } }; }

export function FaqTab({ draft, onChange }: SettingsTabProps) {
  function patch(index: number, patchFn: (item: FaqItem) => FaqItem) {
    onChange((prev) => ({ ...prev, faq: prev.faq.map((i, idx) => (idx === index ? patchFn(i) : i)) }));
  }

  function remove(index: number) {
    onChange((prev) => ({ ...prev, faq: prev.faq.filter((_, idx) => idx !== index) }));
  }

  function add() {
    onChange((prev) => ({ ...prev, faq: [...prev.faq, emptyItem()] }));
  }

  return (
    <div className="space-y-3">
      {draft.faq.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">Nenhuma pergunta ainda.</p>
      )}
      {draft.faq.map((item, index) => (
        <div key={index} className="space-y-2 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Pergunta {index + 1}
            </span>
            <button
              type="button"
              aria-label={`Remover pergunta ${index + 1}`}
              onClick={() => remove(index)}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Input
              aria-label={`Pergunta pt-BR ${index + 1}`}
              placeholder="Pergunta (pt-BR)"
              value={item.q.pt}
              onChange={(e) => patch(index, (i) => ({ ...i, q: { ...i.q, pt: e.target.value } }))}
            />
            <Input
              aria-label={`Pergunta EN ${index + 1}`}
              placeholder="Pergunta (EN)"
              value={item.q.en}
              onChange={(e) => patch(index, (i) => ({ ...i, q: { ...i.q, en: e.target.value } }))}
            />
            <Textarea
              aria-label={`Resposta pt-BR ${index + 1}`}
              placeholder="Resposta (pt-BR)"
              value={item.a.pt}
              onChange={(e) => patch(index, (i) => ({ ...i, a: { ...i.a, pt: e.target.value } }))}
            />
            <Textarea
              aria-label={`Resposta EN ${index + 1}`}
              placeholder="Resposta (EN)"
              value={item.a.en}
              onChange={(e) => patch(index, (i) => ({ ...i, a: { ...i.a, en: e.target.value } }))}
            />
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" onClick={add}>Adicionar pergunta</Button>
    </div>
  );
}
