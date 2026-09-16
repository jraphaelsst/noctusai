/**
 * Edição de Fotos — Revisão de Lote (`/edicao-fotos/lotes/:loteId/revisao`,
 * `status_pagina` row `edicao-fotos-revisao`, migration 128). Template:
 * `pages/clientes/RevisaoFila.tsx` (the review-queue shape: header + count,
 * loading/error/empty/success, a primary bulk action gated on readiness) —
 * adapted around the seed's `PhotoReviewGrid` organ instead of a bespoke
 * grid, per `check_canonical_organ_consumption` (products consume canonical
 * organs, never re-implement them).
 *
 * Zip readiness (contract §3 "download the .zip — 409 until every photo is
 * decided… `falhou` photos excluded from the zip and never block the
 * batch") is computed HERE from the same `fotos` array `PhotoReviewGrid`
 * renders — no separate "is the batch ready" endpoint exists in the
 * contract, so this mirrors the backend's own predicate rather than
 * guessing at a new field.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9, binding):
 * `showSkeleton`/`isRefreshing` come pre-computed off `useRevisao()` /
 * `useLote()` — this file never touches `.isLoading`. `useLote`/`useRevisao`
 * both key on `loteId` with `placeholderData`, so navigating between two
 * lotes' review screens never flashes empty.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertCircle, Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { PhotoReviewGrid } from "@noctusai/lib/photo-editing/PhotoReviewGrid";

import {
  useBaixarZip,
  useCapacidades,
  useDecidirFoto,
  useLote,
  useRetentarFoto,
  useRevisao,
  fotosPermissions,
  type DecisaoTipo,
} from "@/hooks/useEdicaoFotos";

export default function LoteRevisao() {
  const { loteId } = useParams<{ loteId: string }>();
  const [pendingFotoId, setPendingFotoId] = useState<string | null>(null);

  const { capacidades } = useCapacidades();
  const { lote } = useLote(loteId);
  const revisao = useRevisao(loteId);
  const decidirFoto = useDecidirFoto(loteId);
  const retentarFoto = useRetentarFoto(loteId);
  const baixarZip = useBaixarZip();

  const { fotos, showSkeleton, isRefreshing, error, refetch } = revisao;
  const podeVerVeredito = fotosPermissions.podeVerVeredito(capacidades);

  const fotosDecidiveis = fotos.filter((f) => f.estado !== "falhou");
  const zipPronto = fotosDecidiveis.length > 0 && fotosDecidiveis.every((f) => f.decisao !== null);

  async function handleDecidir(fotoId: string, decisao: DecisaoTipo, comentario: string | null) {
    setPendingFotoId(fotoId);
    try {
      await decidirFoto.mutateAsync({ fotoId, body: { decisao, comentario } });
    } catch (err) {
      toast.error("Não foi possível salvar a decisão.", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setPendingFotoId(null);
    }
  }

  async function handleRetry(fotoId: string) {
    setPendingFotoId(fotoId);
    try {
      await retentarFoto.mutateAsync(fotoId);
    } catch (err) {
      toast.error("Não foi possível reprocessar a foto.", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setPendingFotoId(null);
    }
  }

  async function handleBaixarZip() {
    if (!loteId) return;
    try {
      await baixarZip.mutateAsync({
        loteId,
        nomeArquivo: `${(lote?.nome ?? loteId).replace(/[^a-z0-9-_]+/gi, "-")}.zip`,
      });
    } catch (err) {
      toast.error("Não foi possível baixar o zip.", {
        description: err instanceof Error ? err.message : "Ainda há fotos sem decisão neste lote.",
      });
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Revisão — {lote?.nome ?? "Lote"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {error
              ? "Não foi possível carregar as fotos deste lote."
              : showSkeleton
                ? "Carregando…"
                : `${fotos.length} foto(s) · ${fotosDecidiveis.filter((f) => f.decisao !== null).length}/${fotosDecidiveis.length} decidida(s).`}
          </p>
        </div>
        <Button onClick={handleBaixarZip} disabled={!zipPronto || baixarZip.isPending} title={
          zipPronto ? undefined : "Decida todas as fotos (aprovar ou rejeitar) para liberar o download."
        }>
          <Download className="h-4 w-4" />
          {baixarZip.isPending ? "Baixando…" : "Baixar zip"}
        </Button>
      </div>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : (
        <PhotoReviewGrid
          fotos={fotos}
          podeVerVeredito={podeVerVeredito}
          showSkeleton={showSkeleton}
          isRefreshing={isRefreshing}
          onDecidir={handleDecidir}
          onRetry={handleRetry}
          pendingFotoId={pendingFotoId}
        />
      )}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar a revisão deste lote.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
