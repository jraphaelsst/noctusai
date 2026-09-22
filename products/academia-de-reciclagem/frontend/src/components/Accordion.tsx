/**
 * A single expand/collapse section for `/o-projeto` — one per
 * `TOPICOS` entry (`src/content/projeto.ts`).
 *
 * There is no Accordion/Collapsible organ in `@noctusai/lib/design-system`
 * yet (checked via `noctus.dev.find_reusable_component` — the design system
 * only consumes `@radix-ui/react-collapsible` internally, inside
 * `Sidebar.tsx`'s per-group disclosure; it isn't exported as a reusable
 * primitive). This composes the same Radix primitive directly, kept
 * product-local and deliberately small — promote to the seed the moment a
 * second product needs the same shape (DRY N=2 triage), the same reasoning
 * that already promoted this product's former `components/FormControls.tsx`
 * (Card/Textarea/Select/Field/FormError/EmptyState/ErrorState) into
 * `@noctusai/lib/design-system` once the `agents` product needed the same
 * shapes.
 *
 * Uncontrolled by design: `@radix-ui/react-collapsible` has no "one open at
 * a time" group primitive (that's `@radix-ui/react-accordion`, not a
 * platform dependency), and the brief calls for independent expand/collapse
 * per section, not an exclusive accordion. `defaultOpen` exists solely to
 * satisfy a `/o-projeto#<id>` deep link on first mount.
 */
import type { ReactNode } from 'react';
import * as CollapsiblePrimitive from '@radix-ui/react-collapsible';
import { ChevronDown } from 'lucide-react';

export interface AccordionItemProps {
  /** Stable anchor id (`Topico.id`) — also the deep-link target. */
  id: string;
  numero: string;
  titulo: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function AccordionItem({ id, numero, titulo, defaultOpen, children }: AccordionItemProps) {
  const triggerId = `accordion-trigger-${id}`;
  const panelId = `accordion-panel-${id}`;

  return (
    <CollapsiblePrimitive.Root id={id} defaultOpen={defaultOpen} className="accordion-item">
      <CollapsiblePrimitive.Trigger
        id={triggerId}
        className="accordion-trigger"
        aria-controls={panelId}
        data-testid={triggerId}
      >
        <span className="accordion-numero">{numero}</span>
        <span className="accordion-titulo">{titulo}</span>
        <ChevronDown className="accordion-chevron" size={20} aria-hidden="true" />
      </CollapsiblePrimitive.Trigger>
      <CollapsiblePrimitive.Content
        id={panelId}
        role="region"
        aria-labelledby={triggerId}
        className="accordion-panel"
        data-testid={panelId}
      >
        <div className="accordion-panel-inner">{children}</div>
      </CollapsiblePrimitive.Content>
    </CollapsiblePrimitive.Root>
  );
}
