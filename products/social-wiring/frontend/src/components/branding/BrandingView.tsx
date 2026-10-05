/**
 * BrandingView — one branding: colour tokens per theme, type styles,
 * spacing/radius, brand book, components (sandboxed previews), assets, edit.
 * Four states: skeleton / error / empty-detail / data.
 */
import { useState } from "react";
import { toast } from "sonner";

import { MarkdownRenderer } from "@noctusai/lib/components";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@noctusai/lib/design-system";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBrandingDetail, useDeleteBranding, type BrandingDetail } from "@/hooks/useBranding";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { BrandingAssetsPanel } from "./BrandingAssetsPanel";
import { BrandingComponentsPanel } from "./BrandingComponentsPanel";
import { BrandingEditor } from "./BrandingEditor";
import { ColorTokensPanel, ScalesPanel, TypeTokensPanel } from "./BrandingTokensView";

function NoTokens({ onEdit }: { onEdit: () => void }) {
  return (
    <div className="space-y-2 py-8 text-center" data-testid="branding-no-tokens">
      <EmptyState message="Este branding ainda não tem tokens." />
      <Button size="sm" variant="outline" onClick={onEdit}>
        Editar ou importar um design system
      </Button>
    </div>
  );
}

function BrandBook({ branding }: { branding: BrandingDetail }) {
  if (!branding.brand_book.trim() && branding.sections.length === 0) {
    return <EmptyState message="Brand book vazio." />;
  }
  return (
    <section data-testid="branding-book" className="space-y-6">
      {branding.brand_book.trim() && <MarkdownRenderer content={branding.brand_book} />}
      {branding.sections.map((s) => (
        <div key={s.title} className="space-y-2 border-t pt-4">
          <h3 className="text-base font-semibold">{s.title}</h3>
          <MarkdownRenderer content={s.markdown} />
        </div>
      ))}
    </section>
  );
}

export function BrandingView({
  id,
  onDeleted,
  onCreateFromTemplate,
}: {
  id: string;
  onDeleted: () => void;
  onCreateFromTemplate: () => void;
}) {
  const { data, error, showSkeleton, isRefreshing } = useBrandingDetail(id);
  const del = useDeleteBranding();
  const [tab, setTab] = useState("colors");
  const [themeId, setThemeId] = useState<string | null>(null);

  if (showSkeleton) {
    return (
      <div className="space-y-3" data-testid="branding-view-loading">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (error && !data) return <ErrorState message="Não foi possível carregar o branding." />;
  if (!data) return <EmptyState message="Selecione um branding." />;

  const tokens = data.tokens;
  const activeTheme = themeId ?? tokens?.color.themes[0]?.id ?? "";

  const remove = () => {
    if (!window.confirm(`Remover o branding "${data.name}"? Os arquivos enviados também serão removidos.`)) return;
    del.mutate(id, {
      onSuccess: () => {
        toast.success("Branding removido");
        onDeleted();
      },
      onError: (err) => toast.error(mensagemErroServidor(err, "Falha ao remover o branding")),
    });
  };

  return (
    <article className="space-y-4" data-testid="branding-view" aria-busy={isRefreshing}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{data.name}</h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {data.is_template ? <Badge variant="default">Branding Template</Badge> : null}
            {data.marca && <Badge variant="outline">{data.marca.name}</Badge>}
            {!data.is_template && !data.marca && <Badge variant="muted">sem marca</Badge>}
            <span>{data.default_lang}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {data.is_template && (
            <Button size="sm" variant="primary" onClick={onCreateFromTemplate} data-testid="branding-create-from-template">
              Criar branding a partir do template
            </Button>
          )}
          {!data.is_template && (
            <Button size="sm" variant="ghost" disabled={del.isPending} onClick={remove} data-testid="branding-delete">
              Remover
            </Button>
          )}
        </div>
      </header>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="colors">Cores</TabsTrigger>
          <TabsTrigger value="type">Tipografia</TabsTrigger>
          <TabsTrigger value="scales">Espaçamento e raios</TabsTrigger>
          <TabsTrigger value="book">Brand book</TabsTrigger>
          <TabsTrigger value="components">Componentes ({data.components.length})</TabsTrigger>
          <TabsTrigger value="assets">Ativos ({data.assets.length})</TabsTrigger>
          <TabsTrigger value="edit">Editar</TabsTrigger>
        </TabsList>

        <TabsContent value="colors" className="mt-4">
          {tokens ? (
            <ColorTokensPanel tokens={tokens} themeId={activeTheme} onThemeChange={setThemeId} />
          ) : (
            <NoTokens onEdit={() => setTab("edit")} />
          )}
        </TabsContent>
        <TabsContent value="type" className="mt-4">
          {tokens ? <TypeTokensPanel tokens={tokens} /> : <NoTokens onEdit={() => setTab("edit")} />}
        </TabsContent>
        <TabsContent value="scales" className="mt-4">
          {tokens ? <ScalesPanel tokens={tokens} /> : <NoTokens onEdit={() => setTab("edit")} />}
        </TabsContent>
        <TabsContent value="book" className="mt-4">
          <BrandBook branding={data} />
        </TabsContent>
        <TabsContent value="components" className="mt-4">
          {tokens && tokens.color.themes.length > 1 && (
            <p className="mb-3 text-xs text-muted-foreground">
              Tema das pré-visualizações: {tokens.color.themes.find((t) => t.id === activeTheme)?.name} (troque na aba Cores).
            </p>
          )}
          <BrandingComponentsPanel
            brandingId={data.id}
            tokens={tokens}
            themeId={activeTheme}
            components={data.components}
            assets={data.assets}
          />
        </TabsContent>
        <TabsContent value="assets" className="mt-4">
          <BrandingAssetsPanel brandingId={data.id} assets={data.assets} />
        </TabsContent>
        <TabsContent value="edit" className="mt-4">
          <BrandingEditor key={data.updated_at} branding={data} />
        </TabsContent>
      </Tabs>
    </article>
  );
}
