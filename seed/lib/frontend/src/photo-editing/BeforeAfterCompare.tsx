/**
 * `<BeforeAfterCompare/>` — drag-to-reveal before/after photo comparison.
 *
 * Renders the "depois" (edited) image full-bleed with the "antes" (original)
 * image clipped over it via a slider — dragging the handle (or the keyboard,
 * via a native `<input type="range">`) reveals more/less of the original.
 * Pure presentational: no data fetching, no product coupling, so it travels
 * unchanged to the owner's phase-2 standalone app.
 *
 * Used by `PhotoReviewGrid` (expanded thumbnail state) and directly by any
 * product page that needs a before/after comparison (e.g. `ReferencePairCard`
 * intentionally does NOT use it — see that file for why).
 */
import { useId, useState } from 'react';
import { Badge } from '../design-system/ui/Badge';
import { cn } from '../utils';

export interface BeforeAfterCompareProps {
  urlAntes: string;
  urlDepois: string;
  altAntes?: string;
  altDepois?: string;
  /**
   * Renders the "Imagem gerada com IA" badge over the "depois" side — set
   * for virtual-staging output per contract §1 (Edit types: staging output
   * gets the watermark + this on-screen badge).
   */
  geradaComIA?: boolean;
  /** Initial slider position, 0-100. Default 50 (even split). */
  posicaoInicial?: number;
  className?: string;
}

export function BeforeAfterCompare({
  urlAntes,
  urlDepois,
  altAntes = 'Antes',
  altDepois = 'Depois',
  geradaComIA = false,
  posicaoInicial = 50,
  className,
}: BeforeAfterCompareProps) {
  const [posicao, setPosicao] = useState(posicaoInicial);
  const sliderId = useId();

  return (
    <div
      className={cn(
        'relative aspect-[4/3] w-full select-none overflow-hidden rounded-lg border border-border bg-muted',
        className,
      )}
    >
      {/* "Depois" — full-bleed base layer. */}
      <img
        src={urlDepois}
        alt={altDepois}
        className="absolute inset-0 h-full w-full object-cover"
        draggable={false}
      />

      {/* "Antes" — clipped to the slider position, drawn on top. */}
      <div
        className="absolute inset-0 h-full w-full overflow-hidden"
        style={{ clipPath: `inset(0 ${100 - posicao}% 0 0)` }}
      >
        <img
          src={urlAntes}
          alt={altAntes}
          className="h-full w-full object-cover"
          draggable={false}
        />
      </div>

      {/* Divider line at the slider position. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 w-0.5 bg-background shadow"
        style={{ left: `${posicao}%` }}
      />

      {/* Side labels. */}
      <span className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white">
        {altAntes}
      </span>
      <span className="pointer-events-none absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white">
        {altDepois}
      </span>

      {geradaComIA && (
        <Badge variant="default" className="absolute bottom-2 right-2">
          Imagem gerada com IA
        </Badge>
      )}

      {/* Drag control — native range input, transparent, stretched over the whole card so it's keyboard + touch accessible. */}
      <label htmlFor={sliderId} className="sr-only">
        Comparar antes e depois
      </label>
      <input
        id={sliderId}
        type="range"
        min={0}
        max={100}
        value={posicao}
        onChange={(e) => setPosicao(Number(e.target.value))}
        className="absolute inset-x-0 bottom-0 h-6 w-full cursor-ew-resize opacity-0"
        aria-label="Comparar antes e depois"
      />
    </div>
  );
}
