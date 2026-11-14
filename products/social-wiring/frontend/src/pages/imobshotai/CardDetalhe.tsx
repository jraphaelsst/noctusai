/**
 * ImobShotAI -- card detail (`/imobshotai/imoveis/:cardId`, status_pagina `imobshotai-card`, contract §4, §8).
 * Header (ref, título, bairro, etapa) · photos grouped by lote, original beside edited · an empty videos section
 * ("Vídeo em breve") · the event timeline. `404 card_nao_encontrado` (also another org's card, never 403) renders a
 * friendly not-found. Loading-state contract: `showSkeleton` / `isRefreshing` come pre-computed off `useImobCard`.
 */
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Film, SearchX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ETAPA_LABEL,
  useImobCard,
  type CardDetalhe,
  type CardEvento,
  type CardFoto,
} from "@/hooks/useImobShotAI";
import { codigoDoErro } from "@/lib/imobshotaiErros";
import { dataHoraBR, tempoDesde } from "@/lib/imobshotaiFormat";

export default function CardDetalhePage() {
  const { cardId } = useParams<{ cardId: string }>();
  const { card, showSkeleton, isRefreshing, error, refetch } = useImobCard(cardId);

  if (error && !card) {
    return codigoDoErro(error) === "card_nao_encontrado" ? <NaoEncontrado /> : <ErroCarregar onRetry={() => refetch()} />;
  }
  if (showSkeleton || !card) return <DetalheSkeleton />;

  return (
    <div className="space-y-6 p-6" data-testid="imobshotai-card-detalhe" data-refreshing={isRefreshing ? "true" : "false"}>
      <Button asChild variant="ghost" size="sm">
        <Link to="/imobshotai">
          <ArrowLeft className="h-4 w-4" /> Voltar ao quadro
        </Link>
      </Button>

      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight tabular-nums">{card.imovel.codigo}</h1>
          <Badge variant="secondary">{ETAPA_LABEL[card.etapa] ?? card.etapa}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {[card.imovel.titulo, card.imovel.bairro].filter(Boolean).join(" · ") || "—"}
        </p>
        <p className="text-xs text-muted-foreground">
          Nesta etapa {tempoDesde(card.etapa_desde)} · {card.fotos_aprovadas}/{card.total_fotos} fotos aprovadas
        </p>
      </header>

      <FotosPorLote card={card} />

      <section aria-labelledby="videos-titulo" className="space-y-2">
        <h2 id="videos-titulo" className="text-lg font-semibold">
          Vídeos
        </h2>
        <Card>
          <CardContent className="flex items-center gap-3 py-6 text-sm text-muted-foreground">
            <Film className="h-5 w-5" aria-hidden />
            Vídeo em breve
          </CardContent>
        </Card>
      </section>

      <Timeline eventos={card.eventos} />
    </div>
  );
}

function FotosPorLote({ card }: { card: CardDetalhe }) {
  return (
    <section aria-labelledby="fotos-titulo" className="space-y-4">
      <h2 id="fotos-titulo" className="text-lg font-semibold">
        Fotos
      </h2>
      {card.lotes.length === 0 || card.fotos.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="imobshotai-sem-fotos">
          Nenhuma foto neste imóvel ainda.
        </p>
      ) : (
        card.lotes.map((lote) => {
          const fotos = card.fotos.filter((f) => f.lote_id === lote.id);
          if (fotos.length === 0) return null;
          return (
            <div key={lote.id} className="space-y-2" data-testid={`imobshotai-lote-${lote.id}`}>
              <h3 className="text-sm font-medium">
                {lote.nome} <span className="font-normal text-muted-foreground">· {fotos.length} foto(s)</span>
              </h3>
              <ul className="grid gap-3 sm:grid-cols-2">
                {fotos.map((f) => (
                  <FotoPar key={f.id} foto={f} />
                ))}
              </ul>
            </div>
          );
        })
      )}
    </section>
  );
}

function FotoPar({ foto }: { foto: CardFoto }) {
  const rotulo = foto.comodo ?? "Foto";
  return (
    <li className="space-y-1 rounded-lg border border-border p-2" data-testid="imobshotai-foto">
      <div className="grid grid-cols-2 gap-2">
        <figure className="space-y-1">
          <img src={foto.original_url} alt={`${rotulo} — original`} className="aspect-square w-full rounded-md object-cover" />
          <figcaption className="text-center text-xs text-muted-foreground">Original</figcaption>
        </figure>
        <figure className="space-y-1">
          {foto.editada_url ? (
            <img src={foto.editada_url} alt={`${rotulo} — editada`} className="aspect-square w-full rounded-md object-cover" />
          ) : (
            <div className="flex aspect-square w-full items-center justify-center rounded-md bg-muted px-2 text-center text-xs text-muted-foreground">
              Edição ainda não disponível
            </div>
          )}
          <figcaption className="text-center text-xs text-muted-foreground">Editada</figcaption>
        </figure>
      </div>
      <Badge variant="muted">{foto.status}</Badge>
    </li>
  );
}

const EVENTO_TEXTO: Record<CardEvento["tipo"], (e: CardEvento) => string> = {
  card_criado: () => "Imóvel adicionado ao ImobShotAI",
  lote_vinculado: () => "Lote de fotos vinculado",
  etapa_mudou: (e) =>
    `Etapa: ${e.etapa_de ? (ETAPA_LABEL[e.etapa_de] ?? e.etapa_de) : "—"} → ${e.etapa_para ? (ETAPA_LABEL[e.etapa_para] ?? e.etapa_para) : "—"}`,
  card_arquivado: () => "Imóvel arquivado",
};

function Timeline({ eventos }: { eventos: CardEvento[] }) {
  return (
    <section aria-labelledby="timeline-titulo" className="space-y-2">
      <h2 id="timeline-titulo" className="text-lg font-semibold">
        Histórico
      </h2>
      {eventos.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum evento registrado.</p>
      ) : (
        <ol className="space-y-2 border-l border-border pl-4">
          {eventos.map((e, i) => (
            <li key={`${e.em}-${i}`} className="text-sm" data-testid="imobshotai-evento">
              <p>{(EVENTO_TEXTO[e.tipo] ?? (() => e.tipo))(e)}</p>
              <p className="text-xs text-muted-foreground">{dataHoraBR(e.em)}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function DetalheSkeleton() {
  return (
    <div className="space-y-4 p-6" data-testid="imobshotai-card-loading" role="status" aria-label="Carregando imóvel">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-72" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

function NaoEncontrado() {
  return (
    <div className="p-6">
      <Card data-testid="imobshotai-card-nao-encontrado">
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <SearchX className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Esse imóvel não foi encontrado no ImobShotAI.</p>
          <p className="text-sm text-muted-foreground">Ele pode ter sido removido ou você não tem acesso a ele.</p>
          <Button asChild variant="outline">
            <Link to="/imobshotai">Voltar ao quadro</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function ErroCarregar({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="p-6">
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center" role="alert">
          <AlertCircle className="h-10 w-10 text-destructive" />
          <p className="font-medium">Não foi possível carregar este imóvel.</p>
          <Button variant="outline" onClick={onRetry}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
