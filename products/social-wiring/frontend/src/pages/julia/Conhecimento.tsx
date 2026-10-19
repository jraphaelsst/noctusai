/**
 * Julia › Conhecimento (`/julia/conhecimento`) — what Julia knows about the
 * business (contract section 3, wave 1). Tabs of section cards; [Editar] opens
 * a drawer (admin only — members read). Loading = two signals off `data`.
 */
import { useState } from "react";
import { AlertCircle, Eye, Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PreviewModal } from "@/components/julia/conhecimento/PreviewModal";
import { SecaoCard } from "@/components/julia/conhecimento/SecaoCard";
import { SecaoDrawer } from "@/components/julia/conhecimento/SecaoDrawer";
import { ABAS, SECOES } from "@/components/julia/conhecimento/secoes";
import { useJuliaConhecimento } from "@/hooks/useJuliaConhecimento";
import { JULIA_LABEL, JULIA_PAGES } from "@/nav/julia";

export default function JuliaConhecimento() {
  const isAdmin = useIsOrgAdmin();
  const q = useJuliaConhecimento();
  const [editando, setEditando] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{JULIA_LABEL} · {JULIA_PAGES.conhecimento.name}</h1>
          <p className="text-sm text-muted-foreground">
            O que a Julia sabe sobre o seu negócio. {!isAdmin && "Somente owner ou admin pode editar."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isRefreshing && <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="conhecimento-refreshing"><Loader2 className="h-3 w-3 animate-spin" /> Atualizando…</span>}
          <Button variant="outline" size="sm" onClick={() => setPreview(true)}><Eye className="mr-1 h-4 w-4" /> Ver o que a Julia sabe</Button>
        </div>
      </header>

      {showSkeleton ? (
        <div className="space-y-4" data-testid="conhecimento-skeleton">
          {[0, 1, 2].map((i) => <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />)}
        </div>
      ) : q.data ? (
        <Tabs defaultValue={ABAS[0].key}>
          <TabsList className="h-auto flex-wrap">
            {ABAS.map((a) => <TabsTrigger key={a.key} value={a.key}>{a.nome}</TabsTrigger>)}
          </TabsList>
          {ABAS.map((a) => (
            <TabsContent key={a.key} value={a.key} className="space-y-4">
              {a.secoes.map((k) => (
                <SecaoCard key={k} spec={SECOES[k]} saved={q.data.secoes[k]} isAdmin={isAdmin} onEdit={() => setEditando(k)} />
              ))}
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="conhecimento-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar o conhecimento da Julia.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      )}

      {editando && q.data && isAdmin && (
        <SecaoDrawer key={editando} spec={SECOES[editando]} saved={q.data.secoes[editando]} onClose={() => setEditando(null)}
          onReload={async () => (await q.refetch()).data?.secoes[editando]} />
      )}
      <PreviewModal open={preview} onClose={() => setPreview(false)} />
    </div>
  );
}
