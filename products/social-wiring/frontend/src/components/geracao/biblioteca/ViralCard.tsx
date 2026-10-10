/**
 * One viral in the library grid (contract §7.3): checkbox, @handle, 9:16
 * thumbnail, overlay metrics ("—" for a missing value, never 0), duration,
 * post date and "Ver post". Views are not served by Business Discovery, so the
 * viral metric is likes + comments and views are usually "—".
 */
import { Checkbox } from "@/components/ui/checkbox";
import { compactoPtBr, dataPtBr } from "@/components/pesquisa/format";
import type { ViralCard as ViralCardT } from "@/types/geracao";

interface Props {
  viral: ViralCardT;
  selecionado?: boolean;
  /** Omit to hide the checkbox (picker mode shows none). */
  onSelecionar?: (viral: ViralCardT, marcado: boolean) => void;
  onAbrir: (viral: ViralCardT) => void;
}

export function duracaoMmSs(s: number | null | undefined): string {
  if (s == null) return "—";
  const total = Math.round(s);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function ViralCard({ viral, selecionado = false, onSelecionar, onAbrir }: Props) {
  return (
    <article
      className="flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm"
      data-testid={`viral-card-${viral.id}`}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        {onSelecionar && (
          <Checkbox
            aria-label={`Selecionar vídeo ${viral.codigo}`}
            checked={selecionado}
            onCheckedChange={(v) => onSelecionar(viral, v === true)}
          />
        )}
        <span className="truncate text-sm font-medium">@{viral.perfil.handle}</span>
      </div>
      <button
        type="button"
        onClick={() => onAbrir(viral)}
        className="relative aspect-[9/16] w-full bg-muted text-left"
        aria-label={`Abrir viral ${viral.codigo} de @${viral.perfil.handle}`}
      >
        {viral.thumbnail_url ? (
          <img
            src={viral.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="flex h-full items-center justify-center text-xs text-muted-foreground">
            Sem miniatura
          </span>
        )}
        <span className="absolute inset-x-0 bottom-0 flex flex-wrap gap-x-3 gap-y-0.5 bg-black/60 px-2 py-1 text-xs text-white">
          <span title="Visualizações">👁 {compactoPtBr(viral.views)}</span>
          <span title="Curtidas">♥ {compactoPtBr(viral.likes)}</span>
          <span title="Comentários">💬 {compactoPtBr(viral.comments)}</span>
        </span>
      </button>
      <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-muted-foreground">
        <span>
          {duracaoMmSs(viral.duracao_s)} · {dataPtBr(viral.publicado_em)}
        </span>
        <a
          href={viral.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-primary hover:underline"
        >
          Ver post
        </a>
      </div>
    </article>
  );
}
