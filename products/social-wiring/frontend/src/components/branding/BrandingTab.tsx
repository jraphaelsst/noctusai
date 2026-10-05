/**
 * Branding tab — brandings grouped by marca (owners are brands), the Branding
 * Template on top, "Novo branding" and "Importar design system".
 *
 * Four states for the list: skeleton / error / empty / data.
 */
import { useState } from "react";

import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@noctusai/lib/design-system";

import { useBrandingOverview, type BrandingSummary } from "@/hooks/useBranding";
import { BrandingView } from "./BrandingView";
import { ImportDesignSystemDialog } from "./ImportDesignSystemDialog";
import { NewBrandingDialog } from "./NewBrandingDialog";

function Row({ b, selected, onSelect }: { b: BrandingSummary; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid={`branding-row-${b.id}`}
      aria-current={selected}
      className={`w-full rounded px-3 py-2 text-left text-sm transition-colors ${
        selected ? "bg-primary/10" : "hover:bg-muted/50"
      }`}
    >
      <div className="font-medium">{b.name}</div>
      <div className="truncate text-xs text-muted-foreground">{b.default_lang}</div>
    </button>
  );
}

export function BrandingTab() {
  const { data, error, showSkeleton, isRefreshing } = useBrandingOverview();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [newOpen, setNewOpen] = useState<{ fromTemplate: boolean; marcaId: string | null } | null>(null);

  const hasAny = !!data && (!!data.template || data.unassigned.length > 0 || data.marcas.length > 0);

  return (
    <div className="space-y-4" data-testid="branding-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Design systems por marca: cores, tipografia, brand book, componentes e ativos.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setImportOpen(true)} data-testid="branding-import-open">
            Importar design system
          </Button>
          <Button size="sm" variant="primary" onClick={() => setNewOpen({ fromTemplate: false, marcaId: null })} data-testid="branding-new-open">
            Novo branding
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
        <nav aria-label="Brandings" aria-busy={isRefreshing} className="space-y-3 rounded-md border p-2">
          {showSkeleton ? (
            <div className="space-y-2" data-testid="branding-list-loading">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : error && !data ? (
            <ErrorState message="Não foi possível carregar os brandings." />
          ) : !hasAny || !data ? (
            <EmptyState message="Nenhuma marca ou branding ainda. Importe um design system ou crie um branding." />
          ) : (
            <>
              {data.template && (
                <div data-testid="branding-group-template" className="space-y-1">
                  <h3 className="px-3 text-xs font-semibold uppercase text-muted-foreground">Modelo</h3>
                  <Row b={data.template} selected={selectedId === data.template.id} onSelect={() => setSelectedId(data.template!.id)} />
                </div>
              )}
              {data.marcas.map((m) => (
                <div key={m.id} data-testid={`branding-group-${m.id}`} className="space-y-1">
                  <h3 className="flex items-center gap-2 px-3 text-xs font-semibold uppercase text-muted-foreground">
                    {m.name}
                    {m.kind && <Badge variant="muted">{m.kind === "pessoa_fisica" ? "pessoa" : m.kind}</Badge>}
                  </h3>
                  {m.brandings.length === 0 ? (
                    <p className="px-3 text-xs text-muted-foreground">Nenhum branding.</p>
                  ) : (
                    m.brandings.map((b) => (
                      <Row key={b.id} b={b} selected={selectedId === b.id} onSelect={() => setSelectedId(b.id)} />
                    ))
                  )}
                </div>
              ))}
              {data.unassigned.length > 0 && (
                <div data-testid="branding-group-unassigned" className="space-y-1">
                  <h3 className="px-3 text-xs font-semibold uppercase text-muted-foreground">Sem marca</h3>
                  {data.unassigned.map((b) => (
                    <Row key={b.id} b={b} selected={selectedId === b.id} onSelect={() => setSelectedId(b.id)} />
                  ))}
                </div>
              )}
            </>
          )}
        </nav>

        <div className="min-w-0 rounded-md border p-4">
          {selectedId ? (
            <BrandingView
              id={selectedId}
              onDeleted={() => setSelectedId(null)}
              onCreateFromTemplate={() => setNewOpen({ fromTemplate: true, marcaId: null })}
            />
          ) : (
            <EmptyState message="Selecione um branding ou crie um novo." />
          )}
        </div>
      </div>

      {importOpen && (
        <ImportDesignSystemDialog
          open
          onClose={() => setImportOpen(false)}
          onImported={(r) => setSelectedId(r.id)}
        />
      )}
      {newOpen && (
        <NewBrandingDialog
          open
          hasTemplate={!!data?.template}
          defaultFromTemplate={newOpen.fromTemplate}
          defaultMarcaId={newOpen.marcaId}
          onClose={() => setNewOpen(null)}
          onCreated={(id) => {
            setNewOpen(null);
            setSelectedId(id);
          }}
        />
      )}
    </div>
  );
}

export default BrandingTab;
