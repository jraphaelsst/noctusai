/**
 * Edição de Fotos — Lotes (`/edicao-fotos`, `status_pagina` row
 * `edicao-fotos`, migration 128). The feature's landing page: every batch
 * the caller can see (own for corretor, org-wide for agency admin —
 * contract §1/§3), with its aggregate status, so "did my upload finish?"
 * never requires opening the review screen.
 *
 * Loading-state contract (CLAUDE.md §1 / EDICAO-FOTOS-CONTRACT.md §9,
 * binding): `showSkeleton`/`isRefreshing` come pre-computed off
 * `useLotes()` (`@noctusai/lib/photo-editing/hooks` via
 * `hooks/useEdicaoFotos.ts`) — this file never touches `.isLoading`.
 */
import { Link } from "react-router-dom";
import { AlertCircle, ImagePlus, Plus, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useLotes, type EstadoLoteAgregado, type LoteResumo } from "@/hooks/useEdicaoFotos";

const ESTADO_LABEL: Record<EstadoLoteAgregado, string> = {
  processando: "Processando",
  aguardando_revisao: "Aguardando revisão",
  concluido: "Concluído",
  com_falhas: "Com falhas",
};

const ESTADO_VARIANT: Record<EstadoLoteAgregado, "default" | "secondary" | "destructive" | "outline"> = {
  processando: "secondary",
  aguardando_revisao: "default",
  concluido: "outline",
  com_falhas: "destructive",
};

const VELOCIDADE_LABEL: Record<string, string> = {
  urgente: "Urgente",
  economico: "Econômico",
};

export default function Lotes() {
  const { lotes, total, showSkeleton, isRefreshing, error, refetch } = useLotes();

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Lotes</h1>
          <p className="text-sm text-muted-foreground">
            {error
              ? "Não foi possível carregar seus lotes."
              : showSkeleton
                ? "Carregando…"
                : `${total.toLocaleString("pt-BR")} lote(s).`}
          </p>
        </div>
        <Button asChild>
          <Link to="/edicao-fotos/novo">
            <Plus className="h-4 w-4" />
            Novo lote
          </Link>
        </Button>
      </div>

      {isRefreshing && !error && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
          <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
        </p>
      )}

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <LoadingState />
      ) : lotes.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {lotes.map((lote) => (
            <LoteCard key={lote.id} lote={lote} />
          ))}
        </div>
      )}
    </div>
  );
}

function LoteCard({ lote }: { lote: LoteResumo }) {
  const decidido = lote.total_fotos > 0 ? Math.round((lote.fotos_decididas / lote.total_fotos) * 100) : 0;

  return (
    <Link to={`/edicao-fotos/lotes/${lote.id}/revisao`} data-testid={`lote-card-${lote.id}`}>
      <Card className="h-full transition-colors hover:border-primary/50">
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium leading-tight">{lote.nome}</p>
            <Badge variant={ESTADO_VARIANT[lote.estado_agregado]}>{ESTADO_LABEL[lote.estado_agregado]}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {lote.fotos_decididas}/{lote.total_fotos} foto(s) decidida(s)
            {lote.total_fotos > 0 && ` · ${decidido}%`}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="outline">{VELOCIDADE_LABEL[lote.velocidade] ?? lote.velocidade}</Badge>
            {lote.imovel && <Badge variant="outline">Imóvel {lote.imovel.codigo}</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date(lote.criado_em).toLocaleDateString("pt-BR", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
            })}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

function LoadingState() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="lotes-loading">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-32 w-full rounded-lg" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os lotes.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card data-testid="lotes-empty">
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <ImagePlus className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Nenhum lote ainda.</p>
          <p className="text-sm text-muted-foreground">
            Crie um lote para enviar fotos de um imóvel para edição.
          </p>
        </div>
        <Button asChild>
          <Link to="/edicao-fotos/novo">
            <Plus className="h-4 w-4" />
            Novo lote
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
