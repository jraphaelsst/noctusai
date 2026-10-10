import { AlertCircle, ExternalLink, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { compactoPtBr, dataPtBr } from "@/components/pesquisa/format";
import { useAssuntoFontes, type ViralTopic } from "@/hooks/useAssuntosVirais";

interface Props {
  assunto: ViralTopic | null;
  onClose: () => void;
}

/** "Assuntos Virais — «topic»": the posts that made the topic viral. */
export function AssuntoFontesModal({ assunto, onClose }: Props) {
  const fontesQ = useAssuntoFontes(assunto?.id ?? null);
  const fontes = fontesQ.data ?? [];
  return (
    <Dialog open={assunto !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Assuntos Virais — «{assunto?.topic}»</DialogTitle>
          <DialogDescription>
            Posts que originaram este assunto.
          </DialogDescription>
        </DialogHeader>
        {fontesQ.showSkeleton ? (
          <p
            role="status"
            className="py-10 text-center text-sm text-muted-foreground"
          >
            Buscando dados dos virais...
          </p>
        ) : fontesQ.isError && !fontesQ.data ? (
          <div
            role="alert"
            className="flex flex-col items-center gap-3 py-10 text-sm"
          >
            <AlertCircle className="h-6 w-6 text-destructive" />
            Não foi possível carregar os virais deste tópico.
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fontesQ.refetch()}
            >
              Tentar novamente
            </Button>
          </div>
        ) : fontes.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Nenhum dado viral encontrado para este tópico.
          </p>
        ) : (
          <div
            className="grid max-h-[60vh] grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-3"
            data-testid="assunto-fontes"
          >
            {fontes.map((f) => (
              <a
                key={`${f.source_kind}:${f.source_id}`}
                href={f.url ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Abrir post ${f.source_id}`}
                className="flex flex-col overflow-hidden rounded-md border bg-card text-left text-xs hover:border-primary"
              >
                <div className="flex aspect-video items-center justify-center bg-muted">
                  {f.thumbnail_url ? (
                    <img
                      src={f.thumbnail_url}
                      alt=""
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <Play
                      className="h-6 w-6 text-muted-foreground"
                      aria-hidden
                    />
                  )}
                </div>
                <div className="space-y-1 p-2">
                  <p className="text-muted-foreground">
                    {compactoPtBr(f.plays)} Views · {compactoPtBr(f.likes)}{" "}
                    Likes · {compactoPtBr(f.comments)} Comentários
                  </p>
                  <p className="text-muted-foreground">
                    {dataPtBr(f.published_at)}
                  </p>
                  {f.excerpt && <p className="line-clamp-3">{f.excerpt}</p>}
                  {f.url && (
                    <ExternalLink
                      className="h-3 w-3 text-muted-foreground"
                      aria-hidden
                    />
                  )}
                </div>
              </a>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
