/**
 * `<PhotoReviewGrid/>` — the review screen's core organ (contract §4 `/revisao`).
 *
 * Expandable thumbnails, ✓/✗ decision per photo, ✗ requires a non-empty
 * comment (client-side gate mirroring the backend's 422 — contract §4), and
 * decisions are always changeable (re-clicking ✓/✗ re-submits, including
 * after the batch's zip has already been downloaded). `falhou` photos (a
 * TECHNICAL failure, contract §3 — auto-retried once server-side already)
 * render their reason plus a manual retry action instead of ✓/✗.
 *
 * 🔴 The AI verdict is gated EXCLUSIVELY by the `podeVerVeredito` prop —
 * caller-supplied from `capacidades.pode_ver_veredito` (never derived here
 * from role/SSO). It is rendered only when `podeVerVeredito` is true AND the
 * photo carries `avaliacao` (the backend already withholds the field from a
 * corretor by table separation — this is defense in depth, not the
 * boundary). Corretores never see it, full stop (contract §1).
 *
 * Pure presentational — data comes in as props (typically via
 * `createEdicaoFotosHooks(api).useRevisao(loteId)`, which already computes
 * `showSkeleton`/`isRefreshing` per the two-signal loading contract). No
 * `.isLoading` anywhere in this file.
 */
import { useState } from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { Skeleton } from '../design-system/ui/Skeleton';
import { cn } from '../utils';
import { BeforeAfterCompare } from './BeforeAfterCompare';
import type { DecisaoTipo, FotoRevisao } from './hooks';

export interface PhotoReviewGridProps {
  fotos: FotoRevisao[];
  /** From `capacidades.pode_ver_veredito` — never derive this locally. */
  podeVerVeredito: boolean;
  /** `isPending && !data` from the backing query — render the skeleton grid. */
  showSkeleton: boolean;
  /** `isFetching && !!data` — a non-blocking "Atualizando…" indicator, never an early return. */
  isRefreshing?: boolean;
  onDecidir: (fotoId: string, decisao: DecisaoTipo, comentario: string | null) => void;
  /** Omit to hide the retry action (e.g. read-only viewers). */
  onRetry?: (fotoId: string) => void;
  /** Id of the photo currently submitting a decision/retry — disables just that card's controls. */
  pendingFotoId?: string | null;
  className?: string;
}

const ESTADO_LABEL: Record<string, string> = {
  recebida: 'Recebida',
  normalizando: 'Normalizando',
  pronta: 'Pronta',
  editando: 'Editando',
  em_lote_openai: 'Em lote (econômico)',
  editada: 'Editada',
  avaliando: 'Avaliando',
  aguardando_decisao: 'Aguardando decisão',
  aprovada: 'Aprovada',
  rejeitada: 'Rejeitada',
  falhou: 'Falhou',
};

export function PhotoReviewGrid({
  fotos,
  podeVerVeredito,
  showSkeleton,
  isRefreshing = false,
  onDecidir,
  onRetry,
  pendingFotoId = null,
  className,
}: PhotoReviewGridProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [draftComentario, setDraftComentario] = useState('');

  if (showSkeleton) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Carregando fotos"
        className={cn('grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4', className)}
      >
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} height={160} announce={i === 0} className="w-full" />
        ))}
      </div>
    );
  }

  function startRejecting(foto: FotoRevisao) {
    setRejectingId(foto.id);
    setDraftComentario(foto.comentario ?? '');
  }

  function cancelRejecting() {
    setRejectingId(null);
    setDraftComentario('');
  }

  function confirmRejecting(fotoId: string) {
    const comentario = draftComentario.trim();
    if (!comentario) return; // ✗ requires a non-empty comment — client-side mirror of the backend 422.
    onDecidir(fotoId, 'rejeitar', comentario);
    setRejectingId(null);
    setDraftComentario('');
  }

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {isRefreshing && (
        <p className="text-xs text-muted-foreground" role="status">
          Atualizando…
        </p>
      )}

      {fotos.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Nenhuma foto neste lote.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {fotos.map((foto) => {
            const isExpanded = expandedId === foto.id;
            const isRejecting = rejectingId === foto.id;
            const isPending = pendingFotoId === foto.id;
            const isFalhou = foto.estado === 'falhou';
            const mostraVeredito = podeVerVeredito && !!foto.avaliacao;

            return (
              <div
                key={foto.id}
                className={cn(
                  'flex flex-col gap-2 rounded-lg border border-border bg-background p-2',
                  isExpanded && 'col-span-2 row-span-2 sm:col-span-3 lg:col-span-4',
                )}
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : foto.id)}
                  className="relative overflow-hidden rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-expanded={isExpanded}
                  aria-label={isExpanded ? 'Recolher foto' : 'Expandir foto'}
                >
                  {isExpanded && foto.url_depois ? (
                    <BeforeAfterCompare urlAntes={foto.url_antes} urlDepois={foto.url_depois} />
                  ) : (
                    <img
                      src={foto.url_depois ?? foto.url_antes}
                      alt={foto.comodo ?? 'Foto do lote'}
                      className={cn('aspect-square w-full object-cover', isExpanded && 'aspect-video')}
                      draggable={false}
                    />
                  )}
                </button>

                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant={isFalhou ? 'destructive' : 'muted'}>
                    {ESTADO_LABEL[foto.estado] ?? foto.estado}
                  </Badge>
                  {foto.decisao === 'aprovar' && <Badge variant="default">Aprovada</Badge>}
                  {foto.decisao === 'rejeitar' && <Badge variant="destructive">Rejeitada</Badge>}
                </div>

                {mostraVeredito && foto.avaliacao && (
                  <div className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
                    <p>
                      <strong>Veredito IA:</strong>{' '}
                      {foto.avaliacao.veredito === 'aprovar' ? 'Aprovar' : 'Rejeitar'} (
                      {foto.avaliacao.score}/10)
                    </p>
                    <p>{foto.avaliacao.motivo}</p>
                  </div>
                )}

                {isFalhou ? (
                  <div className="flex flex-col gap-2">
                    <p role="alert" className="text-xs text-destructive">
                      {foto.falha_motivo ?? 'Falha técnica no processamento.'}
                    </p>
                    {onRetry && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onRetry(foto.id)}
                        disabled={isPending}
                      >
                        {isPending ? 'Tentando…' : 'Tentar novamente'}
                      </Button>
                    )}
                  </div>
                ) : isRejecting ? (
                  <div className="flex flex-col gap-2">
                    <label htmlFor={`comentario-${foto.id}`} className="text-xs text-muted-foreground">
                      Comentário (obrigatório)
                    </label>
                    <textarea
                      id={`comentario-${foto.id}`}
                      value={draftComentario}
                      onChange={(e) => setDraftComentario(e.target.value)}
                      placeholder="Explique o motivo da rejeição"
                      rows={2}
                      className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={cancelRejecting} disabled={isPending}>
                        Cancelar
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => confirmRejecting(foto.id)}
                        disabled={isPending || !draftComentario.trim()}
                      >
                        Confirmar rejeição
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Button
                      variant={foto.decisao === 'aprovar' ? 'primary' : 'outline'}
                      size="sm"
                      onClick={() => onDecidir(foto.id, 'aprovar', null)}
                      disabled={isPending}
                      aria-label="Aprovar foto"
                    >
                      ✓ Aprovar
                    </Button>
                    <Button
                      variant={foto.decisao === 'rejeitar' ? 'destructive' : 'outline'}
                      size="sm"
                      onClick={() => startRejecting(foto)}
                      disabled={isPending}
                      aria-label="Rejeitar foto"
                    >
                      ✗ Rejeitar
                    </Button>
                  </div>
                )}

                {foto.decisao === 'rejeitar' && !isRejecting && foto.comentario && (
                  <p className="text-xs text-muted-foreground">"{foto.comentario}"</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
