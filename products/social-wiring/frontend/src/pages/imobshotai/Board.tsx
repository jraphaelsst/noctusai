/**
 * ImobShotAI -- board (`/imobshotai`, status_pagina `imobshotai`, contract §8). One card per imóvel, in the 4
 * etapas reachable in v1 (contract §6), on the seed `KanbanBoard` organ.
 *
 * Why `KanbanBoard` and not `FunnelBoard`: `FunnelBoard` is bound to a funnel backend (`GET P/meta`, `GET P/board`,
 * `POST .../mover-etapa`) this contract does not have -- and here the etapa is a PROJECTION derived from the photos
 * (contract §6), never moved by hand. `KanbanBoard` is the presentation-only organ of that family; cards are rendered `draggable={false}` (`onMove` is required by the organ but never fires).
 *
 * Search is the server's `q` (prefix of the ref). Loading-state contract: `showSkeleton` / `isRefreshing` come
 * pre-computed off `useImobCards`; the board never blanks while a refetch or a new search runs.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ImageOff, Plus, Search } from "lucide-react";
import { KanbanBoard } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { ETAPAS_FOTO, ETAPA_LABEL, useImobCards, type CardResumo } from "@/hooks/useImobShotAI";
import { tempoDesde } from "@/lib/imobshotaiFormat";

const PAGE_SIZE = 100;

export default function ImobShotBoard() {
  const navigate = useNavigate();
  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 250).trim();
  const { cards, total, showSkeleton, isRefreshing, error, refetch } = useImobCards({ q, pageSize: PAGE_SIZE });

  const colunas = ETAPAS_FOTO.map((etapa) => ({
    stage: { id: etapa, label: ETAPA_LABEL[etapa] },
    cards: cards.filter((c) => c.etapa === etapa),
  }));
  const semNenhum = !showSkeleton && !error && total === 0;

  return (
    <div className="space-y-4 p-6" data-testid="imobshotai-board" data-refreshing={isRefreshing ? "true" : "false"}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ImobShotAI</h1>
          <p className="text-sm text-muted-foreground">Cada imóvel passa pelas etapas de edição de fotos até a aprovação.</p>
        </div>
        <Button asChild>
          <Link to="/imobshotai/fotos/novo">
            <Plus className="h-4 w-4" /> Nova edição de fotos
          </Link>
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar pelo código do imóvel"
          aria-label="Buscar pelo código do imóvel"
          className="pl-8"
        />
      </div>

      {error && cards.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center" role="alert">
            <AlertCircle className="h-10 w-10 text-destructive" />
            <p className="font-medium">Não foi possível carregar os imóveis do ImobShotAI.</p>
            <Button variant="outline" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          </CardContent>
        </Card>
      ) : semNenhum ? (
        <Card data-testid="imobshotai-vazio">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ImageOff className="h-10 w-10 text-muted-foreground" />
            {q ? (
              <p className="font-medium">Nenhum imóvel com o código “{q}”.</p>
            ) : (
              <>
                <p className="font-medium">Nenhum imóvel no ImobShotAI ainda.</p>
                <p className="text-sm text-muted-foreground">Escolha um imóvel e envie as fotos para começar.</p>
                <Button asChild variant="outline">
                  <Link to="/imobshotai/fotos/novo">Nova edição de fotos</Link>
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <KanbanBoard<CardResumo>
            columns={showSkeleton ? [] : colunas} // `KanbanBoard` draws its skeleton only while it has no columns
            getCardId={(c) => c.id}
            getCardStage={(c) => c.etapa}
            isLoading={showSkeleton}
            // The etapa is derived from the photos (contract §6): cards are not draggable at all.
            draggable={false}
            onMove={() => {}}
            onCardActivate={(c) => navigate(`/imobshotai/imoveis/${c.id}`)}
            columnEmptyState={() => <p className="py-4 text-center text-xs text-muted-foreground">Nenhum imóvel.</p>}
            renderColumnHeader={(stage, colCards) => (
              <div className="flex items-center justify-between px-1">
                <h2 className="text-sm font-semibold">{stage.label}</h2>
                <span className="text-xs text-muted-foreground" aria-label={`${colCards.length} imóveis`}>
                  {colCards.length}
                </span>
              </div>
            )}
            renderCard={(c) => <CardFace card={c} />}
          />
          {total > cards.length && (
            <p className="text-xs text-muted-foreground" role="status">
              Mostrando {cards.length} de {total} imóveis — refine a busca pelo código.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function CardFace({ card }: { card: CardResumo }) {
  return (
    <div className="space-y-2 text-sm" data-testid="imobshotai-card">
      {card.capa_url ? (
        <img src={card.capa_url} alt={`Capa de ${card.imovel.codigo}`} className="aspect-video w-full rounded-md object-cover" draggable={false} />
      ) : (
        <div className="flex aspect-video w-full items-center justify-center rounded-md bg-muted text-muted-foreground" aria-label="Sem capa ainda">
          <ImageOff className="h-5 w-5" />
        </div>
      )}
      <p className="font-medium tabular-nums">{card.imovel.codigo}</p>
      <p className="truncate text-xs text-muted-foreground">{card.imovel.bairro ?? "—"}</p>
      <p className="text-xs text-muted-foreground">
        {card.fotos_aprovadas}/{card.total_fotos} fotos aprovadas
      </p>
      <p className="text-xs text-muted-foreground">Nesta etapa {tempoDesde(card.etapa_desde)}</p>
    </div>
  );
}
