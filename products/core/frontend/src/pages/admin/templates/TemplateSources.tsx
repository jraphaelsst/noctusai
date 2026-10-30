/** "Fontes": read-only discovery of template-like assets that live outside the DB (where they live, nothing editable). */
import { QueryErrorState } from '@noctusai/lib';
import { Skeleton } from '@noctusai/lib/design-system';

import { useTemplateSources } from '../../../hooks/useTemplates';
import { KIND_LABEL, KIND_ORDER, type TemplateFilters } from '../../../lib/templates-contract';

export function TemplateSources({ filters, grouped = false }: { filters: TemplateFilters; grouped?: boolean }) {
  const query = useTemplateSources(filters);
  if (query.isPending && !query.data) return <div data-testid="sources-loading"><Skeleton className="h-16 w-full" /></div>;
  if (!query.data) return <QueryErrorState query={query} title="Não foi possível carregar as fontes" />;
  if (query.data.length === 0) return <p className="text-sm text-muted-foreground" data-testid="sources-empty">Nenhuma fonte catalogada neste escopo.</p>;
  const kinds = KIND_ORDER.filter((k) => query.data!.some((s) => s.kind === k));
  return (
    <div className="space-y-5" data-testid="template-sources">
      {(grouped ? kinds : [null]).map((k) => (
        <div key={k ?? 'all'}>
          {k && <h4 className="mb-2 text-sm font-semibold text-foreground">{KIND_LABEL[k]}</h4>}
          <ul className="divide-y divide-border rounded-md border border-border">
            {query.data!.filter((s) => !k || s.kind === k).map((s) => (
              <li key={s.path} className="px-3 py-2 text-sm">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-foreground">{s.title}</span>
                  <span className="text-xs text-muted-foreground">{s.product ?? 'plataforma'}</span>
                </div>
                <p className="text-xs text-muted-foreground">{s.description}</p>
                <code className="text-xs text-foreground">{s.path}</code>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
